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
n_sub = len([k for k in env if k.startswith("SEOUL_KEY_SUBWAY") and env[k]])
n_feed = len([k for k in env if k.startswith("SEOUL_KEY_FEEDER") and env[k]])
# 일 한도 1,000 은 실시간 지하철 인증키만(열린데이터광장 이용방법, 2026-09-02 확인). 피더키는 없으면 일반키로 수집한다.
print(f"키 점검 ok — 지하철 키 {n_sub}개(실시간 도착 336회/일 회전) · 피더키 {n_feed}개" + ("" if n_feed else " (없음 → 피더·관람지도 일반키)"))
PY

caffeinate -dims & CAF=$!

start_api()  { FEEDERS=${FEEDERS:-default} .venv/bin/python src/collector_api.py >> logs/api.log 2>&1 & P1=$! }
start_cctv() { INTERVAL=${CCTV_INTERVAL:-60} .venv/bin/python src/collector_cctv.py "${CAMS_ARG[@]}" >> logs/cctv.log 2>&1 & P2=$! }
start_loop() { ( while true; do .venv/bin/python src/nowcast.py >> logs/nowcast.log 2>&1; .venv/bin/python src/publish.py >> logs/publish.log 2>&1; sleep 300; done ) & P3=$! }

# FEEDERS=default = 피더 12곳(선행지표, 12~19시) · WATCH 기본값 = 강 건너 관람 명당 6곳(17~23시). 키별 예산은 --budget 로 확인
start_api; start_cctv; start_loop
log "running: api=$P1 cctv=$P2 nowcast/publish=$P3 caffeinate=$CAF  (logs/ 에 기록)"

RUN=1
trap 'RUN=0; kill $P1 $P2 $P3 $CAF $SLP 2>/dev/null; log "stopped"; exit 0' INT TERM

if [ "${WATCHDOG:-1}" = "0" ]; then wait; exit 0; fi

# 수집기가 뜨자마자 죽는 크래시 루프면 30초마다 재기동 = 5분 주기의 10배로 API 쿼터를 태운다.
# 창(기본 10분) 안에서 재기동이 MAX 를 넘으면 재시도 간격을 5분(정상 틱 주기)으로 늘린다. 자가복구는 유지한다.
WD_POLL=${WD_POLL:-30}; WD_WINDOW=${WD_WINDOW:-600}; WD_BACKOFF=${WD_BACKOFF:-300}; MAX_RESTARTS=${MAX_RESTARTS:-5}
RESTARTS=0; WIN_START=$(date +%s); LAST_TRY=0; BACKOFF=0

allow_restart() {
  local now=$(date +%s)
  if (( now - WIN_START > WD_WINDOW )); then RESTARTS=0; WIN_START=$now; BACKOFF=0; fi
  if (( RESTARTS >= MAX_RESTARTS )); then
    if (( BACKOFF == 0 )); then
      BACKOFF=1
      log "WATCHDOG: ${WD_WINDOW}초 안에 재기동 ${RESTARTS}회 — 크래시 루프로 보고 재시도 간격을 ${WD_BACKOFF}초로 늘린다 (API 쿼터 보호). logs/api.log·logs/cctv.log 확인할 것";
    fi
    (( now - LAST_TRY < WD_BACKOFF )) && return 1;
  fi
  RESTARTS=$((RESTARTS + 1)); LAST_TRY=$now; return 0
}

STALE_WARNED=0
while (( RUN )); do
  # 2026-09-02 L5: 맨 `sleep` 은 zsh 트랩을 삼켜 Ctrl+C 후 정지까지 최대 WD_POLL 초가 걸린다(실측 38초).
  # 현장에서 반응이 없다고 한 번 더 누르면 트랩이 버려지고 수집기·caffeinate 가 고아로 남는다.
  # 배경으로 돌리고 wait 하면 wait 가 시그널에 깨므로 즉시 트랩이 돈다.
  sleep $WD_POLL & SLP=$!; wait $SLP
  (( RUN )) || break
  if ! kill -0 $P1 2>/dev/null; then
    if allow_restart; then log "WATCHDOG: collector_api 사망 → 재기동 (직전 로그: $(tail -1 logs/api.log))"; start_api; log "  새 pid=$P1"; fi
  fi
  if ! kill -0 $P2 2>/dev/null; then
    if allow_restart; then log "WATCHDOG: collector_cctv 사망 → 재기동 (직전 로그: $(tail -1 logs/cctv.log))"; start_cctv; log "  새 pid=$P2"; fi
  fi
  if ! kill -0 $P3 2>/dev/null; then
    if allow_restart; then log "WATCHDOG: nowcast/publish 루프 사망 → 재기동"; start_loop; log "  새 pid=$P3"; fi
  fi
  # 프로세스는 살아 있는데 데이터가 안 자라는 경우 (API 무응답·쿼터 소진 등) — 죽음보다 잡기 어렵다
  F="data/live/api_$(date +%Y%m%d).jsonl"
  if [ -f "$F" ]; then
    AGE=$(( $(date +%s) - $(stat -f %m "$F") ))
    if (( AGE > 600 )); then
      (( STALE_WARNED )) || log "WATCHDOG 경고: $F 가 ${AGE}초째 그대로다 — logs/api.log 확인 (쿼터·키·네트워크)"
      STALE_WARNED=1
    else
      STALE_WARNED=0;
    fi
  fi
done
