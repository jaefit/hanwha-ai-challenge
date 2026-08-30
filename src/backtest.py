#!/usr/bin/env python3
"""출구 모델 백테스트 — 2024·2025 축제일 실측(시간대별 승차, OA-12921)으로 관측 모드 compute_exits 를 검증 → data/derived/backtest.json

  .venv/bin/python src/backtest.py

두 모드:
  A. in-sample(형태): 그 해 E_st + 그 해 KT 유출 곡선 → 시간대 분배(지연·통제 처리)만 검증. 총량은 관측이라 맞게 돼 있다.
  B. cross-year(LOYO): 다른 해 E_st + 다른 해 곡선으로 이 해를 예측 → 2026 예측과 같은 조건(과거 데이터만). 규모 이전 오차 포함.
비교 대상: 5호선 여의도·여의나루·신길, 마포 — 시간대 승차가 있는 4역. 9호선 3역은 일별만 있어 시간대 비교 불가(표기).
예측 승차 = 모델 수요(초과분) + 그 해 평시 토요일 중앙값(개방 시간대). 통제 시간대는 0.
지표: |오차|합/실측합 (승차 기준·초과분 기준), 등급 적중률 (load = 초과분/용량, 대시보드 4등급).
통제 시간대 실측 승차(해제가 시간대 중간, 2024 21시 2.3k·2025 5.8k)는 모델 이월 규칙과 같게 다음 개방 시간대 실측에 합산해 비교(obs_raw 에 원값).
통제: 2024·2025 실적은 여의나루 19~21시 하차≈0(topic-fireworks.md §1) → CLOSED 를 그 해 기준으로 바꿔 계산. 2026 은 20~21시(nowcast.CLOSED).
쇼 종료 시프트(nowcast.SHIFT_MIN)는 2026−기준연도 차이라 과거 연도엔 0 → compute_exits 직접 호출.
"""
import sys, json, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import nowcast as N   # noqa: E402

DER = ROOT / "data" / "derived"
YEARS = {"2024": "od_20241005_yeouido.json", "2025": "od_20250927_yeouido.json"}
CLOSED_BY_YEAR = {"2024": {("여의나루(5)", 19), ("여의나루(5)", 20), ("여의나루(5)", 21)},
                  "2025": {("여의나루(5)", 19), ("여의나루(5)", 20), ("여의나루(5)", 21)}}
STATIONS = ("여의도(5)", "여의나루(5)", "신길(1·5)", "마포역 도보(마포대교)")
HOURS = (19, 20, 21, 22, 23)
GRADE = lambda x: "심각" if x >= 1 else "경계" if x >= 0.8 else "주의" if x >= 0.5 else "여유"   # docs/index.html LV 와 동일


def curve_of(year):
    od = json.loads((DER / YEARS[year]).read_text(encoding="utf-8"))
    return {int(h): v for h, v in od["out_hr"].items()}


def run(target, source, ES):
    """target 해 실측과 비교. source 해의 E·곡선으로 예측 (A: source==target, B: 다른 해)."""
    E = {st: float(v) for st, v in ES["by_year"][source]["E"].items()}
    saved = N.CLOSED; N.CLOSED = CLOSED_BY_YEAR[target]
    try:
        ex = N.compute_exits(curve_of(source), None, None, N.lag_table(), hours=HOURS, station_totals=E)
    finally:
        N.CLOSED = saved
    det = ES["by_year"][target]["hourly_detail"]
    res = {"stations": {}}; tb = to = te = toe = hit = n = 0
    for st in STATIONS:
        obs = det[st]["festival_by_hour"]; base = det[st]["saturday_median_by_hour"]
        rows = {}; eb = ob = ee = oe = h_hit = h_n = 0
        # 통제 시간대 실측 승차(해제가 시간대 중간 → 2024 21시 2.3k·2025 5.8k)는 모델 규칙(이월)과 같게 다음 개방 시간대 실측에 합산해 비교
        obs_eval = {h: obs[str(h)] for h in HOURS}; carry = 0
        for h in HOURS:
            if (st, h) in CLOSED_BY_YEAR[target]: carry += obs_eval[h]; obs_eval[h] = 0
            else: obs_eval[h] += carry; carry = 0
        for h in HOURS:
            closed = (st, h) in CLOSED_BY_YEAR[target]
            pe = ex[st][h]["demand"]; a = obs_eval[h]; b = 0 if closed else base[str(h)]
            p = pe + b; ae = a - b
            pl, ol = pe / N.CAP[st], ae / N.CAP[st]
            pg, og = GRADE(pl), GRADE(ol)
            rows[h] = {"pred": p, "obs": a, "obs_raw": obs[str(h)], "pred_excess": pe, "obs_excess": ae, "pred_load": round(pl, 3), "obs_load": round(ol, 3),
                       "pred_grade": pg, "obs_grade": og, "closed": closed}
            eb += abs(p - a); ob += a; ee += abs(pe - ae); oe += abs(ae)
            if not closed: h_n += 1; h_hit += (pg == og)
        res["stations"][st] = {"by_hour": rows, "err_boarding": round(eb / max(1, ob), 3), "err_excess": round(ee / max(1, oe), 3),
                               "grade_hits": h_hit, "grade_n": h_n, "capacity": N.CAP[st], "estimated_capacity": st in N.ESTIMATED}
        tb += eb; to += ob; te += ee; toe += oe; hit += h_hit; n += h_n
    res.update({"total_err_boarding": round(tb / to, 3), "total_err_excess": round(te / toe, 3), "grade_hit_rate": round(hit / n, 3), "grade_hits": hit, "grade_n": n,
                "source_year": source, "target_year": target})
    return res


def show(title, r):
    print(f"\n{title}  (예측 승차/실측 승차)")
    for st, v in r["stations"].items():
        cells = " ".join(f"{h}h {x['pred']:>6,}/{x['obs']:>6,}" for h, x in v["by_hour"].items())
        print(f"  {st:<14} {cells}  |err|/obs 승차 {v['err_boarding']:.2f} · 초과 {v['err_excess']:.2f} · 등급 {v['grade_hits']}/{v['grade_n']}")
    print(f"  4역 합계: 승차 {r['total_err_boarding']:.2f} · 초과 {r['total_err_excess']:.2f} · 등급 적중 {r['grade_hits']}/{r['grade_n']} ({100*r['grade_hit_rate']:.0f}%)")


def main():
    ES = json.loads((DER / "exit_shares.json").read_text(encoding="utf-8"))
    out = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "doc": __doc__.strip().splitlines()[0],
           "observed_source": "서울교통공사 OA-12921 시간대별 승차 (exit_shares.json hourly_detail)", "closed_by_year": {y: sorted(h for _, h in c) for y, c in CLOSED_BY_YEAR.items()},
           "hours": list(HOURS), "stations": list(STATIONS), "modes": {"A_in_sample": {}, "B_cross_year": {}},
           "notes": ["A: 총량은 관측 E 라 맞음 → 시간대 형태·지연·통제 처리만 검증", "B: 다른 해 E·곡선 → 2026 과 같은 조건(과거만). 규모 이전 오차 포함",
                     "9호선 3역·마포역 도보 실측은 일별/추정이라 시간대 비교 불가 → 4역만", "통제 시간대 실측(해제 직후 승차)은 다음 개방 시간대에 합산 비교 (모델 이월 규칙과 동일, obs_raw 원값)", "등급 load = 초과분/용량(nowcast.CAP). 신길·마포 용량은 추정치"]}
    for y in YEARS:
        a = run(y, y, ES); out["modes"]["A_in_sample"][y] = a; show(f"A in-sample {y}", a)
    for y in YEARS:
        o = [k for k in YEARS if k != y][0]
        b = run(y, o, ES); out["modes"]["B_cross_year"][y] = b; show(f"B cross-year {o}→{y}", b)
    for m in out["modes"]:
        ys = out["modes"][m]
        out["modes"][m]["summary"] = {"err_boarding": {y: ys[y]["total_err_boarding"] for y in YEARS}, "err_excess": {y: ys[y]["total_err_excess"] for y in YEARS},
                                      "grade_hit_rate": {y: ys[y]["grade_hit_rate"] for y in YEARS}}
    (DER / "backtest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n→", DER / "backtest.json")


if __name__ == "__main__":
    main()
