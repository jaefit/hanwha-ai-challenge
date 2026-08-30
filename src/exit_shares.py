#!/usr/bin/env python3
"""출구별 저녁 귀가 규모·비중을 관측(교통카드·서울교통공사 승차)에서 뽑는다 → data/derived/exit_shares.json

  .venv/bin/python src/exit_shares.py

왜: 회랑→역 수기 배정표(ASSIGN)는 축제일 실측과 크게 어긋났다(2026-08-29 확인: 샛강 3.5배·국회 7배·마포역 도보 과소, 여의도(5) 과대).
무엇: 출구 7개의 축제일 **초과 승차** E_st = 축제일 승차 − 평시 토요일 중앙값.
  - 5호선 여의도·여의나루·신길, 마포역: OA-12921 시간대별 → 19~23시 합 (연도별 토요일 중앙값 대비)
  - 9호선 여의도·샛강·국회의사당: OA-12914 교통카드 일별 → 일 초과 (검증: 여의도(5)는 일 초과의 96% 가 20~23시)
  - 마포역 도보(마포대교) = 마포역 5호선 초과. 공덕도 ×3~4 지만 경로 확정 못 해 증거로만 기록(보수적)
  - 신길: 1호선 승차는 두 데이터 모두 없음(코레일) → 5호선만. 과소 가능, 표기
출력: 연도별 E_st, 비중, 2년 평균, 출처·기준일. nowcast/backtrack 이 규모·분배 앵커로 쓴다.
"""
import csv, io, re, json, pathlib, datetime, statistics, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
FEST = {"2024": "20241005", "2025": "20250927"}
CARD = {"2024": "card_202410.csv", "2025": "card_202509.csv"}
HOURLY = {"여의도(5)": "여의도", "여의나루(5)": "여의나루", "신길(1·5)": "신길", "마포역 도보(마포대교)": "마포"}   # OA-12921 역명(5호선)
DAILY = {"여의도(9)": ("여의도", "9호선"), "샛강(9)": ("샛강", "9호선"), "국회의사당(9)": ("국회의사당", "9호선")}   # OA-12914
EVE = range(19, 24)


def hour_of(c):
    if "이전" in c: return 5
    if "이후" in c: return 24
    m = re.match(r"\s*(\d{1,2})", c); return int(m.group(1)) if m else None


def hourly_excess(year):
    raw = (RAW / f"subway_{year}.csv").read_bytes().decode("cp949", "ignore"); rd = csv.reader(io.StringIO(raw)); hdr = next(rd)
    di = next(i for i, h in enumerate(hdr) if "일자" in h or "날짜" in h); si = hdr.index("역명"); li = hdr.index("호선"); ti = next(i for i, h in enumerate(hdr) if "구분" in h)
    hc = [(i, hour_of(h)) for i, h in enumerate(hdr) if "시" in h and i not in (di, si, ti, li) and hour_of(h) is not None]
    fest = collections.defaultdict(collections.Counter); sat = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    names = set(HOURLY.values())
    for r in rd:
        st = re.sub(r"\(.*?\)", "", r[si]).strip()
        if st not in names or r[ti] != "승차" or not r[li].startswith("5"): continue
        d = r[di].replace("-", "")
        if d == FEST[year]: tgt = fest[st]
        elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5: tgt = sat[d][st]
        else: continue
        for i, h in hc:
            try: tgt[h] += int(float(r[i] or 0))
            except ValueError: pass
    out = {}
    for ex, st in HOURLY.items():
        f = {h: fest[st][h] for h in EVE}
        med = {h: int(statistics.median(sat[d][st][h] for d in sat if st in sat[d])) for h in EVE}
        med_all = {h: int(statistics.median(sat[d][st][h] for d in sat if st in sat[d])) for h in range(5, 25)}   # 데이터동화 O2 평시 승차율(12~23시) 용
        out[ex] = {"festival_by_hour": f, "saturday_median_by_hour": med, "saturday_median_by_hour_all": med_all, "excess_by_hour": {h: f[h] - med[h] for h in EVE},
                   "excess": sum(f[h] - med[h] for h in EVE), "festival": sum(f.values()), "saturday_median": sum(med.values()), "n_saturdays": len(sat)}
    return out


def daily_excess(year):
    txt = (RAW / CARD[year]).read_bytes().decode("utf-8-sig", "ignore"); txt = txt[txt.find('"사용일자"'):]
    rows = list(csv.DictReader(io.StringIO(txt)))
    out = {}; evidence = {}
    for ex, (nm, ln) in list(DAILY.items()) + [("공덕(5·6)_evidence", ("공덕", "5호선")), ("신길(1)_check", ("신길", "1호선")), ("여의도(5)_check", ("여의도", "5호선"))]:
        f = None; sats = []
        for r in rows:
            if r["역명"].strip().split("(")[0] != nm or not r["노선명"].strip().startswith(ln): continue
            d = r["사용일자"]; v = int(float(r["승차총승객수"] or 0))
            if d == FEST[year]: f = v
            elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5: sats.append(v)
        rec = {"festival": f, "saturday_median": int(statistics.median(sats)) if sats else None, "excess": (f - int(statistics.median(sats))) if f is not None and sats else None, "n_saturdays": len(sats)}
        (out if ex in DAILY else evidence)[ex] = rec
    return out, evidence


def main():
    res = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "festival_days": FEST,
           "sources": {"hourly": "서울교통공사 역별 일별 시간대별 승하차 OA-12921 (5호선 여의도·여의나루·신길·마포, 19~23시)", "daily": "서울 열린데이터광장 교통카드 역별 일별 승하차 OA-12914 (9호선 여의도·샛강·국회의사당)"},
           "by_year": {}, "share_mean": {}, "total_mean": None, "evidence": {}, "notes": []}
    totals = {}
    for y in FEST:
        h = hourly_excess(y); d, ev = daily_excess(y)
        E = {ex: v["excess"] for ex, v in h.items()} | {ex: v["excess"] for ex, v in d.items()}
        tot = sum(E.values())
        res["by_year"][y] = {"E": E, "share": {ex: round(v / tot, 4) for ex, v in E.items()}, "total": tot, "hourly_detail": h, "daily_detail": d}
        res["evidence"][y] = ev; totals[y] = tot
        chk = ev.get("여의도(5)_check", {}); e5h = h["여의도(5)"]["excess"]
        res["notes"].append(f"{y}: 여의도(5) 일 초과(카드) {chk.get('excess')} vs 19~23시 초과(교통공사) {e5h} → 저녁 비율 {round(e5h / chk['excess'], 2) if chk.get('excess') else '-'} (9호선 '일 초과≈저녁 초과' 가정 근거)")
        print(f"{y} 초과 승차 E(명) 합 {tot:,}:", {k: f"{v:,}" for k, v in sorted(E.items(), key=lambda x: -x[1])})
        print(f"     비중:", {k: f"{100*v:.1f}%" for k, v in sorted(res['by_year'][y]['share'].items(), key=lambda x: -x[1])})
        print(f"     증거: 공덕 초과 {ev['공덕(5·6)_evidence']['excess']}, 신길 1호선 {ev['신길(1)_check']}, 검증 {res['notes'][-1][6:]}")
    keys = res["by_year"]["2024"]["E"].keys()
    res["share_mean"] = {ex: round(statistics.mean(res["by_year"][y]["share"][ex] for y in FEST), 4) for ex in keys}
    res["E_mean"] = {ex: round(statistics.mean(res["by_year"][y]["E"][ex] for y in FEST)) for ex in keys}
    res["total_mean"] = round(statistics.mean(totals.values()))
    # 지하철 출구 6개(도보 제외)의 평시 토요일 시간대 승차 합 — nowcast 데이터동화 O2(여의도 핫스팟 30분 승차)의 평시 성분.
    # 5호선 3역은 시간대 중앙값, 9호선 3역은 일 중앙값 × 여의도(5) 시간대 형태(추정). 2년 평균.
    by_year_base = {}
    for y in FEST:
        hd = res["by_year"][y]["hourly_detail"]; dd = res["by_year"][y]["daily_detail"]; y5d = res["evidence"][y]["여의도(5)_check"]["saturday_median"]
        shape5 = {h: hd["여의도(5)"]["saturday_median_by_hour_all"][h] / y5d for h in range(5, 25)}
        by_year_base[y] = {h: sum(hd[st]["saturday_median_by_hour_all"][h] for st in ("여의도(5)", "여의나루(5)", "신길(1·5)"))
                              + sum(dd[st]["saturday_median"] * shape5[h] for st in DAILY) for h in range(5, 25)}
    res["baseline_boarding_by_hour_6exits"] = {h: round(statistics.mean(by_year_base[y][h] for y in FEST)) for h in range(5, 25)}
    res["baseline_boarding_basis"] = "지하철 출구 6개 평시 토요일 승차 합(2년 평균). 5호선 3역 시간대 중앙값 + 9호선 3역 일 중앙값 × 여의도(5) 시간대 형태(추정). 마포역 도보 제외"
    res["notes"] += ["여의나루 초과는 통제 해제 후(22시~) 승차. 모델은 통제 시간대엔 여의도(5)로 이관, 해제 후 비중 적용",
                     "마포역 도보 = 마포역 5호선 초과만. 공덕(×3~4)은 경로 미확정이라 제외 — 보행 귀가 과소 가능",
                     "신길 1호선(코레일)은 두 데이터 모두 없음 → 5호선만. 과소 가능",
                     "KT OD 유출×지하철비중(≈78k)보다 관측 초과 승차(≈109k)가 크다 → 규모 앵커는 관측값, KT 는 시간 형태·α 용도"]
    (DER / "exit_shares.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n2년 평균 비중:", {k: f"{100*v:.1f}%" for k, v in sorted(res["share_mean"].items(), key=lambda x: -x[1])}, "합", f"{res['total_mean']:,}")
    print("→", DER / "exit_shares.json")


if __name__ == "__main__":
    main()
