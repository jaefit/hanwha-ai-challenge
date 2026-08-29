#!/usr/bin/env python3
"""L2·L3·L4 나우캐스트: 오늘 수집 로그 + baseline.json → data/live/forecast_latest.json

  .venv/bin/python src/nowcast.py            # 1회 계산
  .venv/bin/python src/nowcast.py --date 20260905

L2 α(t)  = 여의나루 누적 하차(관측, citydata LIVE_SUB_PPLTN) / 축제일 2년 평균 누적 하차(같은 시각까지)
           여의나루는 19시부터 무정차라 α 는 19:00 이후 동결. 관측이 없으면 α=1.
L3 출구수요 = α × 유출곡선(h) × 방향분포 × 지하철 비중 → 회랑별 역 배정표
L4 대기(분) = max(0, 수요 − 용량) / 용량 × 60.   용량 = 관측 최대 시간당 승차(1~8호선), 9호선은 추정(주석)
출처: data/derived/baseline.json (KT OD·서울교통공사), data/live/api_*.jsonl (서울 실시간 도시데이터)
"""
import json, sys, pathlib, datetime, collections

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
    "신길(1·5)": BASE["subway_capacity_obs_max_per_hour"]["신길"] * 2,   # 1호선 경부선 합산 추정
    "여의도(9)": 12000, "샛강(9)": 4000, "국회의사당(9)": 4000,          # 추정: 9호선 시간대 실적 미공개
    "마포역 도보(마포대교)": 15000,                                        # 추정: 보행로 1차로 폭 기준
}
ESTIMATED = {"신길(1·5)", "여의도(9)", "샛강(9)", "국회의사당(9)", "마포역 도보(마포대교)"}
# 불꽃쇼 종료 시각 앵커. 베이스라인(2024·2025)은 19:20~20:30 진행 → 유출 피크 20시.
# 2026은 20:00~21:10(영국 20:00, 미국 20:20, 한국 ~20:40) → 종료가 +40분 늦다. 유출 곡선을 그만큼 뒤로 민다.
SHOW_END_BASE, SHOW_END_2026 = (20, 30), (21, 10)
SHIFT_MIN = (SHOW_END_2026[0] * 60 + SHOW_END_2026[1]) - (SHOW_END_BASE[0] * 60 + SHOW_END_BASE[1])
CLOSED = {("여의나루(5)", 20), ("여의나루(5)", 21)}   # 2026 공식 공지(hanwhafireworks.com/notice/6): 여의나루역 임시 통제 20:40~21:40. 2024·2025 실적은 19~20시대 하차 ≈0


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
    # 공원→역 도달 지연: OD 출발시각 기준 유출의 40%가 같은 시간대, 60%가 다음 시간대에 역에 닿는다(추정).
    # 근거: KT 유출 피크 20시 vs 여의도역 승차 피크 21시(2024·2025 동일). 보행 20~40분 + 대기.
    LAG_SAME, LAG_NEXT = 0.4, 0.6
    # 베이스라인 유출 곡선을 SHIFT_MIN 만큼 뒤로 민다 (시간대 선형 배분)
    f = (SHIFT_MIN % 60) / 60; k = SHIFT_MIN // 60
    shifted = {h: (1 - f) * out_base.get(h - k, 0) + f * out_base.get(h - k - 1, 0) for h in range(17, 25)}
    total = {h: a * shifted.get(h, 0) for h in range(17, 25)}
    exits = collections.OrderedDict(); backlog = collections.Counter()
    for h in hours:
        arriving = LAG_SAME * total[h] + LAG_NEXT * total[h - 1]
        demand = collections.Counter()
        for d, share in dirs.items():
            for st, w in ASSIGN.get(d, {}).items():
                demand[st] += arriving * share * sub_share * w
        # 무정차 시간대엔 여의나루 수요를 여의도(5)로 이관
        for st in list(demand):
            if (st, h) in CLOSED:
                demand["여의도(5)"] += demand[st]; demand[st] = 0.0
        for st in CAP:
            dem = demand.get(st, 0.0); cap = CAP[st]; closed = (st, h) in CLOSED
            backlog[st] = 0.0 if closed else max(0.0, backlog[st] + dem - cap)   # 시간대 넘어가는 누적 대기열
            wait = None if closed else round(backlog[st] / cap * 60)
            load = None if closed else round(dem / cap, 2)   # 부하율 = 수요/용량. 랭킹은 이 값으로(관측 최대 처리량이 곧 용량이라 절대 대기분은 보수적)
            exits.setdefault(st, {})[str(h)] = {"demand": round(dem), "capacity": cap, "load": load, "backlog": round(backlog[st]), "wait_min": wait, "closed": closed, "estimated_capacity": st in ESTIMATED}
    ranking = {}
    for h in hours:
        opens = [(st, v[str(h)]["load"], v[str(h)]["wait_min"]) for st, v in exits.items() if not v[str(h)]["closed"]]
        ranking[str(h)] = sorted(opens, key=lambda x: (x[1], x[2]))
    seoul_fcst = (city.get("여의도한강공원") or {}).get("fcst", [])
    result = {
        "ts": now.isoformat(timespec="seconds"), "date": date, "alpha": a, "alpha_reason": why,
        "outflow_forecast": {str(h): round(total[h]) for h in hours},
        "outflow_baseline": {str(h): out_base[h] for h in hours},
        "show_shift_min": SHIFT_MIN, "show_end_2026": "21:10", "show_end_baseline": "20:30",
        "direction_share": dirs, "subway_share": sub_share, "direction_basis": dir_basis,
        "exits": exits, "ranking_by_hour": ranking,
        "closures": [{"exit": "여의나루(5)", "hours": [20, 21], "basis": "2026 공식 공지: 임시 통제 20:40~21:40 (현장 공지). 2024·2025 실적: 19~20시대 하차 ≈0"}, {"road": "여의동로", "hours": [15, 24], "basis": "2026 공식 공지: 마포대교 남단~63빌딩 전면 통제"}, {"road": "원효대교", "basis": "2026 공식 공지: 설치·행사·철수 일정별 전면 통제"}],
        "alerts_live": alerts[:10],
        "live_snapshot": {k: {"congest": v.get("congest"), "ppltn": [v.get("ppltn_min"), v.get("ppltn_max")], "ts": v.get("ppltn_time"), "road": v.get("road_idx")} for k, v in city.items()},
        "seoul_fcst_snapshot": seoul_fcst,
        "notes": ["유출 곡선은 불꽃쇼 종료 앵커 기준 +40분 이동(2025 20:30 → 2026 21:10)", "용량 중 estimated_capacity=true 는 추정치(9호선·도보·1호선 합산)", "역 도달 지연 40%/60%(같은/다음 시간대)는 추정 — 유출 피크 20시 vs 승차 피크 21시 근거", "대기열은 시간대를 넘어 누적(backlog)", "α 는 여의나루 누적 하차 기준, 19:00 이후 동결", "cnt 기반 수치는 KT 추정치 — 비율·순위 용도"],
    }
    (LIVE / "forecast_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"α={a} ({why})"); print("유출 예측:", result["outflow_forecast"])
    for h in ("20", "21", "22"):
        print(f"{h}시 출구 랭킹(부하율):", ", ".join(f"{st} {l:.2f}{'' if not w else f'/{w}분'}" for st, l, w in ranking[h]))


if __name__ == "__main__":
    main()
