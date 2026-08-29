#!/usr/bin/env python3
"""역추적(backtrack): 2024·2025 축제일 데이터로 "여의도에 온 사람은 어디서 탔나" → 2026 사전 예측표.
라이브 데이터 없이 완성되는 예측. nowcast.py(당일 α 보정)는 이 위에 얹는 선택 레이어.

  .venv/bin/python src/backtrack.py

입력 (data/raw, git 제외 — src/fetch_seoul_data.py 로 재다운로드)
  od_20241005.zip, od_20250927.zip   KT 생활이동 출발-도착 행정동(목적) OA-22300 — 여의동(11560540) 유입·유출
  mode_20250927.zip                  KT 생활이동 수단 OA-22657 — 출발지별 지하철 비중 (2024는 수단 파일 없음 → 2025 비중 적용)
  subway_2024.csv, subway_2025.csv   서울교통공사 역별·일별·시간대별 승하차 OA-12921 (1~8호선)
  data/derived/stations.json         역 → 구·좌표 (StationAdresTelno + subwayStationMaster, 2026-08-29)
출력 (data/derived, 커밋)
  feeder_origin.json        출발지(구·시군)별 여의도행 유입 · 서울 역별 귀속 승차(피더 표) · 유입/유출 대칭 검증
  exit_forecast_2026.json   출발지 구성 기반 2026 시간대별 출구 수요·부하율 (2년 범위 lo/hi + 평균)

방법
  1. 유입: OD에서 d=여의동 인 행을 출발 행정동·시간대로 합산 → 구/시군 단위.
  2. 지하철 유입 = 유입 × 출발지별 지하철 비중(수단 OD 2025, 10~19시).
  3. 역 귀속(서울 출발지만): 구의 지하철 유입을 그 구 안 역들에 "축제일 초과 승차(대조 토요일 평균 대비)" 비율로 배분.
     가중치 = 2024·2025 양수 초과의 기하평균 — 한 해만 튄 역(타 행사)은 0. 모두 0이면 축제일 승차 비율.
     경기·인천 출발지는 서울교통공사 데이터 밖(코레일·9호선·공항철도) → 시군 단위로만. 여의도·여의나루는 목적지라 제외.
  4. 귀가 방향 = 유입 출발지 회랑 구성(유입≈유출 대칭을 같은 파일에서 검증해 오차를 적는다).
  5. 출구 수요 = nowcast.py 와 같은 규칙(유출곡선 +40분, 도달지연 40/60, 회랑→역 배정표, 여의나루 통제)로 연도별 계산.
     대표값 = 유입 출발지 회랑 기준 2년 평균. 범위(lo/hi) = {2024,2025} × {출발지 기준, 유출 도착지 기준} 4회 계산의 최소/최대.
숫자 규칙: KT cnt 는 추정치 — 비율·순위 용도. 용량 추정치(9호선·도보·1호선 합산)는 estimated_capacity 로 표기.
"""
import zipfile, io, csv, json, re, sys, pathlib, collections, statistics, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
sys.path.insert(0, str(ROOT / "src"))
import baseline as B                      # corridor(), GU, MODE
import nowcast as N                       # ASSIGN, CAP, ESTIMATED, CLOSED, SHIFT_MIN

Y = B.Y
DAYS = {"2024": "20241005", "2025": "20250927"}
CONTROL = {"2024": ["20240928", "20241012"], "2025": ["20250913", "20250920"]}   # 대조 토요일. 2025-10-04 는 추석 연휴(10/3~10/9) 시작일이라 제외
DEST_STATIONS = {"여의도", "여의나루"}    # 여의동 안 역 = 목적지, 피더 귀속 제외
IN_HOURS = list(range(10, 20))            # 유입 집계 창 (출발 시각)
SIGUN = {"41110": "수원", "41130": "성남", "41150": "의정부", "41170": "안양", "41190": "부천", "41210": "광명", "41220": "평택", "41250": "동두천",
         "41270": "안산", "41280": "고양", "41290": "과천", "41310": "구리", "41360": "남양주", "41370": "오산", "41390": "시흥", "41410": "군포",
         "41430": "의왕", "41450": "하남", "41460": "용인", "41480": "파주", "41500": "이천", "41550": "안성", "41570": "김포", "41590": "화성",
         "41610": "광주", "41630": "양주", "41650": "포천", "41670": "여주", "41800": "연천", "41820": "가평", "41830": "양평"}


def origin_key(code):
    """행정동 코드 → 서울 구명 / 경기 시군명 / 인천 / 기타"""
    if code.startswith("11"): return B.GU.get(code[:5], "서울기타")
    if code.startswith("41"): return SIGUN.get(code[:5], "경기" + code[:5])
    if code.startswith("28"): return "인천"
    return "기타"


def stream_zip_csv(p):
    z = zipfile.ZipFile(p); name = z.namelist()[0]
    with z.open(name) as f:
        rd = csv.reader(io.TextIOWrapper(f, encoding="cp949", errors="ignore"))
        hdr = next(rd); idx = {h: i for i, h in enumerate(hdr)}
        for r in rd:
            if len(r) < len(hdr): continue
            yield r, idx


def od_inflow_outflow(day):
    """여의동 유입 [(출발키, 시)] · 유출 [(도착키, 시)] (cnt 합). 헤더 중복행 등 오류행은 건너뜀."""
    inflow, outflow = collections.Counter(), collections.Counter()
    n = 0
    for r, i in stream_zip_csv(RAW / f"od_{day}.zip"):
        o, d = r[i["o_admdong_cd"]], r[i["d_admdong_cd"]]
        if d != Y and o != Y: continue
        try: v = float(r[i["cnt"]] or 0); t = int(r[i["st_time_cd"]][:2])
        except ValueError: continue
        if d == Y and o != Y: inflow[(origin_key(o), t)] += v
        elif o == Y and d != Y: outflow[(origin_key(d), t)] += v
        n += 1
    print(f"  od {day}: 여의동 관련 {n:,}행", flush=True)
    return inflow, outflow


def mode_subway_share(day):
    """출발키별 지하철 비중(유입, 10~19시) · 도착키별 지하철 비중(유출, 20시~)"""
    tot_in, sub_in = collections.Counter(), collections.Counter()
    tot_out, sub_out = collections.Counter(), collections.Counter()
    for r, i in stream_zip_csv(RAW / f"mode_{day}.zip"):
        o, d = r[i["o_admdong_cd"]], r[i["d_admdong_cd"]]
        if d != Y and o != Y: continue
        try: v = float(r[i["cnt"]] or 0); t = int(r[i["st_time_cd"]][:2])
        except ValueError: continue
        m = B.MODE.get(r[i["move_trans"]], r[i["move_trans"]])
        if d == Y and o != Y and t in IN_HOURS:
            k = origin_key(o); tot_in[k] += v
            if m == "지하철": sub_in[k] += v
        elif o == Y and d != Y and t >= 20:
            k = origin_key(d); tot_out[k] += v
            if m == "지하철": sub_out[k] += v
    share_in = {k: round(sub_in[k] / tot_in[k], 4) for k in tot_in if tot_in[k] > 0}
    share_out = {k: round(sub_out[k] / tot_out[k], 4) for k in tot_out if tot_out[k] > 0}
    overall_in = sum(sub_in.values()) / max(1, sum(tot_in.values()))
    print(f"  mode {day}: 유입 지하철 비중 전체 {overall_in:.3f}", flush=True)
    return share_in, share_out, round(overall_in, 4)


def norm(name):
    return re.sub(r"\(.*?\)", "", name).replace(" ", "").strip()


def hour_of(col):
    if "이전" in col: return 5
    if "이후" in col: return 24
    m = re.match(r"\s*(\d{1,2})", col); return int(m.group(1)) if m else None


def subway_boarding(year, days):
    """OA-12921 → {day: {역(정규화): {h: 승차}}}. 호선 합산. lines[역] = 호선 목록."""
    raw = (RAW / f"subway_{year}.csv").read_bytes().decode("cp949", "ignore")
    rd = csv.reader(io.StringIO(raw)); hdr = next(rd)
    di = next(i for i, h in enumerate(hdr) if "일자" in h or "날짜" in h)
    si = hdr.index("역명"); li = hdr.index("호선"); ti = next(i for i, h in enumerate(hdr) if "구분" in h)
    hcols = [(i, hour_of(h)) for i, h in enumerate(hdr) if "시" in h and i not in (di, si, ti, li) and hour_of(h) is not None]
    out = {d: collections.defaultdict(lambda: collections.Counter()) for d in days}
    lines = collections.defaultdict(set)
    for r in rd:
        d = r[di].replace("-", "")
        if d not in out or r[ti] != "승차": continue
        st = norm(r[si]); lines[st].add(r[li])
        for i, h in hcols:
            try: out[d][st][h] += int(float(r[i] or 0))
            except ValueError: pass
    return out, {k: sorted(v) for k, v in lines.items()}


def load_stations():
    S = json.loads((DER / "stations.json").read_text(encoding="utf-8"))["stations"]
    by = {}
    for nm, v in S.items():
        for k in {norm(nm), norm(nm) + "역", norm(nm).rstrip("역")}:
            by.setdefault(k, v)
    return by


def exit_forecast(out_curve, dirs, sub_share):
    """nowcast.main() 과 같은 규칙, α=1, 라이브 없음. out_curve: {h: 유출}, dirs: 회랑 비중, sub_share: 지하철 비중"""
    f = (N.SHIFT_MIN % 60) / 60; k = N.SHIFT_MIN // 60
    shifted = {h: (1 - f) * out_curve.get(h - k, 0) + f * out_curve.get(h - k - 1, 0) for h in range(17, 25)}
    LAG_SAME, LAG_NEXT = 0.4, 0.6
    exits = collections.OrderedDict(); backlog = collections.Counter()
    for h in (19, 20, 21, 22, 23):
        arriving = LAG_SAME * shifted.get(h, 0) + LAG_NEXT * shifted.get(h - 1, 0)
        demand = collections.Counter()
        for d, share in dirs.items():
            for st, w in N.ASSIGN.get(d, {}).items():
                demand[st] += arriving * share * sub_share * w
        for st in list(demand):
            if (st, h) in N.CLOSED: demand["여의도(5)"] += demand[st]; demand[st] = 0.0
        for st in N.CAP:
            dem = demand.get(st, 0.0); cap = N.CAP[st]; closed = (st, h) in N.CLOSED
            backlog[st] = 0.0 if closed else max(0.0, backlog[st] + dem - cap)
            exits.setdefault(st, {})[h] = {"demand": round(dem), "load": None if closed else round(dem / cap, 3),
                                          "wait_min": None if closed else round(backlog[st] / cap * 60), "closed": closed}
    return {h: round(v) for h, v in shifted.items() if 19 <= h <= 23}, exits


def main():
    print("1/5 OD 유입·유출", flush=True)
    od = {y: od_inflow_outflow(d) for y, d in DAYS.items()}
    print("2/5 수단 비중 (2025)", flush=True)
    share_in, share_out, overall_in = mode_subway_share(DAYS["2025"])
    print("3/5 지하철 승차 (OA-12921)", flush=True)
    stations = load_stations()
    board, lines = {}, {}
    for y in DAYS:
        b, l = subway_boarding(y, [DAYS[y]] + CONTROL[y]); board[y] = b; lines.update(l)

    # ── 출발지 표 (구·시군) ──
    origins = {}
    keys = sorted({k for y in DAYS for (k, t) in od[y][0]})
    tot_in = {y: sum(v for (k, t), v in od[y][0].items() if t in IN_HOURS) for y in DAYS}
    for k in keys:
        rec = {"corridor": None, "subway_share_2025": share_in.get(k), "by_year": {}}
        for y in DAYS:
            inflow_h = {t: round(od[y][0].get((k, t), 0)) for t in IN_HOURS}
            total = sum(inflow_h.values())
            ss = share_in.get(k, overall_in)
            rec["by_year"][y] = {"inflow": total, "share": round(total / tot_in[y], 4), "inflow_by_hour": inflow_h,
                                 "subway_inflow": round(total * ss), "subway_inflow_by_hour": {t: round(v * ss) for t, v in inflow_h.items()}}
        rec["share_mean"] = round(statistics.mean(rec["by_year"][y]["share"] for y in DAYS), 4)
        # 회랑: 코드 대신 키로 판정 (서울 구명·경기 시군코드)
        code = next(c for c in [g for g in B.GU if B.GU[g] == k] + [c for c, n in SIGUN.items() if n == k] + (["28000"] if k == "인천" else ["99999"]))
        rec["corridor"] = B.corridor(code)
        origins[k] = rec
    origins = dict(sorted(origins.items(), key=lambda x: -x[1]["share_mean"]))

    # ── 유입 출발지 회랑 구성 vs 유출 도착지 회랑 구성 (대칭 검증) ──
    symmetry = {}
    for y in DAYS:
        cin, cout = collections.Counter(), collections.Counter()
        for (k, t), v in od[y][0].items():
            if t in IN_HOURS: cin[origins[k]["corridor"]] += v
        for (k, t), v in od[y][1].items():
            if t >= 20: cout[origin_key_to_corridor(k, origins)] += v
        si, so = sum(cin.values()), sum(cout.values())
        symmetry[y] = {c: {"inflow_origin": round(cin[c] / si, 4), "outflow_dest": round(cout[c] / so, 4), "diff_pp": round(100 * (cout[c] / so - cin[c] / si), 1)} for c in sorted(set(cin) | set(cout))}

    # ── 서울 역 귀속 (피더 표) ──
    print("4/5 역 귀속", flush=True)
    feeders = {}
    gu_stations = collections.defaultdict(list)
    for st in {s for y in DAYS for d in board[y] for s in board[y][d]}:
        info = stations.get(st) or stations.get(st + "역")
        if info and info.get("sido") == "서울":
            g = info["gu"]; g = g if g == "중구" else g[:-1]      # 구 이름을 baseline.GU 표기로 (영등포구→영등포, 중구는 유지)
            gu_stations[g].append(st)
    unmatched = sorted({s for y in DAYS for d in board[y] for s in board[y][d]} - {s for v in gu_stations.values() for s in v})
    xval = {}
    for sts in gu_stations.values(): sts[:] = [s for s in sts if s not in DEST_STATIONS]
    # 초과 승차 (연도별) → 2년 기하평균 가중치
    ex = {y: {} for y in DAYS}
    for y in DAYS:
        fest, ctrl = board[y][DAYS[y]], [board[y][c] for c in CONTROL[y]]
        for sts in gu_stations.values():
            for st in sts:
                for t in IN_HOURS:
                    c = statistics.mean(cc[st][t] for cc in ctrl) if all(st in cc for cc in ctrl) else 0
                    ex[y][(st, t)] = (fest[st][t] - c, fest[st][t], c)
    W = {k: (max(ex["2024"][k][0], 0) * max(ex["2025"][k][0], 0)) ** 0.5 for k in ex["2024"] if k in ex["2025"]}
    for y in DAYS:
        seoul_sub_in = 0; excess_pos = sum(max(v[0], 0) for v in ex[y].values())
        for gu, sts in gu_stations.items():
            org = origins.get(gu)
            if not org or not sts: continue
            sub_h = org["by_year"][y]["subway_inflow_by_hour"]
            seoul_sub_in += sum(sub_h.values())
            for t in IN_HOURS:
                ws = {st: W.get((st, t), 0.0) for st in sts}
                basis = "excess_2yr" if sum(ws.values()) > 0 else "boarding"
                if basis == "boarding": ws = {st: ex[y][(st, t)][1] for st in sts}
                tot = sum(ws.values()) or 1
                for st in sts:
                    e, fb, c = ex[y][(st, t)]
                    f = feeders.setdefault(st, {"gu": gu, "lines": lines.get(st, []), "lat": (stations.get(st) or {}).get("lat"), "lng": (stations.get(st) or {}).get("lng"), "weight_basis": basis, "by_year": {}})
                    fy = f["by_year"].setdefault(y, {"attributed": {}, "boarding_fest": {}, "boarding_ctrl": {}, "excess": {}})
                    fy["attributed"][t] = round(sub_h[t] * ws[st] / tot); fy["boarding_fest"][t] = fb; fy["boarding_ctrl"][t] = round(c); fy["excess"][t] = round(e)
        xval[y] = {"seoul_origin_subway_inflow": round(seoul_sub_in), "positive_excess_boarding_10_19": round(excess_pos),
                   "ratio": round(excess_pos / seoul_sub_in, 2) if seoul_sub_in else None,
                   "note": "서울 전 역 양수 초과 승차(대조 토요일 대비) ÷ 서울 출발 지하철 유입. 1 근처면 초과분이 대체로 축제 유입, 크게 넘으면 타 요인 혼입. 귀속은 구 단위 OD 총량으로 제약하고 가중치는 2년 연속 초과만 인정"}
    for st, f in feeders.items():
        f["attributed_total"] = {y: sum(f["by_year"][y]["attributed"].values()) for y in f["by_year"]}
        f["attributed_mean"] = round(statistics.mean(f["attributed_total"].values()))
        f["excess_ratio_mean"] = round(statistics.mean(
            (sum(f["by_year"][y]["boarding_fest"].values()) / max(1, sum(f["by_year"][y]["boarding_ctrl"].values()))) for y in f["by_year"]), 2)
    feeders = dict(sorted(feeders.items(), key=lambda x: -x[1]["attributed_mean"]))
    total_attr = sum(f["attributed_mean"] for f in feeders.values())
    for f in feeders.values(): f["share_of_seoul"] = round(f["attributed_mean"] / total_attr, 4) if total_attr else None

    # ── 2026 사전 예측 (출발지 회랑 구성 기반) ──
    print("5/5 2026 출구 예측", flush=True)
    per_year = {}
    for y in DAYS:
        cin, cout = collections.Counter(), collections.Counter()
        for (k, t), v in od[y][0].items():
            if t in IN_HOURS: cin[origins[k]["corridor"]] += v
        for (k, t), v in od[y][1].items():
            if t >= 20: cout[origin_key_to_corridor(k, origins)] += v
        s = sum(cin.values()); dirs = {c: round(v / s, 4) for c, v in cin.items()}
        so = sum(cout.values()); dirs_out = {c: round(v / so, 4) for c, v in cout.items()}
        out_curve = {t: v for (k, t), v in _sum_by_hour(od[y][1]).items()}
        # 유출 지하철 비중: 도착지별(2025 수단) 가중 평균
        wsum = sum(v for (k, t), v in od[y][1].items() if t >= 20)
        sub_out = sum(v * share_out.get(k, overall_in) for (k, t), v in od[y][1].items() if t >= 20) / wsum if wsum else overall_in
        curve, exits = exit_forecast(out_curve, dirs, round(sub_out, 4))
        _, exits_ob = exit_forecast(out_curve, dirs_out, round(sub_out, 4))
        per_year[y] = {"direction_share_from_origin": dirs, "direction_share_outflow_dest": dirs_out, "subway_share_out": round(sub_out, 4),
                       "outflow_shifted": curve, "exits": exits, "exits_outflow_basis": exits_ob}
    exits_out = collections.OrderedDict()
    for st in N.CAP:
        exits_out[st] = {}
        for h in (19, 20, 21, 22, 23):
            vals = [per_year[y]["exits"][st][h] for y in DAYS]
            loads = [v["load"] for v in vals if v["load"] is not None]
            loads_all = loads + [per_year[y]["exits_outflow_basis"][st][h]["load"] for y in DAYS if per_year[y]["exits_outflow_basis"][st][h]["load"] is not None]
            exits_out[st][str(h)] = {
                "load": round(statistics.mean(loads), 2) if loads else None, "load_lo": round(min(loads_all), 2) if loads_all else None, "load_hi": round(max(loads_all), 2) if loads_all else None,
                "demand": round(statistics.mean(v["demand"] for v in vals)), "capacity": N.CAP[st],
                "wait_min": round(statistics.mean(v["wait_min"] for v in vals if v["wait_min"] is not None)) if loads else None,
                "closed": vals[0]["closed"], "estimated_capacity": st in N.ESTIMATED,
                "by_year_origin_basis": {y: per_year[y]["exits"][st][h]["load"] for y in DAYS},
                "by_year_outflow_basis": {y: per_year[y]["exits_outflow_basis"][st][h]["load"] for y in DAYS}}
    ranking = {str(h): sorted([(st, v[str(h)]["load"], v[str(h)]["wait_min"]) for st, v in exits_out.items() if not v[str(h)]["closed"]], key=lambda x: (x[1], x[2])) for h in (19, 20, 21, 22, 23)}
    outflow_forecast = {str(h): round(statistics.mean(per_year[y]["outflow_shifted"][h] for y in DAYS)) for h in (19, 20, 21, 22, 23)}

    gen = datetime.datetime.now().isoformat(timespec="seconds")
    fo = {"generated": gen, "method": "src/backtrack.py (모듈 docstring)", "festival_days": DAYS, "control_saturdays": CONTROL, "inflow_hours": IN_HOURS,
          "sources": {"od": "OA-22300", "mode": "OA-22657 (2025-09-27 만, 수단코드 6=지하철 추정)", "subway": "OA-12921 (1~8호선)", "stations": "StationAdresTelno + subwayStationMaster"},
          "inflow_total_10_19": {y: round(v) for y, v in tot_in.items()}, "subway_share_in_overall_2025": overall_in,
          "origins": origins, "symmetry_inflow_origin_vs_outflow_dest": symmetry,
          "feeders_seoul": feeders, "feeder_crossval": xval, "stations_outside_seoul_excluded": unmatched,
          "notes": ["cnt 는 KT 추정치 — 비율·순위 용도", "역 귀속은 구 단위 지하철 유입을 초과 승차 비율로 배분한 추정 — 실제 승차역 데이터 아님",
                    "경기·인천 출발지는 서울교통공사 승하차 데이터 밖 — 시군 단위, 진입역 미상", "2024 지하철 비중은 2025 수단 OD 를 적용"]}
    ef = {"generated": gen, "method": "src/backtrack.py — 출발지 회랑 구성 × 유출곡선(+40분) × 지하철 비중 × 회랑→역 배정 ÷ 용량, 연도별 계산 후 2년 평균·범위",
          "alpha": 1.0, "alpha_reason": "사전 예측(2024·2025 출발지 구성 기반) — 당일 보정 전",
          "outflow_forecast": outflow_forecast, "outflow_baseline": outflow_forecast,
          "outflow_by_year": {y: {str(h): v for h, v in per_year[y]["outflow_shifted"].items()} for y in DAYS},
          "direction_share": {c: round(statistics.mean(per_year[y]["direction_share_from_origin"].get(c, 0) for y in DAYS), 4) for c in N.ASSIGN},
          "direction_basis": "inflow_origin", "direction_share_by_year": {y: per_year[y]["direction_share_from_origin"] for y in DAYS},
          "direction_share_outflow_basis": {c: round(statistics.mean(per_year[y]["direction_share_outflow_dest"].get(c, 0) for y in DAYS), 4) for c in N.ASSIGN},
          "subway_share": round(statistics.mean(per_year[y]["subway_share_out"] for y in DAYS), 4),
          "show_end_2026": "21:10", "show_shift_min": N.SHIFT_MIN,
          "exits": exits_out, "ranking_by_hour": ranking,
          "closures": [{"exit": "여의나루(5)", "hours": [20, 21], "basis": "2026 공식 공지: 임시 통제 20:40~21:40"}],
          "band_note": "load = 출발지 기준 2년 평균. load_lo/hi = {2024,2025}×{출발지 기준, 유출 도착지 기준} 4회 계산의 최소/최대 (신뢰구간 아님). 용량 추정 오차는 미포함",
          "notes": ["유출 곡선 +40분 이동(쇼 종료 20:30→21:10)", "도달 지연 40/60 추정", "9호선·도보·1호선 합산 용량은 추정(estimated_capacity)", "KT cnt 는 추정치 — 비율·순위 용도"]}
    (DER / "feeder_origin.json").write_text(json.dumps(fo, ensure_ascii=False, indent=1), encoding="utf-8")
    (DER / "exit_forecast_2026.json").write_text(json.dumps(ef, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 요약 ──
    print("\n출발지 상위 12 (유입 비중 2년 평균 · 지하철 비중 2025 · 회랑)")
    for k, v in list(origins.items())[:12]:
        print(f"  {k:8s} {100*v['share_mean']:5.1f}%  지하철 {v['subway_share_2025'] if v['subway_share_2025'] is not None else '-':<6} {v['corridor']}")
    print("\n유입 출발 회랑 vs 유출 20시~ 도착 회랑 (2025, %p 차이)")
    for c, v in symmetry["2025"].items(): print(f"  {c:4s} in {100*v['inflow_origin']:5.1f}  out {100*v['outflow_dest']:5.1f}  Δ{v['diff_pp']:+.1f}")
    print("\n서울 피더 역 상위 15 (귀속 여의도행 승차 10~19시, 2년 평균 · 축제일/평시 승차 배율)")
    for st, f in list(feeders.items())[:15]:
        print(f"  {st:12s} {f['gu']:4s} {'/'.join(f['lines']):10s} {f['attributed_mean']:6,d}  ({100*f['share_of_seoul']:4.1f}%)  x{f['excess_ratio_mean']}")
    print("\n교차검증", json.dumps(xval, ensure_ascii=False))
    if unmatched: print("서울 밖 역(귀속 제외)", len(unmatched), unmatched[:15])
    print("\n2026 출구 부하율 (평균 [2년 범위])")
    for h in ("20", "21", "22"):
        print(f"  {h}시:", ", ".join(f"{st} {v:.2f}[{exits_out[st][h]['load_lo']:.2f}-{exits_out[st][h]['load_hi']:.2f}]" for st, v, w in ranking[h]))
    print("\n→", DER / "feeder_origin.json", "·", DER / "exit_forecast_2026.json")


def _sum_by_hour(counter):
    out = collections.Counter()
    for (k, t), v in counter.items(): out[("*", t)] += v
    return out


def origin_key_to_corridor(k, origins):
    if k in origins: return origins[k]["corridor"]
    code = next((c for c, n in SIGUN.items() if n == k), None) or next((g for g in B.GU if B.GU[g] == k), None) or ("28000" if k == "인천" else "99999")
    return B.corridor(code)


if __name__ == "__main__":
    main()
