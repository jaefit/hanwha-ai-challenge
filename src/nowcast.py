#!/usr/bin/env python3
"""L2·L3·L4 나우캐스트: 오늘 수집 로그 + baseline.json → data/live/forecast_latest.json

  .venv/bin/python src/nowcast.py            # 1회 계산
  .venv/bin/python src/nowcast.py --date 20260905

L2 α(t)  = 여의나루 누적 하차(관측, citydata LIVE_SUB_PPLTN) / 축제일 2년 평균 누적 하차(같은 시각까지)
           여의나루는 19시부터 무정차라 α 는 19:00 이후 동결. 관측이 없으면 α=1.
L3 출구수요 = α × E_st(관측 초과 승차, exit_shares.json) × KT 유출곡선 형태(h) → 도달 지연.  (2026-08-29 정정: 회랑→역 배정표는 실측과 어긋나 참고용으로 강등)
L4 대기(분) = max(0, 수요 − 용량) / 용량 × 60.   용량 = 관측 최대 시간당 승차(1~8호선), 9호선은 추정(주석)
도달 지연 = 관람구역→출구 거리 ÷ Weidmann 밀도별 보행속도(CCTV 등급 연동). 쇼 종료 실제 시각: --show-end HH:MM 또는 data/live/show_end.txt
출처: data/derived/baseline.json (KT OD·서울교통공사), data/live/api_*.jsonl (서울 실시간 도시데이터)
"""
import json, sys, os, math, pathlib, datetime, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER, LIVE = ROOT / "data" / "derived", ROOT / "data" / "live"
BASE = json.loads((DER / "baseline.json").read_text(encoding="utf-8"))

# 축제일 여의나루 시간대별 하차 (2024-10-05 / 2025-09-27 평균, OA-12921). α 분모.
YEOUINARU_GTOFF_BASE = {12: 4300, 13: 5800, 14: 7900, 15: 10600, 16: 13700, 17: 15565, 18: 4018, 19: 36, 20: 24}
# 회랑 → 지하철 출구 배정 (topic-fireworks.md §5 L3). 값 = 회랑 지하철 수요 중 비중. 나머지는 버스·도보.
ASSIGN = {
    "서":   {"여의도(5)": 0.75, "신길(1·5)": 0.25},   # 2025 실적: 21시 신길 2.8k vs 여의도(5) 12.5k
    "북서": {"여의나루(5)": 0.50, "마포역 도보(마포대교)": 0.50},
    "북동": {"여의나루(5)": 0.70, "여의도(5)": 0.30},
    "남":   {"여의도(9)": 0.40, "샛강(9)": 0.35, "신길(1·5)": 0.25},
    "남동": {"여의도(9)": 0.55, "샛강(9)": 0.25, "국회의사당(9)": 0.20},
    "기타": {"여의도(5)": 0.50, "여의도(9)": 0.50},
}
CAP = {  # 시간당 처리 용량(명). 관측값은 baseline.subway_capacity_obs_max_per_hour, 9호선·도보는 추정(표기)
    "여의도(5)": BASE["subway_capacity_obs_max_per_hour"]["여의도"],
    "여의나루(5)": BASE["subway_capacity_obs_max_per_hour"]["여의나루"],
    "신길(1·5)": BASE["subway_capacity_obs_max_per_hour"]["신길"] * 2,   # 1호선 경부선 합산 추정 (line9_capacity.json 있으면 대체)
    "여의도(9)": 12000, "샛강(9)": 4000, "국회의사당(9)": 4000,          # 수기 추정 (line9_capacity.json 있으면 대체)
    "마포역 도보(마포대교)": 15000,                                        # 추정: 보행로 1차로 폭 기준
}
# 관측 출구 규모·비중 (src/exit_shares.py): E_st = 축제일 초과 승차, 2년 평균. 없으면 회랑 모드로 동작
_ES = DER / "exit_shares.json"
EXIT_SHARES = json.loads(_ES.read_text(encoding="utf-8")) if _ES.exists() else None
E_MEAN = {st: float(v) for st, v in EXIT_SHARES["E_mean"].items()} if EXIT_SHARES else None
# 교통카드 일별 승차비로 비례 추정한 9호선·신길 용량 (src/line9_capacity.py, OA-12914). 여전히 추정이라 ESTIMATED 유지
_L9 = DER / "line9_capacity.json"
CAP_BASIS = {}
if _L9.exists():
    for _st, _v in json.loads(_L9.read_text(encoding="utf-8")).get("capacity", {}).items():
        if _st in CAP: CAP[_st] = int(_v["value"]); CAP_BASIS[_st] = _v["basis"]
ESTIMATED = {"신길(1·5)", "여의도(9)", "샛강(9)", "국회의사당(9)", "마포역 도보(마포대교)"}
# 불꽃쇼 종료 시각 앵커. 베이스라인(2024·2025)은 19:20~20:30 진행 → 유출 피크 20시.
# 2026은 20:00~21:10(영국 20:00, 미국 20:20, 한국 ~20:40) → 종료가 +40분 늦다. 유출 곡선을 그만큼 뒤로 민다.
SHOW_END_BASE, SHOW_END_2026 = (20, 30), (21, 10)
SHIFT_MIN = (SHOW_END_2026[0] * 60 + SHOW_END_2026[1]) - (SHOW_END_BASE[0] * 60 + SHOW_END_BASE[1])
CLOSED = {("여의나루(5)", 20), ("여의나루(5)", 21)}   # 2026 공식 공지(hanwhafireworks.com/notice/6): 여의나루역 임시 통제 20:40~21:40. 2024·2025 실적은 19~20시대 하차 ≈0


# ── 쇼 종료 실제 시각(offset) — 우선순위: --show-end HH:MM > data/live/show_end.txt > 계획 21:10 (benchmark §4-5) ──
def show_end_actual(argv):
    if "--show-end" in argv:
        hh, mm = argv[argv.index("--show-end") + 1].split(":"); return (int(hh), int(mm)), "arg"
    fn = LIVE / "show_end.txt"
    if fn.exists():
        try:
            hh, mm = fn.read_text().strip().split(":"); return (int(hh), int(mm)), "file"
        except ValueError: pass
    return SHOW_END_2026, "planned"


def shift_for(show_end):
    return (show_end[0] * 60 + show_end[1]) - (SHOW_END_BASE[0] * 60 + SHOW_END_BASE[1])


# ── 도달 지연: 관람구역→출구 거리 ÷ 밀도별 보행속도 (Weidmann 1993 / Kladek 식), benchmark §4-2 ──
# 기존 40/60 상수는 구역 밀도 3명/m² 일 때의 결과와 같다(이벤트광장→여의도역 약 39분). CCTV 등급이 있으면 구역별로 바뀐다.
ZONES = {"마포대교 남단": (37.5310, 126.9345), "이벤트광장": (37.5290, 126.9330), "원효대교 방향": (37.5257, 126.9412), "63빌딩 앞": (37.5205, 126.9385), "여의도공원": (37.5268, 126.9245)}
EXIT_LL = {"여의나루(5)": (37.5271, 126.9327), "여의도(5)": (37.5222, 126.9238), "여의도(9)": (37.5206, 126.9262), "샛강(9)": (37.5172, 126.9287),
           "국회의사당(9)": (37.5281, 126.9174), "신길(1·5)": (37.5170, 126.9137), "마포역 도보(마포대교)": (37.5391, 126.9459)}
DETOUR = 1.3                 # 직선거리 → 보행 경로 계수 (추정)
DENSE_SEG_M = 300            # 출구 방향 첫 300m 는 구역 밀도로 걷는다 (추정)
STREET_DENSITY = 1.5         # 그 뒤 가로 밀도 명/m² (추정)
DENSITY_BY_LEVEL = {"여유": 1.5, "주의": 3.0, "경계": 4.0, "심각": 5.0}   # 서울시 3/4/5 기준의 대표값
DEFAULT_DENSITY = 3.0        # CCTV 없거나 신뢰 못 할 때 — 기존 40/60 과 동치
V_MIN = 0.15                 # 정체 하한 속도 m/s (추정: Kladek 식은 5명/m² 에서 0.04 까지 떨어짐)
MIN_COUNT_FOR_DENSITY = 20   # 밀도맵 count 가 이보다 작으면 등급을 구역 밀도에 쓰지 않는다 (오탐 방지)
ZONE_CAM_RADIUS_M = 500            # 마포대교남단 483m·원효대교남단 419m 포함 (구역 5곳 전부 카메라 1대 이상)


def kladek(rho):
    """Weidmann(1993) 속도-밀도: v0 1.34 m/s, 정체밀도 5.4 명/m², γ 1.913"""
    if rho <= 0: return 1.34
    return max(V_MIN, 1.34 * (1 - math.exp(-1.913 * (1 / rho - 1 / 5.4))))


def haversine_m(a, b):
    R = 6371000.0; p1, p2 = math.radians(a[0]), math.radians(b[0]); dp = p2 - p1; dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def travel_min(zone, exit_name, rho):
    L = haversine_m(ZONES[zone], EXIT_LL[exit_name]) * DETOUR
    l1 = min(DENSE_SEG_M, L)
    return (l1 / kladek(rho) + (L - l1) / kladek(STREET_DENSITY)) / 60


def arrival_split(T):
    """시간대 안 균등 출발 + T분 이동 → 같은(0)/다음(1)/다다음(2) 시간대 도착 비율"""
    k, f = divmod(max(0.0, T), 60); k = int(k)
    same = (60 - f) / 60
    return {k: same, k + 1: 1 - same}


def lag_table(zone_density=None):
    """{출구: {offset: 비율}} — 관람구역 5곳 균등 가중(추정), 구역 밀도는 {구역: 명/m²}"""
    zd = zone_density or {}; out = {}
    for ex in EXIT_LL:
        acc = collections.Counter()
        for z in ZONES:
            for off, fr in arrival_split(travel_min(z, ex, zd.get(z, DEFAULT_DENSITY))).items(): acc[off] += fr / len(ZONES)
        out[ex] = dict(acc)
    return out


def zone_density_from_cctv(date):
    """오늘 CCTV 로그의 캘리브레이션된 카메라별 최신 등급 → 500m 안 구역의 밀도(최대). 미캘리브레이션·저신뢰·count<20 은 무시."""
    fn = LIVE / f"cctv_{date}.jsonl"
    cams_fn = DER / "topis_yeouido_cams.json"
    if not fn.exists() or not cams_fn.exists(): return {}, {}
    cams = {c["camId"]: c for c in json.loads(cams_fn.read_text(encoding="utf-8"))}
    latest = {}
    for l in fn.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        r = json.loads(l)
        # 모델 입력 조건: 캘리브레이션된 카메라(ROI+roi_m2 → density 있음) · 신뢰도 ok · count≥20. 미캘리브레이션 카메라는 화면 참고용.
        if r.get("ok") and r.get("level") in DENSITY_BY_LEVEL and r.get("density") is not None and r.get("confidence", "ok") == "ok" and (r.get("count") or 0) >= MIN_COUNT_FOR_DENSITY: latest[r["cam_id"]] = r
    zd, used = {}, {}
    for cid, r in latest.items():
        c = cams.get(str(cid)) or cams.get(cid)
        if not c: continue
        for z, ll in ZONES.items():
            if haversine_m(ll, (c["lat"], c["lng"])) <= ZONE_CAM_RADIUS_M:
                d = DENSITY_BY_LEVEL[r["level"]]
                if d > zd.get(z, 0): zd[z] = d; used[z] = {"cam": r.get("name"), "level": r["level"], "ts": r.get("ts")}
    return zd, used


def compute_exits(total, dirs, sub_share, lags, hours=(19, 20, 21, 22, 23), station_totals=None):
    """출구별 시간대 수요·부하율·대기. total: {h: 유출 곡선(출발 기준)}, lags: lag_table() 결과.
    관측 모드(station_totals 있음, 2026-08-29 채택): 규모·분배 = 관측 초과 승차 E_st(exit_shares.json), KT 곡선은 시간 형태만.
      도착 형태 = Σ_off lag[st][off] × 곡선[h-off] 를 **그 역의 개방 시간대에서만** 정규화해 E_st 를 분배한다.
      통제 시간대 재배정은 하지 않는다 — 관측 E 자체가 통제 하의 행동(여의나루=해제 후 승차, 여의도(5)=우회 포함)이라 재배정하면 이중계산.
      통제 시간대 도착분은 그 역의 해제 후 첫 개방 시간대로 이월한다(2026: 여의나루 20~21시분 → 22시).
      (백테스트 2025: 재배정 방식은 여의나루 22시 2.6k vs 실측 9.6k, 개방시간 분배로 정정)
    회랑 모드(레거시·참고): 출발(st,h) = total[h] × Σ_d dirs[d]·sub_share·ASSIGN[d][st], 통제 시간대 여의나루 수요는 여의도(5)로 이관."""
    H = range(15, 25)
    demand_by = {}
    if station_totals is not None:
        tot = sum(total.get(h, 0) for h in H) or 1.0
        shape = {h: total.get(h, 0) / tot for h in H}
        for st in CAP:   # E_st 는 19~23시(hours)에서 잰 값 → 같은 창에서만 정규화·분배 (15~18시 출발분엔 배분하지 않음)
            arr = {h: sum(fr * shape.get(h - off, 0.0) for off, fr in lags.get(st, {0: 0.4, 1: 0.6}).items()) for h in H}
            # 통제 시간대 도착분은 해제 후 첫 개방 시간대로 이월 (2026-08-30 결정): 여의나루에 온 사람은 해제(21:40)를 기다렸다 바로 탄다
            # → 22시 수요에 합산. 근거: 해제 직후 시간대 승차 2024 2.3k·2025 5.8k(OA-12921). 비례 재분배(구 방식)는 19시를 부풀렸다.
            mass = {h: 0.0 for h in H}; carry = 0.0
            for h in sorted(hours):
                if (st, h) in CLOSED: carry += arr[h]
                else: mass[h] = arr[h] + carry; carry = 0.0
            tot_mass = sum(mass[h] for h in hours) or 1.0
            demand_by[st] = {h: station_totals.get(st, 0.0) * mass[h] / tot_mass for h in H}
    else:
        dep = {st: {h: 0.0 for h in H} for st in CAP}
        for h in H:
            for d, share in dirs.items():
                for st, w in ASSIGN.get(d, {}).items():
                    dep[st][h] += total.get(h, 0) * share * sub_share * w
        for st in CAP:
            demand_by[st] = {h: sum(fr * dep[st].get(h - off, 0.0) for off, fr in lags.get(st, {0: 0.4, 1: 0.6}).items()) for h in H}
        for h in H:                                   # 무정차 시간대엔 여의나루 수요를 여의도(5)로 이관 (회랑 모드만)
            for st in list(demand_by):
                if (st, h) in CLOSED: demand_by["여의도(5)"][h] += demand_by[st][h]; demand_by[st][h] = 0.0
    exits = collections.OrderedDict(); backlog = collections.Counter()
    for h in hours:
        for st in CAP:
            dem = demand_by[st].get(h, 0.0); cap = CAP[st]; closed = (st, h) in CLOSED
            backlog[st] = 0.0 if closed else max(0.0, backlog[st] + dem - cap)   # 시간대 넘어가는 누적 대기열
            exits.setdefault(st, {})[h] = {"demand": round(dem), "capacity": cap, "load": None if closed else round(dem / cap, 3),
                                          "backlog": round(backlog[st]), "wait_min": None if closed else round(backlog[st] / cap * 60),
                                          "closed": closed, "estimated_capacity": st in ESTIMATED}
    return exits


def latest_api(date):
    fn = LIVE / f"api_{date}.jsonl"
    if not fn.exists(): return {}, []
    rows = [json.loads(l) for l in fn.read_text(encoding="utf-8").splitlines() if l.strip()]
    city = {r["area"]: r for r in rows if r.get("kind") == "citydata" and "error" not in r}
    acdnt = [x for r in city.values() for x in (r.get("acdnt") or [])]
    dst = [x for r in city.values() for x in (r.get("dst_msg") or [])]
    return city, acdnt + dst


def alpha(city, now):
    park = city.get("여의도한강공원")
    if not park or not park.get("sub_live"): return 1.0, "관측 없음 → α=1"
    s = park["sub_live"]
    try: obs = (int(s["SUB_ACML_GTOFF_PPLTN_MIN"]) + int(s["SUB_ACML_GTOFF_PPLTN_MAX"])) / 2
    except Exception: return 1.0, "누적 하차 파싱 실패 → α=1"
    h = min(now.hour, 19); frac = 0 if now.hour >= 19 else now.minute / 60
    base = sum(v for k, v in YEOUINARU_GTOFF_BASE.items() if k < h) + YEOUINARU_GTOFF_BASE.get(h, 0) * frac
    if base < 1000: return 1.0, f"기준 누적이 작아 α 미정의({now:%H:%M}) → α=1"
    a = max(0.3, min(3.0, obs / base))
    return round(a, 3), f"여의나루 누적 하차 관측 {obs:,.0f} / 기준 {base:,.0f}"


def main():
    date = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else datetime.datetime.now().strftime("%Y%m%d")
    now = datetime.datetime.now()
    city, alerts = latest_api(date)
    a, why = alpha(city, now)
    out_base = {int(k): v for k, v in BASE["outflow_by_hour_mean"].items()}
    # 방향·지하철 비중: 역추적 사전 예측표(src/backtrack.py, 유입 출발지 기준)가 있으면 그것을, 없으면 baseline(유출 도착지 기준)
    prior_fn = DER / "exit_forecast_2026.json"
    if prior_fn.exists():
        PRIOR = json.loads(prior_fn.read_text(encoding="utf-8")); dirs = PRIOR["direction_share"]; sub_share = PRIOR["subway_share"]; dir_basis = "backtrack:inflow_origin"
    else:
        dirs = BASE["outflow_direction_share_mean"]; sub_share = BASE["outflow_mode_share_20250927"].get("지하철", 0.45); dir_basis = "baseline:outflow_dest"
    hours = [19, 20, 21, 22, 23]
    show_end, show_src = show_end_actual(sys.argv); shift = shift_for(show_end)
    # 베이스라인 유출 곡선을 shift 분 만큼 뒤로 민다 (시간대 선형 배분)
    f = (shift % 60) / 60; k = shift // 60
    shifted = {h: (1 - f) * out_base.get(h - k, 0) + f * out_base.get(h - k - 1, 0) for h in range(15, 25)}
    total = {h: a * shifted.get(h, 0) for h in range(15, 25)}
    zd, zd_src = zone_density_from_cctv(date); lags = lag_table(zd)
    if E_MEAN:   # 관측 모드: 규모 = α × 2년 평균 초과 승차, 형태 = KT 곡선(α 무관하게 정규화됨)
        station_totals = {st: a * E_MEAN.get(st, 0.0) for st in CAP}; demand_basis = "observed_station_excess (exit_shares.json) × α"
    else:
        station_totals = None; demand_basis = "corridor ASSIGN × KT outflow × subway_share"
    ex_int = compute_exits(total, dirs, sub_share, lags, hours, station_totals=station_totals)
    prior_exits = PRIOR.get("exits", {}) if prior_fn.exists() else {}
    exits = collections.OrderedDict()
    for st, byh in ex_int.items():
        exits[st] = {}
        for h, v in byh.items():
            v = dict(v); v["load"] = None if v["load"] is None else round(v["load"], 2)
            pe = (prior_exits.get(st) or {}).get(str(h)) or {}
            if v["load"] is not None:
                if pe.get("load") and pe.get("load_lo") is not None:      # 사전 예측표의 밴드 비율(버퍼 포함)을 α 스케일에 그대로 적용
                    v["load_lo"] = round(v["load"] * pe["load_lo"] / pe["load"], 2); v["load_hi"] = round(v["load"] * pe["load_hi"] / pe["load"], 2)
                else:
                    v["load_lo"] = round(v["load"] * 0.9, 2); v["load_hi"] = round(v["load"] * 1.1, 2)   # MARTA 관행 ±MAPE≈10%
            exits[st][str(h)] = v
    ranking = {}
    for h in hours:
        opens = [(st, v[str(h)]["load"], v[str(h)]["wait_min"]) for st, v in exits.items() if not v[str(h)]["closed"]]
        ranking[str(h)] = sorted(opens, key=lambda x: (x[1], x[2]))
    seoul_fcst = (city.get("여의도한강공원") or {}).get("fcst", [])
    result = {
        "ts": now.isoformat(timespec="seconds"), "date": date, "alpha": a, "alpha_reason": why,
        "outflow_forecast": {str(h): round(total[h]) for h in hours},
        "outflow_baseline": {str(h): out_base[h] for h in hours},
        "show_shift_min": shift, "show_end_2026": "21:10", "show_end_actual": f"{show_end[0]:02d}:{show_end[1]:02d}", "show_end_source": show_src, "show_end_baseline": "20:30",
        "lag_model": {"method": "구역→출구 거리 ÷ Weidmann 밀도별 속도, 첫 300m 구역 밀도·이후 1.5명/m²(추정), 구역 균등 가중(추정)", "zone_density": zd, "zone_density_source": zd_src,
                      "lag_by_exit": {st: {str(o): round(fr, 3) for o, fr in v.items()} for st, v in lags.items()}},
        "direction_share": dirs, "subway_share": sub_share, "direction_basis": dir_basis,
        "exits": exits, "ranking_by_hour": ranking, "capacity_basis": CAP_BASIS,
        "demand_basis": demand_basis, "station_totals": {st: round(v) for st, v in (station_totals or {}).items()}, "exit_share_mean": (EXIT_SHARES or {}).get("share_mean"),
        "closures": [{"exit": "여의나루(5)", "hours": [20, 21], "basis": "2026 공식 공지: 임시 통제 20:40~21:40 (현장 공지). 2024·2025 실적: 19~20시대 하차 ≈0"}, {"road": "여의동로", "hours": [15, 24], "basis": "2026 공식 공지: 마포대교 남단~63빌딩 전면 통제"}, {"road": "원효대교", "basis": "2026 공식 공지: 설치·행사·철수 일정별 전면 통제"}],
        "alerts_live": alerts[:10],
        "live_snapshot": {k: {"congest": v.get("congest"), "ppltn": [v.get("ppltn_min"), v.get("ppltn_max")], "ts": v.get("ppltn_time"), "road": v.get("road_idx")} for k, v in city.items()},
        "seoul_fcst_snapshot": seoul_fcst,
        "notes": ["유출 곡선은 불꽃쇼 종료 앵커 기준 +40분 이동(2025 20:30 → 2026 21:10)", "용량 중 estimated_capacity=true 는 추정치(9호선·도보·1호선 합산)", "역 도달 지연 = 거리÷밀도별 속도(Weidmann). CCTV 등급 없으면 구역 밀도 3명/m² 가정(≈기존 40/60)", "load_lo/hi = 사전 예측표 밴드 비율 × α (±10% 버퍼 포함)", "대기열은 시간대를 넘어 누적(backlog)", "α 는 여의나루 누적 하차 기준, 19:00 이후 동결", "cnt 기반 수치는 KT 추정치 — 비율·순위 용도"],
    }
    (LIVE / "forecast_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"α={a} ({why})"); print("유출 예측:", result["outflow_forecast"])
    for h in ("20", "21", "22"):
        print(f"{h}시 출구 랭킹(부하율):", ", ".join(f"{st} {l:.2f}{'' if not w else f'/{w}분'}" for st, l, w in ranking[h]))


if __name__ == "__main__":
    main()
