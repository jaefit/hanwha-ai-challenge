#!/usr/bin/env python3
"""L2·L3·L4 나우캐스트: 오늘 수집 로그 + baseline.json → data/live/forecast_latest.json

  .venv/bin/python src/nowcast.py            # 1회 계산
  .venv/bin/python src/nowcast.py --date 20260905
  .venv/bin/python src/nowcast.py --out /tmp/fc.json   # 라이브 forecast_latest.json 을 건드리지 않고 산출 (테스트용)

L2 α     = 출구 수요 규모 배율. 격자 사후분포(61점, 1/3~3, 사전 LogNormal(0,0.25))를 당일 관측 2종으로 갱신(2026-08-30 T1c):
           O1 도착측 = 여의나루(여의도한강공원 핫스팟) 30분 하차 증분 vs α×2년 평균 증분 (12~19시, σ 15%+범위)
           O2 귀가측 = 여의도 핫스팟(9역 합산) 30분 승차 vs c×(α×모델 초과 승차 + 평시 승차) (19시~, σ 20%, c=커버리지 추정)
           매 틱 당일 로그 전체를 다시 계산(재시작 무관). 관측 0건이면 사전분포 → α=1, 밴드 0.73~1.38.
L3 출구수요 = α × E_st(관측 초과 승차, exit_shares.json) × KT 유출곡선 형태(h) → 도달 지연.  (2026-08-29 정정: 회랑→역 배정표는 실측과 어긋나 참고용으로 강등)
L4 대기(분) = max(0, 수요 − 용량) / 용량 × 60.   용량 = 관측 최대 시간당 승차(1~8호선), 9호선은 추정(주석)
도달 지연 = 관람구역→출구 거리 ÷ Weidmann 밀도별 보행속도(CCTV 등급 연동). 쇼 종료 실제 시각: --show-end HH:MM 또는 data/live/show_end.txt
출처: data/derived/baseline.json (KT OD·서울교통공사), data/live/api_*.jsonl (서울 실시간 도시데이터)
"""
import json, re, sys, os, math, pathlib, datetime, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER, LIVE = ROOT / "data" / "derived", ROOT / "data" / "live"
BASE = json.loads((DER / "baseline.json").read_text(encoding="utf-8"))

# 축제일 여의나루 시간대별 하차 (2024-10-05 / 2025-09-27 평균, OA-12921). α 분모.
YEOUINARU_GTOFF_BASE = {12: 4300, 13: 5800, 14: 7900, 15: 10600, 16: 13700, 17: 15565, 18: 4018, 19: 36, 20: 24}


def o1_base_inc(h, half, shift):
    """(시, 30분 구간) 창의 기준 30분 하차. 2026-09-02 H7 정정 — 쇼 종료가 shift 분 늦으면 도착도 그만큼 늦다.
    유출 곡선은 이미 shift 만큼 밀었는데(main) O1 분모만 2024·2025 시각 그대로여서 오후 내내 α<1 로 읽혔다.
    기준선의 '시간대 안 균등' 가정은 그대로 두고, 관측 창 [t0, t0+30분) 을 shift 만큼 앞당겨 그 구간의 기준 하차를 적분한다.
    shift=0 이면 두 반시간 모두 예전과 같은 '그 시간대 값 ÷ 2'."""
    t0 = h + 0.5 * half - shift / 60.0
    t1 = t0 + 0.5
    total, hh = 0.0, int(math.floor(t0))
    while hh < t1:
        lo, hi = max(t0, hh), min(t1, hh + 1)
        if hi > lo: total += YEOUINARU_GTOFF_BASE.get(hh, 0) * (hi - lo)
        hh += 1
    return total


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
BASE6 = {int(h): float(v) for h, v in (EXIT_SHARES or {}).get("baseline_boarding_by_hour_6exits", {}).items()}   # 지하철 출구 6개 평시 토요일 시간대 승차 합
# 출구별 평시 토요일 시간대 승차. CAP 은 축제일 **총** 승차의 시간당 최댓값이므로 부하율 분자에도 평시가 들어가야 단위가 맞는다 (결함 H9, 2026-09-03)
BASE_EXIT = {st: {int(h): float(v) for h, v in byh.items()} for st, byh in (EXIT_SHARES or {}).get("baseline_boarding_by_hour_by_exit", {}).items()}
# ── α 데이터동화 상수 (T1c) ──
ALPHA_GRID = [3.0 ** ((i - 30) / 30) for i in range(61)]   # 로그 등간격 61점, 1/3 ~ 3, 중앙(i=30) = 1.0
PRIOR_SIGMA = 0.25            # LogNormal(0, σ): p10/p90 = 0.73/1.38 ≈ 2년 관측 밴드 폭
O1_REL_SIGMA, O2_REL_SIGMA = 0.15, 0.20
O1_MIN_BASE_INC = 200         # 30분 기준 증분이 이보다 작은 창은 정보 없음(새벽·통제 후)
COVERAGE_FALLBACK, COVERAGE_CLAMP = 1.3, (0.8, 3.0)   # 여의도 핫스팟 9역 ÷ 우리 6출구 커버리지. 당일 14~17시로 추정, 실패 시 고정값
COVERAGE_HOURS = range(14, 18)   # 14·15·16·17시 (2026-09-01 red team H5: 코드가 14~16 만 봐 문서·보고서 §3.4 와 어긋났다)
COVERAGE_MAX_SPREAD = 0.3        # (최대−최소)÷중앙값. c 는 α 에 반비례하므로 창끼리 이만큼 넘게 흩어지면 중앙값을 믿지 않고 고정값
SUBWAY_EXITS = ("여의도(5)", "여의나루(5)", "신길(1·5)", "여의도(9)", "샛강(9)", "국회의사당(9)")
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
# 2026 공식 공지(hanwhafireworks.com/notice/6): 여의나루역 임시 통제 20:40~21:40. 2024·2025 실적은 19~20시대 하차 ≈0.
# 2026-09-05 19:10 hotfix: 당일 실측 — 30분 하차가 18:10 8,300 → 18:35 1,100, 승차 30 으로 붕괴 = 조기 무정차(현장 확인). 19시 추가.
CLOSED = {("여의나루(5)", 19), ("여의나루(5)", 20), ("여의나루(5)", 21)}


# ── 쇼 종료 실제 시각(offset) — 우선순위: --show-end HH:MM > data/live/show_end.txt > 계획 21:10 (benchmark §4-5) ──
# 2026-09-01 red team C4: 값 누락·콜론 누락은 크래시였고, 형식 오류는 조용히 계획값으로 떨어져 "기입했는데 반영 안 됨"
# 을 알 수 없었으며, '25:99' 는 통과해 유출 곡선을 369분 밀었다. 파싱·범위 검증 + 결과를 source 로 드러낸다.
_HHMM = re.compile(r"^(\d{1,2}):([0-5]\d)$")
SHOW_END_MIN, SHOW_END_MAX = 19 * 60, 24 * 60   # 쇼 종료가 놓일 수 있는 범위 (공지 21:10 기준 ±)


def parse_show_end(s):
    """'HH:MM' → (시, 분). 형식·범위를 벗어나면 None."""
    m = _HHMM.match((s or "").strip())
    if not m: return None
    hh, mm = int(m.group(1)), int(m.group(2))
    return (hh, mm) if SHOW_END_MIN <= hh * 60 + mm <= SHOW_END_MAX else None


def show_end_actual(argv):
    if "--show-end" in argv:
        i = argv.index("--show-end") + 1
        se = parse_show_end(argv[i]) if i < len(argv) else None
        if se is None:
            print(f"오류: --show-end 는 HH:MM (19:00~24:00) 이어야 한다. 예: --show-end 21:25", file=sys.stderr)
            raise SystemExit(2)
        return se, "arg"
    fn = LIVE / "show_end.txt"
    if fn.exists():
        raw = fn.read_text(encoding="utf-8", errors="replace")
        se = parse_show_end(raw)
        if se: return se, "file"
        print(f"경고: {fn} 내용 {raw.strip()!r} 은 HH:MM (19:00~24:00) 형식이 아니다 — 계획값 "
              f"{SHOW_END_2026[0]:02d}:{SHOW_END_2026[1]:02d} 으로 진행한다. 다시 기입할 것.", file=sys.stderr)
        return SHOW_END_2026, "planned_invalid_file"
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
CCTV_MAX_AGE_MIN = 30              # 2026-09-02 M10: 나이 컷이 없어 낮에 조건을 맞춘 등급이 밤까지 남았다


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


def zone_density_from_cctv(date, now=None):
    """오늘 CCTV 로그의 캘리브레이션된 카메라별 최신 등급 → 500m 안 구역의 밀도(최대).
    미캘리브레이션·저신뢰·count<20·CCTV_MAX_AGE_MIN 분 넘게 지난 관측은 무시."""
    now = now or datetime.datetime.now()
    fn = LIVE / f"cctv_{date}.jsonl"
    cams_fn = DER / "topis_yeouido_cams.json"
    if not fn.exists() or not cams_fn.exists(): return {}, {}
    cams = {c["camId"]: c for c in json.loads(cams_fn.read_text(encoding="utf-8"))}
    latest = {}
    for l in fn.read_text(encoding="utf-8").splitlines():
        if not l.strip(): continue
        r = json.loads(l)
        # 모델 입력 조건: 캘리브레이션된 카메라(ROI+roi_m2 → density 있음) · 신뢰도 ok · count≥20. 미캘리브레이션 카메라는 화면 참고용.
        if not (r.get("ok") and r.get("level") in DENSITY_BY_LEVEL and r.get("density") is not None
                and r.get("confidence", "ok") == "ok" and (r.get("count") or 0) >= MIN_COUNT_FOR_DENSITY): continue
        try: age = (now - datetime.datetime.fromisoformat(r["ts"])).total_seconds() / 60
        except Exception: continue
        if age > CCTV_MAX_AGE_MIN: continue        # 묵은 등급을 현재 밀도로 쓰지 않는다 (M10)
        latest[r["cam_id"]] = r
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
            base = 0.0 if closed else BASE_EXIT.get(st, {}).get(h, 0.0)   # 평시 승객도 같은 개찰구·열차를 쓴다. 통제 시간대엔 열차가 안 서므로 0
            tot = dem + base                                              # 용량과 비교할 도착 총량 (demand 는 초과분 그대로 둔다 — evaluate·backtest 가 그 단위를 쓴다)
            backlog[st] = 0.0 if closed else max(0.0, backlog[st] + tot - cap)   # 시간대 넘어가는 누적 대기열
            exits.setdefault(st, {})[h] = {"demand": round(dem), "baseline": round(base), "demand_total": round(tot), "capacity": cap,
                                          "load": None if closed else round(tot / cap, 3),
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


SOURCE_MAX_AGE_MIN = 15   # 정상 틱 5분의 3배 — publish.forecast_stale_min 과 같은 기준(M9)


def source_freshness(records, now, kinds=("citydata", "subway")):
    """종류별 마지막 **성공** 레코드의 나이. 오류 레코드는 세지 않는다.

    왜 필요한가(결함 H10, 2026-09-03): 수집이 끊겨도 nowcast 는 계속 돌아 새 ts 로 발행되고,
    화면은 발행 시각으로 신선도를 재서 "3분 전 · 실시간"이라고 말했다. 파일 mtime 도 오류 레코드로
    갱신돼 워치독을 속인다. 성공 레코드의 시각만이 수집기가 살아 있다는 증거다.
    last_ok=None 은 '아직 한 번도 못 받음'(수집 시작 전)이고 stale 과 구분해 쓴다."""
    out = {}
    for kind in kinds:
        ok = [r["ts"] for r in records if r.get("kind") == kind and "error" not in r and r.get("ts")]
        if not ok:
            out[kind] = {"last_ok": None, "age_min": None, "stale": False}   # 아직 시작 전 — '끊김' 과 다르다
            continue
        last = max(ok)
        try: age = round((now - datetime.datetime.fromisoformat(last)).total_seconds() / 60)
        except (ValueError, TypeError): age = None
        out[kind] = {"last_ok": last, "age_min": age, "stale": age is None or age > SOURCE_MAX_AGE_MIN}
    return out


def _load_records(date):
    fn = LIVE / f"api_{date}.jsonl"
    if not fn.exists(): return []
    return [json.loads(l) for l in fn.read_text(encoding="utf-8").splitlines() if l.strip()]


def _win(records, area):
    """(시, 30분 구간) 별 마지막 레코드. 30분 창 = 그 레코드 시각 직전 30분(수집 주기 5분 → 최대 5분 어긋남, 표기)."""
    out = {}
    for r in records:
        if r.get("kind") != "citydata" or r.get("area") != area or "error" in r or not r.get("sub_live"): continue
        try: t = datetime.datetime.fromisoformat(r["ts"])
        except Exception: continue
        key = (t.hour, t.minute // 30)
        if key not in out or t > out[key][0]: out[key] = (t, r["sub_live"])
    return out


def _mid(s, key):
    try: lo, hi = float(s[f"{key}_MIN"]), float(s[f"{key}_MAX"])
    except (KeyError, TypeError, ValueError): return None
    return (lo + hi) / 2, (hi - lo) / 2


def _observations(records, excess1_by_hour, base_by_hour, shift=0):
    """당일 로그 → 우도 항. obs = [(y, A, B, rel_sigma, abs_sigma, kind)], pred(α) = A·α + B, σ = rel·pred + abs.
    O1 여의도한강공원(=여의나루 1역) 30분 하차: A = 2년 평균 30분 증분(쇼 시프트 반영, o1_base_inc), B = 0. 창 종료 ≤ 19:00.
    O2 여의도 핫스팟(9역 합산) 30분 승차: A = c·초과(α=1)/2, B = c·평시/2. 창 시작 ≥ 19:00.
    c(커버리지) = 당일 14~17시 관측 30분 승차 ÷ 우리 6출구 평시 30분 승차 의 중앙값 (3창 이상), 없으면 COVERAGE_FALLBACK."""
    obs = []; park = _win(records, "여의도한강공원"); ydo = _win(records, "여의도")
    n1 = 0
    for (h, half), (t, s) in sorted(park.items()):
        if h > 18 or h < 12: continue
        base_inc = o1_base_inc(h, half, shift)
        if base_inc < O1_MIN_BASE_INC: continue
        m = _mid(s, "SUB_30WTHN_GTOFF_PPLTN")
        if not m: continue
        obs.append((m[0], base_inc, 0.0, O1_REL_SIGMA, m[1], "alighting")); n1 += 1
    cs = []
    for (h, half), (t, s) in sorted(ydo.items()):
        if h in COVERAGE_HOURS and base_by_hour.get(h):
            m = _mid(s, "SUB_30WTHN_GTON_PPLTN")
            if m: cs.append(m[0] / (base_by_hour[h] / 2))
    med = sorted(cs)[len(cs) // 2] if len(cs) >= 3 else None   # 3창 미만이면 산포를 말할 수 없다
    spread = (max(cs) - min(cs)) / med if med else None
    if len(cs) < 3:
        c = COVERAGE_FALLBACK; c_basis = "fallback"
    elif spread is None or spread > COVERAGE_MAX_SPREAD:
        c = COVERAGE_FALLBACK; c_basis = "fallback_spread"   # 창끼리 어긋남 → 관측 이상으로 보고 고정값
    else:
        c = max(COVERAGE_CLAMP[0], min(COVERAGE_CLAMP[1], med)); c_basis = "same_day_14_17h"
    n2 = 0
    for (h, half), (t, s) in sorted(ydo.items()):
        if h < 19 or h > 23: continue
        m = _mid(s, "SUB_30WTHN_GTON_PPLTN")
        if not m: continue
        A = c * excess1_by_hour.get(h, 0.0) / 2; B = c * base_by_hour.get(h, 0.0) / 2
        if A + B <= 0: continue
        obs.append((m[0], A, B, O2_REL_SIGMA, m[1], "boarding")); n2 += 1
    meta = {"n_obs": {"alighting": n1, "boarding": n2}, "coverage_c": round(c, 3), "coverage_basis": c_basis, "coverage_samples": len(cs),
            "coverage_spread": None if spread is None else round(spread, 3),
            "window_note": "30분 창 = 각 30분 구간 마지막 수집 레코드 직전 30분 (최대 5분 어긋남)"}
    return obs, meta


def assimilate(obs, prior_sigma=PRIOR_SIGMA, grid=ALPHA_GRID):
    """격자 사후분포. w(α) ∝ LogNormal 사전 × Π N(y; A·α+B, σ). 반환: alpha [p10,p50,p90], weights, edge_hit, n_obs."""
    # σ 는 α 무관 상수: rel × max(관측 y, α=1 예측 A+B) + abs. 예측(α) 기준이면 −ln σ 항이 작은 α 를 편애(테스트 0.91),
    # 관측만 기준이면 작은 y 한 건이 σ 를 줄여 과신(8/29 평시 로그: 1건으로 밴드 ±5%). 둘 중 큰 쪽이라 둘 다 막는다.
    sigs = [max(rel * max(y, A + B) + ab, 1.0) for y, A, B, rel, ab, kind in obs]
    logw = []
    for a in grid:
        lw = -0.5 * (math.log(a) / prior_sigma) ** 2
        for (y, A, B, rel, ab, kind), sig in zip(obs, sigs):
            lw += -0.5 * ((y - (A * a + B)) / sig) ** 2
        logw.append(lw)
    m = max(logw); w = [math.exp(x - m) for x in logw]; z = sum(w); w = [x / z for x in w]
    step = math.log(grid[1] / grid[0])   # 각 격자점 질량은 로그 공간에서 그 점을 중심으로 한 셀 [g/√r, g·√r] 에 균등 (끝점 귀속은 반 셀 편향)
    def q(p):
        c = 0.0
        for i, wi in enumerate(w):
            if c + wi >= p:
                f = (p - c) / wi if wi > 0 else 0.5
                return math.exp(math.log(grid[i]) + step * (f - 0.5))
            c += wi
        return grid[-1]
    imax = max(range(len(w)), key=lambda i: w[i])
    return {"alpha": [round(q(0.1), 3), round(q(0.5), 3), round(q(0.9), 3)], "weights": w, "edge_hit": imax in (0, len(w) - 1), "n_obs": len(obs), "grid_n": len(grid)}


def main():
    date = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else datetime.datetime.now().strftime("%Y%m%d")
    now = datetime.datetime.now()
    city, alerts = latest_api(date)
    records = _load_records(date)
    fresh = source_freshness(records, now)
    # 지하철 도착은 17~23시만 수집한다(collector_api.SUBWAY_HOURS) — 그 밖의 시간대에 '끊김'이라 말하면 늑대소년이 된다
    expected = ["citydata"] + (["subway"] if 17 <= now.hour <= 23 else [])
    degraded = sorted(k for k in expected if fresh.get(k, {}).get("stale"))
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
    zd, zd_src = zone_density_from_cctv(date); lags = lag_table(zd)
    # α 데이터동화: α=1 초과 수요(지하철 6출구 합)를 O2 예측항으로 쓰고, 당일 로그 전체로 사후분포 계산
    if E_MEAN:
        ex1 = compute_exits(shifted, dirs, sub_share, lags, hours, station_totals=E_MEAN)
        excess1 = {h: sum(ex1[st][h]["demand"] for st in SUBWAY_EXITS) for h in hours}
        obs, ometa = _observations(records, excess1, BASE6, shift=shift)
    else:
        obs, ometa = [], {"n_obs": {"alighting": 0, "boarding": 0}, "coverage_c": None, "coverage_basis": "n/a"}
    post = assimilate(obs)
    a = post["alpha"][1]
    why = (f"관측 {post['n_obs']}건(하차 {ometa['n_obs']['alighting']}·승차 {ometa['n_obs']['boarding']}) → α p50 {a} [{post['alpha'][0]}–{post['alpha'][2]}]"
           if post["n_obs"] else "관측 없음 → 사전분포 α=1 [0.73–1.38]")
    band_lo, band_hi = post["alpha"][0] / a, post["alpha"][2] / a
    total = {h: a * shifted.get(h, 0) for h in range(15, 25)}
    if E_MEAN:   # 관측 모드: 규모 = α × 2년 평균 초과 승차, 형태 = KT 곡선(α 무관하게 정규화됨)
        station_totals = {st: a * E_MEAN.get(st, 0.0) for st in CAP}; demand_basis = "observed_station_excess (exit_shares.json) × α"
    else:
        station_totals = None; demand_basis = "corridor ASSIGN × KT outflow × subway_share"
    ex_int = compute_exits(total, dirs, sub_share, lags, hours, station_totals=station_totals)
    exits = collections.OrderedDict()
    for st, byh in ex_int.items():
        exits[st] = {}
        for h, v in byh.items():
            v = dict(v); v["load"] = None if v["load"] is None else round(v["load"], 2)
            if v["load"] is not None:   # 밴드 = α 사후 p10/p90 비율 (관측 모드에서 load ∝ α). 관측 없으면 0.73~1.38, 관측 쌓이면 좁아짐
                v["load_lo"] = round(v["load"] * band_lo, 2); v["load_hi"] = round(v["load"] * band_hi, 2)
            exits[st][str(h)] = v
    ranking = {}
    for h in hours:
        opens = [(st, v[str(h)]["load"], v[str(h)]["wait_min"]) for st, v in exits.items() if not v[str(h)]["closed"]]
        ranking[str(h)] = sorted(opens, key=lambda x: (x[1], x[2]))
    seoul_fcst = (city.get("여의도한강공원") or {}).get("fcst", [])
    result = {
        "ts": now.isoformat(timespec="seconds"), "date": date, "alpha": a, "alpha_reason": why,
        # 2026-09-02 T7 드라이런: 관측 0건이면 α=1 은 측정값이 아니라 사전분포의 중앙값이다. 이 플래그가 없으면
        # docs/app/board.js 가 mode="live" 로 읽어 관람객 화면이 "실시간 반영 · α 1.00" 이라 말한다 (결함 M6).
        "prior": not post["n_obs"],
        # 수집기가 살아 있는지 — prior 와 다른 축이다. prior 는 '오늘 관측이 하나도 없다',
        # 이건 '방금까지 받고 있나'. α 는 낮 동안 쌓인 관측을 계속 쓰는 게 맞으므로 여기서 관측을 버리지 않는다 (H10)
        "data_freshness": fresh, "degraded_sources": degraded,
        "assimilation": {"method": "격자 사후분포 61점(1/3~3), 사전 LogNormal(0,0.25), 관측 O1 여의나루 30분 하차·O2 여의도 핫스팟 30분 승차", "grid_n": post["grid_n"],
                         "n_obs": ometa["n_obs"], "alpha": post["alpha"], "edge_hit": post["edge_hit"], "coverage_c": ometa.get("coverage_c"), "coverage_basis": ometa.get("coverage_basis"),
                         "coverage_samples": ometa.get("coverage_samples", 0), "coverage_spread": ometa.get("coverage_spread"), "window_note": ometa.get("window_note")},
        "outflow_forecast": {str(h): round(total[h]) for h in hours},
        "outflow_baseline": {str(h): out_base[h] for h in hours},
        "show_shift_min": shift, "show_end_2026": "21:10", "show_end_actual": f"{show_end[0]:02d}:{show_end[1]:02d}", "show_end_source": show_src, "show_end_baseline": "20:30",
        "lag_model": {"method": "구역→출구 거리 ÷ Weidmann 밀도별 속도, 첫 300m 구역 밀도·이후 1.5명/m²(추정), 구역 균등 가중(추정)", "zone_density": zd, "zone_density_source": zd_src,
                      "lag_by_exit": {st: {str(o): round(fr, 3) for o, fr in v.items()} for st, v in lags.items()}},
        "direction_share": dirs, "subway_share": sub_share, "direction_basis": dir_basis,
        "exits": exits, "ranking_by_hour": ranking, "capacity_basis": CAP_BASIS,
        "demand_basis": demand_basis, "station_totals": {st: round(v) for st, v in (station_totals or {}).items()}, "exit_share_mean": (EXIT_SHARES or {}).get("share_mean"),
        "closures": [{"exit": "여의나루(5)", "hours": [19, 20, 21], "basis": "2026 공식 공지: 임시 통제 20:40~21:40. 당일 실측(9/5 18:10~) 조기 무정차 → 19시 추가 (2026-09-05 19:10 hotfix)"}, {"road": "여의동로", "hours": [15, 24], "basis": "2026 공식 공지: 마포대교 남단~63빌딩 전면 통제"}, {"road": "원효대교", "basis": "2026 공식 공지: 설치·행사·철수 일정별 전면 통제"}],
        "alerts_live": alerts[:10],
        # role = core(여의도 3구역) · watch(강 건너 관람 명당) · feeder(유입 출발지). fcst 2칸 = 서울시 1·2시간 뒤 예보 → UI 추세 화살표
        "live_snapshot": {k: {"congest": v.get("congest"), "ppltn": [v.get("ppltn_min"), v.get("ppltn_max")], "ts": v.get("ppltn_time"), "road": v.get("road_idx"),
                              "role": v.get("role", "feeder"), "fcst": [{"t": f["t"], "lvl": f["lvl"], "min": f["min"], "max": f["max"]} for f in (v.get("fcst") or [])[:2]]} for k, v in city.items()},
        "seoul_fcst_snapshot": seoul_fcst,
        "notes": ["유출 곡선은 불꽃쇼 종료 앵커 기준 +40분 이동(2025 20:30 → 2026 21:10)", "용량 중 estimated_capacity=true 는 추정치(9호선·도보·1호선 합산)", "역 도달 지연 = 거리÷밀도별 속도(Weidmann). CCTV 등급 없으면 구역 밀도 3명/m² 가정(≈기존 40/60)", "load_lo/hi = α 사후분포 p10/p90 비율 (관측 없으면 0.73~1.38, 관측 쌓이면 축소)", "대기열은 시간대를 넘어 누적(backlog)", "α = 격자 사후 p50. O1 여의나루 30분 하차(12~19시, 기준선도 쇼 시프트만큼 이동)·O2 여의도 핫스팟 30분 승차(19시~, 커버리지 c 추정)", "cnt 기반 수치는 KT 추정치 — 비율·순위 용도"],
    }
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else LIVE / "forecast_latest.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"α={a} ({why})"); print("유출 예측:", result["outflow_forecast"])
    for h in ("20", "21", "22"):
        print(f"{h}시 출구 랭킹(부하율):", ", ".join(f"{st} {l:.2f}{'' if not w else f'/{w}분'}" for st, l, w in ranking[h]))


if __name__ == "__main__":
    main()
