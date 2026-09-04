#!/bin/zsh
# 수집 파이프라인 한눈 점검 — 런북(runbook_20260904.md)의 매 시각 확인 항목을 한 번에 찍는다.
#   ./tools/status.sh
# 작성 2026-09-04. 읽기만 한다. 아무것도 바꾸지 않는다.
cd "$(dirname "$0")/.."
now=$(date +%s)
age() { [ -f "$1" ] && echo $(( (now - $(stat -f %m "$1")) / 60 )) || echo "-" }

print -- "== $(date '+%m-%d %H:%M:%S') =="
print -- "전원   : $(pmset -g batt | sed -n 1p | sed 's/Now drawing from //')  $(pmset -g batt | sed -n 2p | awk '{print $3, $4}')"
print -- "슬립막음: $(pmset -g assertions 2>/dev/null | grep -c 'PreventUserIdleSystemSleep.*caffeinate')건 (caffeinate)"
for n in run_all.sh collector_api.py collector_cctv.py "caffeinate -dims"; do
  c=$(pgrep -f "$n" | wc -l | tr -d ' '); print -- "프로세스: $n $c"
done
print -- "api_last_ok : $(cat data/live/api_last_ok 2>/dev/null)  ($(age data/live/api_last_ok)분 전)  — 10분 넘으면 수집 끊김"
print -- "api jsonl   : data/live/api_$(date +%Y%m%d).jsonl $(age data/live/api_$(date +%Y%m%d).jsonl)분 전"
print -- "cctv jsonl  : data/live/cctv_$(date +%Y%m%d).jsonl $(age data/live/cctv_$(date +%Y%m%d).jsonl)분 전"
print -- "마지막 발행 : $(tail -1 logs/publish.log 2>/dev/null)"
print -- "발행 실패   : $(grep -c '발행 실패' logs/publish.log 2>/dev/null)건 누적"
print -- "워치독 마지막: $(tail -1 logs/watchdog.log 2>/dev/null)"
print -- "재기동 오늘 : $(grep "^$(date +%m-%d)" logs/watchdog.log 2>/dev/null | grep -c WATCHDOG)건"
.venv/bin/python - <<'PY' 2>/dev/null
import json, datetime
d = json.load(open("docs/data/latest.json")); f = d["forecast"]
ok = sum(1 for v in d.get("cctv", {}).values() if v.get("ok"))
print(f"latest.json : {d['generated']}  degraded={f.get('degraded_sources')}  α={f.get('alpha')}({f.get('alpha_reason','')[:30]})  prior={f.get('prior')}")
print(f"CCTV ok     : {ok}/{len(d.get('cctv', {}))}  show_end={f.get('show_end_actual')} ({f.get('show_end_source')})")
# 시간 공백 — 오늘 api jsonl 의 연속 레코드 간격이 10분을 넘는 구간 (슬립의 흔적)
import pathlib, itertools
p = pathlib.Path(f"data/live/api_{datetime.date.today():%Y%m%d}.jsonl")
ts = []
if p.exists():
    for line in p.read_text(encoding="utf-8").splitlines():
        try: ts.append(datetime.datetime.fromisoformat(json.loads(line)["ts"][:19]))
        except Exception: pass
ts = sorted(set(t.replace(second=0) for t in ts))
gaps = [(a, b) for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 600]
print("시간 공백   : " + ("없음" if not gaps else " · ".join(f"{a:%H:%M}→{b:%H:%M}" for a, b in gaps)))
PY
print -- "Pages       : https://jaefit.github.io/hanwha-ai-challenge/go.html  (필 「실시간」이어야 정상)"
