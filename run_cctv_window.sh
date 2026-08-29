#!/bin/zsh
# CCTV 수집기를 지정 시각에 시작해 N분 돌리고 끝낸다 (야간 테스트·전야제 리허설용). 끝나면 요약을 로그에 남긴다. 맥 슬립 방지(caffeinate).
#   ./run_cctv_window.sh 20:00 60                 # 오늘 20:00 부터 60분, 23대 전부
#   CAMS=192,725,310,331 ./run_cctv_window.sh 20:00 30
# 뚜껑을 닫으면 caffeinate 로도 못 막는다. 전원 연결·뚜껑 열어 둘 것.
cd "$(dirname "$0")"
mkdir -p logs
START=$1; MIN=${2:-60}
[ -z "$START" ] && { echo "usage: $0 HH:MM [minutes]"; exit 1; }
now=$(date +%s); target=$(date -j -f "%Y-%m-%d %H:%M" "$(date +%Y-%m-%d) $START" +%s)
[ $target -le $now ] && target=$((target + 86400))
wait=$((target - now))
echo "$(date '+%Y-%m-%d %H:%M:%S') 대기 ${wait}s → ${START} 시작, ${MIN}분 수집 (cams=${CAMS:-all})"
caffeinate -dims -w $$ &
sleep $wait
CAMS_ARG=(); [ -n "$CAMS" ] && CAMS_ARG=(--cams "$CAMS")
LOG=logs/cctv_window_$(date +%Y%m%d_%H%M).log
echo "$(date '+%H:%M:%S') 수집 시작 → $LOG"
INTERVAL=${CCTV_INTERVAL:-60} .venv/bin/python src/collector_cctv.py "${CAMS_ARG[@]}" >> "$LOG" 2>&1 &
P=$!
sleep $((MIN * 60)); kill $P 2>/dev/null
echo "$(date '+%H:%M:%S') 수집 종료. 요약:"
.venv/bin/python src/cctv_summary.py --from "$START" --minutes "$MIN"
