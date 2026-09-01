#!/bin/zsh
# 축제 당일 실행기: API 5분 + CCTV 60초 + 나우캐스트·발행 5분. 맥 슬립 방지(caffeinate).
#   ./run_all.sh            # 전부 실행 (Ctrl+C 로 종료)
#   CAMS=192,725,310,331,39 ./run_all.sh   # CCTV 일부만
#   WATCHDOG=0 ./run_all.sh                # 감시 끄기 (디버깅용)
#
# 2026-09-01 red team C3: 전에는 프로세스가 죽어도 재기동·경보가 없어 대시보드가 조용히 얼어붙었다.
# 이제 30초마다 세 프로세스 생존을 확인하고, 죽었으면 재기동한다. 수집 로그가 10분 넘게 안 자라도 경고한다.
cd "$(dirname "$0")"
mkdir -p data/live logs
CAMS_ARG=(); [ -n "$CAMS" ] && CAMS_ARG=(--cams "$CAMS")

log() { print -r -- "$(date '+%m-%d %H:%M:%S') $*" | tee -a logs/watchdog.log }

# ── 시작 전 점검: .env 키 (다른 기기에서 키가 빠진 채 돌리면 임포트 시점에 죽는다) ──
.venv/bin/python - <<'PY' || exit 1
import pathlib, sys
env = {}
p = pathlib.Path(".env")
if not p.exists():
    print("중단: .env 가 없다. 키를 채운 뒤 다시 실행할 것.", file=sys.stderr); sys.exit(1)
for line in p.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); env[k.strip()] = v.strip()
need = ["SEOUL_KEY_GENERAL", "SEOUL_KEY_SUBWAY"]
missing = [k for k in need if not env.get(k)]
if missing:
    print(f"중단: .env 필수 키 없음 — {', '.join(missing)}", file=sys.stderr); sys.exit(1)
opt = [k for k in ("SEOUL_KEY_FEEDER", "SEOUL_KEY_FEEDER2") if not env.get(k)]
n_sub = len([k for k in env if k.startswith("SEOUL_KEY_SUBWAY") and env[k]])
print(f"키 점검 ok — 지하철 키 {n_sub}개" + (f" · 없는 선택 키: {', '.join(opt)}" if opt else ""))
PY

caffeinate -dims & CAF=$!

start_api()  { FEEDERS=${FEEDERS:-default} .venv/bin/python src/collector_api.py >> logs/api.log 2>&1 & P1=$! }
start_cctv() { INTERVAL=${CCTV_INTERVAL:-60} .venv/bin/python src/collector_cctv.py "${CAMS_ARG[@]}" >> logs/cctv.log 2>&1 & P2=$! }
start_loop() { ( while true; do .venv/bin/python src/nowcast.py >> logs/nowcast.log 2>&1; .venv/bin/python src/publish.py >> logs/publish.log 2>&1; sleep 300; done ) & P3=$! }

# FEEDERS=default = 피더 12곳(선행지표, 12~19시) · WATCH 기본값 = 강 건너 관람 명당 6곳(17~23시). 키별 예산은 --budget 로 확인
start_api; start_cctv; start_loop
log "running: api=$P1 cctv=$P2 nowcast/publish=$P3 caffeinate=$CAF  (logs/ 에 기록)"

RUN=1
trap 'RUN=0; kill $P1 $P2 $P3 $CAF 2>/dev/null; log "stopped"; exit 0' INT TERM

if [ "${WATCHDOG:-1}" = "0" ]; then wait; exit 0; fi

STALE_WARNED=0
while (( RUN )); do
  sleep 30
  (( RUN )) || break
  kill -0 $P1 2>/dev/null || { log "WATCHDOG: collector_api 사망 → 재기동 (직전 로그: $(tail -1 logs/api.log))"; start_api; log "  새 pid=$P1" }
  kill -0 $P2 2>/dev/null || { log "WATCHDOG: collector_cctv 사망 → 재기동 (직전 로그: $(tail -1 logs/cctv.log))"; start_cctv; log "  새 pid=$P2" }
  kill -0 $P3 2>/dev/null || { log "WATCHDOG: nowcast/publish 루프 사망 → 재기동"; start_loop; log "  새 pid=$P3" }
  # 프로세스는 살아 있는데 데이터가 안 자라는 경우 (API 무응답·쿼터 소진 등) — 죽음보다 잡기 어렵다
  F="data/live/api_$(date +%Y%m%d).jsonl"
  if [ -f "$F" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$F") ))
    if (( AGE > 600 )); then
      (( STALE_WARNED )) || log "WATCHDOG 경고: $F 가 ${AGE}초째 그대로다 — logs/api.log 확인 (쿼터·키·네트워크)"
      STALE_WARNED=1
    else
      STALE_WARNED=0
    fi
  fi
done
