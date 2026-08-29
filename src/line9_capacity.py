#!/usr/bin/env python3
"""9호선(여의도·샛강·국회의사당)·1호선 신길 용량 비례 추정 → data/derived/line9_capacity.json

  .venv/bin/python src/line9_capacity.py

근거: 서울교통공사 시간대별 데이터(OA-12921)엔 9호선·1호선(코레일)이 없다. 교통카드 역별 **일별** 승하차(OA-12914, 1~9호선)는 있다.
방법: 축제일 같은 날의 일 승차 비율로 5호선 관측 최대 시간당 승차를 비례 배분한다.
  CAP[9호선 역] = CAP[여의도(5)] × (축제일 9호선 역 일 승차 ÷ 축제일 여의도(5) 일 승차)   — 2024·2025 평균
  CAP[신길(1·5)] = CAP5[신길] × (1 + 축제일 신길 1호선 일 승차 ÷ 신길 5호선 일 승차)   — 기존 ×2 가정을 대체
가정(표기): 일 승차 비율 ≈ 피크 시간 승차 비율. 9호선 급행 정차(여의도)·환승 구조 차이는 반영 못 한다 → estimated_capacity 유지.
입력: data/raw/card_202509.csv, card_202410.csv (src/fetch_seoul_data.py card 202509 202410), data/derived/baseline.json
"""
import csv, io, json, pathlib, datetime, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
BASE = json.loads((DER / "baseline.json").read_text(encoding="utf-8"))
FEST = {"2024": ("20241005", "card_202410.csv"), "2025": ("20250927", "card_202509.csv")}
STATIONS = {"여의도": {"5호선", "9호선"}, "샛강": {"9호선"}, "국회의사당": {"9호선"}, "여의나루": {"5호선"}, "신길": {"1호선", "5호선"}}


def read_card(fn):
    txt = (RAW / fn).read_bytes().decode("utf-8-sig", "ignore").lstrip("﻿")
    txt = txt[txt.find('"사용일자"'):] if '"사용일자"' in txt else txt
    rows = list(csv.DictReader(io.StringIO(txt)))
    return rows


def main():
    out = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "source": "서울 열린데이터광장 OA-12914 교통카드 역별 일별 승하차 (1~9호선)", "days": {}, "ratios": {}, "capacity": {}}
    ratios = {k: [] for k in ("여의도(9)", "샛강(9)", "국회의사당(9)", "신길1/신길5")}
    for y, (day, fn) in FEST.items():
        rows = read_card(fn)
        lines_seen = sorted({r["노선명"] for r in rows})
        pick = {}
        sats = {}
        for r in rows:
            nm, ln = r["역명"].strip(), r["노선명"].strip()
            base = nm.split("(")[0]
            if base in STATIONS and any(ln.startswith(l) for l in STATIONS[base]):
                key = f"{base}|{ln}"
                d = r["사용일자"]
                v = int(float(r["승차총승객수"] or 0))
                if d == day: pick[key] = v
                elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5: sats.setdefault(key, []).append(v)
        out["days"][y] = {"festival": day, "boarding_festival": pick, "boarding_saturday_median": {k: int(statistics.median(v)) for k, v in sats.items()},
                          "uplift": {k: round(pick[k] / statistics.median(sats[k]), 2) for k in pick if k in sats}}
        print(f"{y} {day}  (파일 노선 예: {[l for l in lines_seen if l.startswith(('5','9','1호'))][:6]})")
        for k, v in sorted(pick.items()): print(f"   {k:<14} 승차 {v:>7,}  평시토 중앙 {int(statistics.median(sats[k])) if k in sats else '-':>7}  ×{out['days'][y]['uplift'].get(k, '-')}")
        y5 = pick.get("여의도|5호선")
        if y5:
            for st in ("여의도", "샛강", "국회의사당"):
                k9 = next((k for k in pick if k.startswith(st + "|9")), None)
                if k9: ratios[f"{st}(9)"].append(pick[k9] / y5)
        s5, s1 = pick.get("신길|5호선"), next((pick[k] for k in pick if k.startswith("신길|1")), None)
        if s5 and s1: ratios["신길1/신길5"].append(s1 / s5)
    cap5 = BASE["subway_capacity_obs_max_per_hour"]["여의도"]; cap_singil5 = BASE["subway_capacity_obs_max_per_hour"]["신길"]
    for k, v in ratios.items():
        if v: out["ratios"][k] = {"by_year": [round(x, 4) for x in v], "mean": round(statistics.mean(v), 4)}
    for st in ("여의도(9)", "샛강(9)", "국회의사당(9)"):
        if st in out["ratios"]:
            out["capacity"][st] = {"value": round(cap5 * out["ratios"][st]["mean"]), "basis": f"여의도(5) 관측 최대 {cap5:,}/h × 일승차비 {out['ratios'][st]['mean']} (축제일 2년 평균, 추정)", "estimated": True}
    if "신길1/신길5" in out["ratios"]:
        r = out["ratios"]["신길1/신길5"]["mean"]
        out["capacity"]["신길(1·5)"] = {"value": round(cap_singil5 * (1 + r)), "basis": f"신길(5) 관측 최대 {cap_singil5:,}/h × (1 + 1호선/5호선 일승차비 {r}) (추정, 기존 ×2 대체)", "estimated": True}
    out["note"] = "일 승차 비율 ≈ 피크 시간 비율 가정. 9호선 급행·환승 구조 차이 미반영. 기존 수기값: 여의도(9) 12000 · 샛강 4000 · 국회의사당 4000 · 신길 ×2"
    (DER / "line9_capacity.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n용량:", {k: v["value"] for k, v in out["capacity"].items()})
    print("→", DER / "line9_capacity.json")


if __name__ == "__main__":
    main()
