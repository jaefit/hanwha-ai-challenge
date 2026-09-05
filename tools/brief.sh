#!/bin/zsh
# 현장 브리핑 한 장 — 지금 인파·α·출구 순위·CCTV. 읽기만 한다.
#   ./tools/brief.sh
# 작성 2026-09-05 18:05. status.sh(파이프라인 건강)와 짝. 이건 "지금 여의도가 어떤가".
cd "$(dirname "$0")/.."
.venv/bin/python - <<'PY'
import json, datetime, collections, sys
sys.path.insert(0, "src"); import nowcast as N
d = json.load(open("docs/data/latest.json", encoding="utf-8")); f = d["forecast"]
now = datetime.datetime.now(); H = str(now.hour if 19 <= now.hour <= 23 else 21)
snap = f.get("live_snapshot") or {}
def z(k):
    v = snap.get(k) or {}; p = v.get("ppltn") or [None, None]
    return f"{v.get('congest','—')} {p[0]:,}~{p[1]:,}" if p[0] is not None else "—"
park = snap.get("여의도한강공원") or {}
print(f"== 브리핑 {now:%H:%M} · 발행 {d['generated'][11:19]} · 데이터 {park.get('ts','—')[-5:]}(시차 28분) ==")
print(f"행사장  여의도한강공원 {z('여의도한강공원')} · 여의도 {z('여의도')} · 여의서로 {z('여의서로')}")
# 30분 하차 — 오늘 api jsonl 마지막 레코드
rows = [json.loads(l) for l in open(f"data/live/api_{now:%Y%m%d}.jsonl", encoding="utf-8") if l.strip()]
last = [r for r in rows if r.get("kind") == "citydata" and r.get("area") == "여의도한강공원" and "error" not in r]
if last:
    s = last[-1].get("sub_live") or {}
    print(f"지하철  여의나루 30분 하차 {s.get('SUB_30WTHN_GTOFF_PPLTN_MIN','-')}~{s.get('SUB_30WTHN_GTOFF_PPLTN_MAX','-')} · 승차 {s.get('SUB_30WTHN_GTON_PPLTN_MIN','-')}~{s.get('SUB_30WTHN_GTON_PPLTN_MAX','-')}")
a = f.get("assimilation") or {}
print(f"α       {f.get('alpha')} {a.get('alpha') if isinstance(a.get('alpha'), list) else ''} · {f.get('alpha_reason','')[:60]}")
print(f"쇼 종료 {f.get('show_end_actual')} ({f.get('show_end_source')}) · 유출 시프트 +{f.get('show_shift_min')}분")
ex = f.get("exits") or {}
opens = sorted([(v[H]["load"], k, v[H].get("wait_min") or 0) for k, v in ex.items() if H in v and not v[H].get("closed") and v[H].get("load") is not None])
closed = [k for k, v in ex.items() if H in v and v[H].get("closed")]
grade = lambda x: "심각" if x >= 1 else "경계" if x >= .8 else "주의" if x >= .5 else "여유"
SH = {"여의도(5)": "여의도5", "여의도(9)": "여의도9", "여의나루(5)": "여의나루", "신길(1·5)": "신길", "샛강(9)": "샛강", "국회의사당(9)": "국회", "마포역 도보(마포대교)": "마포도보"}
print(f"{H}시 출구  " + " · ".join(f"{SH.get(k, k)} {l:.2f}{grade(l)}" + (f"+대기{w}분" if w else "") for l, k, w in opens[:7]) + (f" · 통제 {','.join(SH.get(c, c) for c in closed)}" if closed else ""))
cams = d.get("cctv") or {}
lv = collections.Counter(v.get("level") for v in cams.values() if v.get("ok"))
hot = [f"{v['name']}({v['level']})" for v in cams.values() if v.get("level") in ("경계", "심각")]
flags = sum(1 for v in cams.values() if v.get("flags"))
print(f"CCTV    ok {sum(1 for v in cams.values() if v.get('ok'))}/{len(cams)} · " + " ".join(f"{k}{n}" for k, n in sorted(lv.items(), key=lambda x: -x[1]) if k) + (f" · 경계 이상: {', '.join(hot)}" if hot else "") + (f" · 플래그 {flags}대" if flags else ""))
al = f.get("alerts_live") or []
def amsg(x):
    if not isinstance(x, dict): return str(x)[:70]
    return (x.get("ACDNT_INFO") or x.get("ACDNT_DTYPE") or x.get("ACDNT_TYPE") or str(x))[:70] + f" ({str(x.get('ACDNT_OCCR_DT',''))[11:16]}~)"
if al: print(f"알림 {len(al)}건 " + " / ".join(amsg(x) for x in al[-3:]))
PY
