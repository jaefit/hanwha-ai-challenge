#!/usr/bin/env python3
"""④ 피더 선행지표 사전 근거 — 2024·2025 축제일 시간대 데이터로 "피더 귀속 승차 → 여의도 도착" 교차상관 → data/derived/feeder_leadlag.json

  .venv/bin/python src/feeder_leadlag.py

방법: 예측자 X(h) = Σ_피더 귀속 승차(h) (feeder_origin.json, p50 초과 기반·OD 제약).
      반응 Y(h) = 여의도(5)+여의나루(5) 하차 초과(h) = 축제일 하차 − 평시 토요일 중앙값 (OA-12921).
      Pearson r 을 랙 0h / 1h 에서. 시간대 해상도라 25~40분 랙은 대부분 랙 0 에 나타난다(명시).
한계: 9호선 도착 미포함(시간대 실측 없음), 표본 = 연 10~11시점 × 2년. 5분 해상도 검증은 9/5 라이브(전용 키)로.
"""
import csv, io, re, json, pathlib, datetime, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
FEST = {"2024": "20241005", "2025": "20250927"}
ARRIVE = ("여의도", "여의나루")   # 5호선 하차
HOURS = list(range(10, 21))


def hour_of(c):
    m = re.match(r"\s*(\d{1,2})", c)
    return int(m.group(1)) if m and "시" in c else None


def alight_excess(year):
    raw = (RAW / f"subway_{year}.csv").read_bytes().decode("cp949", "ignore"); rd = csv.reader(io.StringIO(raw)); hdr = next(rd)
    di = next(i for i, h in enumerate(hdr) if "일자" in h or "날짜" in h); si = hdr.index("역명"); li = hdr.index("호선"); ti = next(i for i, h in enumerate(hdr) if "구분" in h)
    hc = [(i, hour_of(h)) for i, h in enumerate(hdr) if hour_of(h) is not None and i not in (di, si, ti, li)]
    fest = {st: {} for st in ARRIVE}; sat = {}
    for r in rd:
        st = re.sub(r"\(.*?\)", "", r[si]).strip()
        if st not in ARRIVE or r[ti] != "하차" or not r[li].startswith("5"): continue
        d = r[di].replace("-", "")
        row = {}
        for i, h in hc:
            try: row[h] = row.get(h, 0) + int(float(r[i] or 0))
            except ValueError: pass
        if d == FEST[year]:
            for h, v in row.items(): fest[st][h] = fest[st].get(h, 0) + v
        elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5:
            sat.setdefault(d, {}).setdefault(st, {})
            for h, v in row.items(): sat[d][st][h] = sat[d][st].get(h, 0) + v
    out = {}
    for h in HOURS:
        med = statistics.median(sum(sat[d].get(st, {}).get(h, 0) for st in ARRIVE) for d in sat)
        out[h] = sum(fest[st].get(h, 0) for st in ARRIVE) - med
    return out


def pearson(xs, ys):
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    sx = (sum((x - mx) ** 2 for x in xs)) ** 0.5; sy = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if sx == 0 or sy == 0: return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    fo = json.loads((DER / "feeder_origin.json").read_text(encoding="utf-8"))
    res = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "method": __doc__.strip().splitlines()[3].strip(), "hours": HOURS, "by_year": {}, "pooled": {}, "top_feeders": {},
           "notes": ["시간대(1h) 해상도: 노선 소요 25~40분 랙은 대부분 랙 0h 에 흡수", "Y 는 5호선 여의도·여의나루 하차 초과만 (9호선 시간대 실측 없음)",
                     "X 는 OD 총량 제약 귀속치 — 순수 관측 아님", "5분 해상도 실측 검증은 9/5 피더 핫스팟 수집으로"]}
    pooled = {0: ([], []), 1: ([], [])}
    for y in FEST:
        X = {int(h): 0.0 for h in range(10, 20)}
        for st, v in fo["feeders_seoul"].items():
            att = (v["by_year"].get(y) or {}).get("attributed") or {}
            for h, a in att.items(): X[int(h)] = X.get(int(h), 0.0) + a
        Y = alight_excess(y)
        r0_pts = [(X[h], Y[h]) for h in range(10, 20) if h in Y]
        r1_pts = [(X[h], Y[h + 1]) for h in range(10, 20) if h + 1 in Y]
        r0 = pearson([p[0] for p in r0_pts], [p[1] for p in r0_pts]); r1 = pearson([p[0] for p in r1_pts], [p[1] for p in r1_pts])
        res["by_year"][y] = {"X_attributed_by_hour": {str(h): round(v) for h, v in X.items()},
                             "Y_alight_excess_by_hour": {str(h): round(v) for h, v in Y.items()},
                             "pearson_lag0": round(r0, 3), "pearson_lag1": round(r1, 3), "n": len(r0_pts)}
        for lag, pts in ((0, r0_pts), (1, r1_pts)):
            pooled[lag][0].extend(p[0] for p in pts); pooled[lag][1].extend(p[1] for p in pts)
        print(f"{y}: lag0 r={r0:.3f}  lag1 r={r1:.3f}  (n={len(r0_pts)})")
        print(f"    X 귀속승차: {[round(X[h]/1000,1) for h in range(10,20)]} (천명, 10~19시)")
        print(f"    Y 도착초과: {[round(Y[h]/1000,1) for h in HOURS]} (천명, 10~20시)")
    for lag in (0, 1):
        res["pooled"][f"lag{lag}"] = {"pearson": round(pearson(*pooled[lag]), 3), "n": len(pooled[lag][0])}
    # 상위 피더 개별 상관 (2년 합동, lag0)
    tops = sorted(fo["feeders_seoul"].items(), key=lambda kv: -sum(sum((kv[1]["by_year"].get(y) or {}).get("attributed", {}).values()) for y in FEST))[:8]
    for st, v in tops:
        xs, ys = [], []
        for y in FEST:
            Y = res["by_year"][y]["Y_alight_excess_by_hour"]
            att = (v["by_year"].get(y) or {}).get("attributed") or {}
            for h in range(10, 20):
                if str(h) in Y or h in [int(k) for k in Y]:
                    xs.append(att.get(str(h), 0)); ys.append(res["by_year"][y]["Y_alight_excess_by_hour"][str(h)])
        r = pearson(xs, ys)
        res["top_feeders"][st] = {"lines": v.get("lines"), "attributed_2yr": round(sum(sum((v["by_year"].get(y) or {}).get("attributed", {}).values()) for y in FEST)), "pearson_lag0_pooled": round(r, 3) if r is not None else None}
    (DER / "feeder_leadlag.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("합동: lag0 r=%.3f  lag1 r=%.3f" % (res["pooled"]["lag0"]["pearson"], res["pooled"]["lag1"]["pearson"]))
    print("상위 피더:", {st: v["pearson_lag0_pooled"] for st, v in res["top_feeders"].items()})
    print("→", DER / "feeder_leadlag.json")


if __name__ == "__main__":
    main()
