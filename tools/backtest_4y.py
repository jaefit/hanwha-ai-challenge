#!/usr/bin/env python3
"""4년 교차 검증(2022·2023 추가) — 보고서·제안사항용. **라이브 모델은 읽지도 쓰지도 않는다.**

  .venv/bin/python tools/backtest_4y.py

작성 2026-09-04 23:50. 사용자 결정: 축제는 2000년부터인데 2년만 썼다 → 표본을 늘려 C1(교차 오차 ±42% vs α 밴드 ±5%)의
근거를 대되, 9/5 본번에 도는 모델(`src/`·`exit_shares.json`·`exit_forecast_2026.json`·`backtest.json`)은 건드리지 않는다.
출력은 전부 `_4y` 접미사 별도 파일.

자료 (data/raw, git 제외 — 2026-09-04 23:37 내려받음)
  subway_2022.csv (OA-12921 seq 39) · subway_2023.csv (seq 45) · card_202310.csv (OA-12914) · card_2022.csv (연간 파일, seq 113)
  od_20231007.zip (OA-22300) — KT 일별 OD 는 2023-01-01 부터라 **2022 축제일 유출 곡선은 없다**
  → 2022 는 실측 목표(target)로만 쓴다. 소스(E·곡선)는 2023·2024·2025. 교차 쌍 = 2022:3 + 2023:2 + 2024:2 + 2025:2 = 9 (지금 2)

여의나루 통제(시간대) — 축제일 승차 실측에서 읽음 (0 에 가까운 시간대)
  2022 20221008: 19시 2,830 · 20시 444 · 21시 1,832 · 22시 8,546 → 20시만 (부분 통제, 21시도 낮음 — 주석)
  2023 20231007: 19시 46 · 20시 55 · 21시 8,438 → 19·20시
  2024·2025 는 backtest.py 그대로 (19·20·21, 21시는 해제가 시간대 중간이라 이월 규칙)
"""
import json, sys, pathlib, csv, io, datetime, statistics, collections, itertools

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import exit_shares as XS      # noqa: E402
import backtest as BT         # noqa: E402
import backtrack as BK        # noqa: E402

RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
FEST = {"2022": "20221008", "2023": "20231007", "2024": "20241005", "2025": "20250927"}
CARD_MONTH = {"2023": ("card_202310.csv", None), "2022": ("card_2022.csv", "202210")}   # (파일, 월 필터 — 연간 파일은 축제 달만)
CLOSED = {"2022": {("여의나루(5)", 20)}, "2023": {("여의나루(5)", 19), ("여의나루(5)", 20)}}
CLOSED.update(BT.CLOSED_BY_YEAR)
SOURCES = ("2023", "2024", "2025")
TARGETS = ("2022", "2023", "2024", "2025")


def daily_excess_month(year, fn, month):
    """exit_shares.daily_excess 와 같은 계산 — 연간 카드 파일이라 축제 달의 토요일만 중앙값에 넣는다(월파일과 같은 조건)."""
    raw = (RAW / fn).read_bytes()
    txt = raw.decode("utf-8-sig", "ignore")
    if '"사용일자"' not in txt[:2000]: txt = raw.decode("cp949", "ignore")     # 연간 파일(2022)은 cp949
    txt = txt[txt.find('"사용일자"'):]
    rows = [r for r in csv.DictReader(io.StringIO(txt)) if month is None or r["사용일자"].startswith(month)]
    out, evidence = {}, {}
    for ex, (nm, ln) in list(XS.DAILY.items()) + [("공덕(5·6)_evidence", ("공덕", "5호선")), ("신길(1)_check", ("신길", "1호선")), ("여의도(5)_check", ("여의도", "5호선"))]:
        f = None; sats = []
        for r in rows:
            if r["역명"].strip().split("(")[0] != nm or not r["노선명"].strip().startswith(ln): continue
            d = r["사용일자"]; v = int(float(r["승차총승객수"] or 0))
            if d == FEST[year]: f = v
            elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5: sats.append(v)
        rec = {"festival": f, "saturday_median": int(statistics.median(sats)) if sats else None,
               "excess": (f - int(statistics.median(sats))) if f is not None and sats else None, "n_saturdays": len(sats)}
        (out if ex in XS.DAILY else evidence)[ex] = rec
    return out, evidence


def exit_shares_year(year):
    XS.FEST[year] = FEST[year]
    h = XS.hourly_excess(year)
    fn, month = CARD_MONTH[year]
    d, ev = daily_excess_month(year, fn, month)
    E = {ex: v["excess"] for ex, v in h.items()} | {ex: v["excess"] for ex, v in d.items()}
    # exit_shares.json 을 읽은 2024·2025 는 시간 키가 문자열이다 — backtest.run 이 obs[str(h)] 로 읽으니 같은 형태로 맞춘다
    return json.loads(json.dumps({"E": E, "total": sum(E.values()), "hourly_detail": h, "daily_detail": d, "evidence": ev}, ensure_ascii=False))


def od_curve(day):
    """backtest.curve_of 가 읽는 형태(out_hr)만 — backtrack.od_inflow_outflow 그대로 호출."""
    fn = DER / f"od_{day}_yeouido.json"
    if fn.exists():
        return
    inflow, outflow = BK.od_inflow_outflow(day)
    out_hr = collections.Counter(); in_hr = collections.Counter()
    for (_, t), v in outflow.items(): out_hr[f"{t:02d}"] += v
    for (_, t), v in inflow.items(): in_hr[f"{t:02d}"] += v
    fn.write_text(json.dumps({"day": day, "in_hr": dict(sorted(in_hr.items())), "out_hr": dict(sorted(out_hr.items())),
                              "note": "tools/backtest_4y.py 가 backtrack.od_inflow_outflow 로 만든 유출 곡선(시간대 합). 보고서용."},
                             ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  → {fn.name}")


def main():
    base = json.loads((DER / "exit_shares.json").read_text(encoding="utf-8"))
    by_year = {y: base["by_year"][y] for y in ("2024", "2025")}
    for y in ("2022", "2023"):
        print(f"exit_shares {y} …", flush=True)
        by_year[y] = exit_shares_year(y)
        print(f"  {y} E 합 {by_year[y]['total']:,}:", {k: f"{v:,}" for k, v in sorted(by_year[y]["E"].items(), key=lambda x: -x[1])})
    ES = {"by_year": by_year}
    od_curve("20231007")
    BT.YEARS["2023"] = "od_20231007_yeouido.json"
    BT.CLOSED_BY_YEAR.update(CLOSED)

    res = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "doc": "4년 교차 검증 — 보고서·제안사항용. 라이브 모델 미반영 (tools/backtest_4y.py)",
           "festival_days": FEST, "closed_by_year": {y: sorted(h for _, h in c) for y, c in CLOSED.items()},
           "sources": list(SOURCES), "targets": list(TARGETS),
           "E_by_year": {y: by_year[y]["E"] for y in TARGETS},
           "pairs": {}, "in_sample": {}}
    rows = []
    for t in TARGETS:
        for s in SOURCES:
            r = BT.run(t, s, ES)
            key = f"{s}->{t}"
            if s == t:
                res["in_sample"][t] = r
            else:
                res["pairs"][key] = r
                rows.append((t, s, r["total_err_excess"], r["total_err_boarding"], r["grade_hit_rate"], r["grade_hits"], r["grade_n"]))
    errs = [r[2] for r in rows]; hits = sum(r[5] for r in rows); n = sum(r[6] for r in rows)
    res["summary"] = {"n_pairs": len(rows), "err_excess": {"mean": round(statistics.mean(errs), 3), "median": round(statistics.median(errs), 3),
                                                            "min": round(min(errs), 3), "max": round(max(errs), 3)},
                      "grade_hit_rate_pooled": round(hits / n, 3), "grade_hits": hits, "grade_n": n,
                      "prev_2y": {"pairs": 2, "err_excess": [BT_prev(y) for y in ("2024", "2025")]}}
    (DER / "backtest_4y.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n교차 검증 (소스 해의 E·곡선 → 목표 해 실측)   |초과 오차| = Σ|예측−실측| / Σ|실측|, 4역 19~23시")
    print(f"{'목표':<6}{'소스':<6}{'초과 오차':>9}{'승차 오차':>9}{'등급 적중':>10}")
    for t, s, ee, eb, hr, h, m in rows:
        print(f"{t:<6}{s:<6}{ee:>9.2f}{eb:>9.2f}{h:>6}/{m:<3}({100*hr:.0f}%)")
    S = res["summary"]
    print(f"\n9쌍 요약: 초과 오차 평균 {S['err_excess']['mean']:.2f} · 중앙값 {S['err_excess']['median']:.2f} · 범위 {S['err_excess']['min']:.2f}~{S['err_excess']['max']:.2f} · 등급 적중 {hits}/{n} ({100*hits/n:.0f}%)")
    print(f"기존 2쌍(24↔25): 초과 오차 {S['prev_2y']['err_excess']}")
    print("→", DER / "backtest_4y.json")


def BT_prev(y):
    try:
        return json.loads((DER / "backtest.json").read_text(encoding="utf-8"))["modes"]["B_cross_year"][y]["total_err_excess"]
    except Exception:
        return None


if __name__ == "__main__":
    main()
