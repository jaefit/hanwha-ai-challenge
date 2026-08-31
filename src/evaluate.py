#!/usr/bin/env python3
"""오차표 (T6) — 우리 예측 vs 서울시 12h 예측 vs 실측. 출력: 마크다운 표 + data/derived/eval_YYYYMMDD.json

  .venv/bin/python src/evaluate.py --date 20260905
  .venv/bin/python src/evaluate.py --fallback rehearsal                       # 9/4 전야제 로그로
  .venv/bin/python src/evaluate.py --date 20260905 --official data/raw/subway_2026.csv   # OA-12921 공개 후 확정판

층위:
 1) 서울시 12h 인구 예측 성능(기준선): 여의도한강공원 실측 인구 vs 그 시각을 가장 일찍 예측한 스냅샷 — MAPE·범위 포함률
 2) 우리 예측 안정성: 사전표 → publish 스냅샷(data/live/forecast_history/) → 최종. α p50·밴드 추이
 3) 지하철 형태: 여의도권 핫스팟 30분 승차 실측 vs 우리 지하철 6출구 수요+평시 — 커버리지로 스케일 자유 → 상관·피크 시각만
 4) --official: 축제일 출구별 시간대 승차 실측(5호선 4역) vs 사전표 — |오차|/실측·등급 적중·밴드 포함 (backtest.py 와 같은 이월 규칙)
"""
import json, sys, csv, io, re, pathlib, datetime, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE, DER = ROOT / "data" / "live", ROOT / "data" / "derived"
sys.path.insert(0, str(ROOT / "src"))
import nowcast as N   # noqa: E402

HOURLY_MAP = {"여의도(5)": "여의도", "여의나루(5)": "여의나루", "신길(1·5)": "신길", "마포역 도보(마포대교)": "마포"}
LVL = lambda x: "심각" if x >= 1 else "경계" if x >= 0.8 else "주의" if x >= 0.5 else "여유"


def ape(actual, pred):
    return abs(actual - pred) / actual if actual else None


def first_forecast_for(records, area="여의도한강공원"):
    """각 목표 시각(YYYY-MM-DD HH:00)을 가장 일찍 예측한 스냅샷 → {target: {min,max,lvl,at,lead_min}}"""
    out = {}
    for r in sorted(records, key=lambda x: x.get("ts", "")):
        if r.get("area") != area: continue
        for f in r.get("fcst") or []:
            t = f.get("t")
            if t and t not in out:
                lead = (datetime.datetime.fromisoformat(t.replace(" ", "T")) - datetime.datetime.fromisoformat(r["ts"])).total_seconds() / 60
                out[t] = {"min": f["min"], "max": f["max"], "lvl": f.get("lvl"), "at": r["ts"], "lead_min": round(lead)}
    return out


def actual_pop(records, area="여의도한강공원"):
    """정시(HH:00)에 가장 가까운 실측 인구(±30분) → {target: mid}"""
    rows = [(r["ts"], (r["ppltn_min"] + r["ppltn_max"]) / 2) for r in records if r.get("area") == area and r.get("ppltn_min") is not None]
    out = {}
    for ts, mid in rows:
        t = datetime.datetime.fromisoformat(ts)
        tgt = t.replace(minute=0, second=0) + datetime.timedelta(hours=round(t.minute / 60))
        key = tgt.strftime("%Y-%m-%d %H:00"); off = abs((t - tgt).total_seconds())
        if off <= 1800 and (key not in out or off < out[key][1]):
            out[key] = (mid, off)
    return {k: v[0] for k, v in out.items()}


def load_records(date):
    fn = LIVE / f"api_{date}.jsonl"
    return [json.loads(l) for l in fn.read_text(encoding="utf-8").splitlines() if l.strip()] if fn.exists() else []


def seoul_baseline(records):
    fc, act = first_forecast_for(records), actual_pop(records)
    rows = []
    for t in sorted(set(fc) & set(act)):
        p = fc[t]; mid_p = (p["min"] + p["max"]) / 2
        rows.append({"t": t, "actual": act[t], "pred_mid": mid_p, "pred_range": [p["min"], p["max"]], "lead_min": p["lead_min"],
                     "ape": round(ape(act[t], mid_p), 3) if act[t] else None, "in_range": p["min"] <= act[t] <= p["max"]})
    apes = [r["ape"] for r in rows if r["ape"] is not None]
    return {"rows": rows, "mape": round(statistics.mean(apes), 3) if apes else None,
            "range_hit": round(sum(r["in_range"] for r in rows) / len(rows), 3) if rows else None}


def our_snapshots(date):
    hdir = LIVE / "forecast_history" / date
    snaps = []
    files = sorted(hdir.glob("*.json")) if hdir.exists() else []
    if not files and (LIVE / "forecast_latest.json").exists():
        fc = json.loads((LIVE / "forecast_latest.json").read_text(encoding="utf-8"))
        if fc.get("date") == date: files = [None]; snaps.append(("latest", fc))
    for f in files:
        if f is not None: snaps.append((f.stem, json.loads(f.read_text(encoding="utf-8"))))
    rows = []
    for name, fc in snaps:
        a = fc.get("assimilation") or {}
        al = a.get("alpha") or [None, fc.get("alpha"), None]
        rows.append({"at": name, "alpha": al, "n_obs": a.get("n_obs"), "out21": (fc.get("outflow_forecast") or {}).get("21")})
    return rows


def subway_shape(records, date):
    obs = {}
    for area in ("여의도", "여의도한강공원"):
        for (h, half), (t, s) in N._win(records, area).items():
            try: v = (float(s["SUB_30WTHN_GTON_PPLTN_MIN"]) + float(s["SUB_30WTHN_GTON_PPLTN_MAX"])) / 2
            except (KeyError, TypeError, ValueError): continue
            obs[h] = obs.get(h, 0) + v
    prior = json.loads((DER / "exit_forecast_2026.json").read_text(encoding="utf-8"))
    pred = {int(h): sum(prior["exits"][st][h]["demand"] or 0 for st in prior["exits"] if st != "마포역 도보(마포대교)") + N.BASE6.get(int(h), 0) for h in ("19", "20", "21", "22", "23")}
    common = sorted(set(obs) & set(pred))
    r = None
    if len(common) >= 3:
        xs, ys = [obs[h] for h in common], [pred[h] for h in common]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        sx = (sum((x - mx) ** 2 for x in xs)) ** .5; sy = (sum((y - my) ** 2 for y in ys)) ** .5
        if sx and sy: r = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sx / sy, 3)
    return {"obs_by_hour": {str(h): round(v) for h, v in sorted(obs.items())}, "pred_by_hour": {str(h): round(v) for h, v in pred.items()},
            "hours_common": common, "pearson": r,
            "peak_obs": max(obs, key=obs.get) if obs else None, "peak_pred": max(pred, key=pred.get),
            "note": "실측=여의도·여의도한강공원 핫스팟 30분 승차 합(커버리지 상이) → 스케일 자유, 형태(상관·피크)만 유효"}


def official_eval(csv_path, date):
    raw = pathlib.Path(csv_path).read_bytes().decode("cp949", "ignore"); rd = csv.reader(io.StringIO(raw)); hdr = next(rd)
    di = next(i for i, h in enumerate(hdr) if "일자" in h or "날짜" in h); si = hdr.index("역명"); li = hdr.index("호선"); ti = next(i for i, h in enumerate(hdr) if "구분" in h)
    hc = [(i, int(m.group(1))) for i, h in enumerate(hdr) if (m := re.match(r"\s*(\d{1,2})", h)) and "시" in h and i not in (di, si, ti, li)]
    names = set(HOURLY_MAP.values()); fest = {}; sat = {}
    for r in rd:
        st = re.sub(r"\(.*?\)", "", r[si]).strip()
        if st not in names or r[ti] != "승차" or not r[li].startswith("5"): continue
        d = r[di].replace("-", "")
        row = {}
        for i, h in hc:
            try: row[h] = row.get(h, 0) + int(float(r[i] or 0))
            except ValueError: pass
        if d == date:
            for h, v in row.items(): fest.setdefault(st, {})[h] = fest.get(st, {}).get(h, 0) + v
        elif datetime.date(int(d[:4]), int(d[4:6]), int(d[6:])).weekday() == 5:
            b = sat.setdefault(d, {}).setdefault(st, {})
            for h, v in row.items(): b[h] = b.get(h, 0) + v
    if not fest: return {"error": f"{date} 승차 데이터가 파일에 없음 (공개 지연?)"}
    prior = json.loads((DER / "exit_forecast_2026.json").read_text(encoding="utf-8"))
    out = {"stations": {}, "note": "이월 규칙 동일: 통제 시간대 실측은 다음 개방 시간대에 합산"}
    tb = to = hit = n = binc = 0
    for ex, stn in HOURLY_MAP.items():
        med = {h: int(statistics.median(sat[d].get(stn, {}).get(h, 0) for d in sat)) for h in range(19, 24)}
        obs = {h: fest.get(stn, {}).get(h, 0) for h in range(19, 24)}
        carry = 0; obs_ev = {}
        for h in range(19, 24):
            closed = prior["exits"][ex][str(h)]["closed"]
            if closed: carry += obs[h]; obs_ev[h] = 0
            else: obs_ev[h] = obs[h] + carry; carry = 0
        rows = {}; eb = ob = s_hit = s_n = 0
        for h in range(19, 24):
            v = prior["exits"][ex][str(h)]; closed = v["closed"]
            pred = 0 if closed else v["demand"] + med[h]; a = obs_ev[h]
            pl = 0 if closed else v["load"]; ol = (a - (0 if closed else med[h])) / N.CAP[ex]
            row = {"pred": pred, "obs": a, "ape": round(ape(a, pred), 3) if a else None,
                   "pred_grade": "통제" if closed else LVL(pl), "obs_grade": "통제" if closed else LVL(ol),
                   "band_hit": (None if closed else bool(v["load_lo"] <= ol <= v["load_hi"]))}
            rows[str(h)] = row
            if not closed:
                eb += abs(pred - a); ob += a; s_n += 1; s_hit += row["pred_grade"] == row["obs_grade"]; binc += bool(row["band_hit"]); n += 1
        hit += s_hit
        out["stations"][ex] = {"by_hour": rows, "err_abs_over_obs": round(eb / max(1, ob), 3), "grade_hit": f"{s_hit}/{s_n}"}
        tb += eb; to += ob
    out["total"] = {"err_abs_over_obs": round(tb / max(1, to), 3), "grade_hit_rate": round(hit / max(1, n), 3), "band_hit_rate": round(binc / max(1, n), 3)}
    return out


def md_table(rows, cols, keys):
    s = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows: s += "| " + " | ".join(str(r.get(k, "—")) for k in keys) + " |\n"
    return s


def main():
    date = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else datetime.datetime.now().strftime("%Y%m%d")
    if "--fallback" in sys.argv and sys.argv[sys.argv.index("--fallback") + 1] == "rehearsal": date = "20260904"
    recs = load_records(date)
    res = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "date": date, "n_records": len(recs),
           "seoul_12h": seoul_baseline(recs), "our_snapshots": our_snapshots(date), "subway_shape": subway_shape(recs, date)}
    if "--official" in sys.argv:
        res["official"] = official_eval(sys.argv[sys.argv.index("--official") + 1], date)
    (DER / f"eval_{date}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    s12 = res["seoul_12h"]
    print(f"## 오차표 {date} (레코드 {len(recs)})\n\n### 1. 서울시 12h 인구 예측 (기준선)  MAPE={s12['mape']} · 범위 포함률={s12['range_hit']}")
    print(md_table(s12["rows"][:14], ["시각", "실측", "예측중앙", "APE", "리드(분)"], ["t", "actual", "pred_mid", "ape", "lead_min"]))
    print("### 2. 우리 스냅샷 (α [p10,p50,p90] · 21시 유출)")
    print(md_table(res["our_snapshots"][:14], ["시각", "α", "관측수", "21시 유출"], ["at", "alpha", "n_obs", "out21"]))
    ss = res["subway_shape"]
    print(f"### 3. 지하철 형태  상관={ss['pearson']} · 피크 실측 {ss['peak_obs']}시 vs 예측 {ss['peak_pred']}시  ({ss['note']})")
    if "official" in res:
        o = res["official"]
        print("### 4. 공식 승하차 확정판:", o.get("error") or f"|오차|/실측={o['total']['err_abs_over_obs']} · 등급 적중={o['total']['grade_hit_rate']} · 밴드 포함={o['total']['band_hit_rate']}")
    print("→", DER / f"eval_{date}.json")


if __name__ == "__main__":
    main()
