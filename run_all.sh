#!/bin/zsh
# 축제 당일 실행기: API 5분 + CCTV 60초 + 나우캐스트·발행 5분. 맥 슬립 방지(caffeinate).
#   ./run_all.sh            # 전부 실행 (Ctrl+C 로 종료)
#   CAMS=192,725,310,331,39 ./run_all.sh   # CCTV 일부만
cd "$(dirname "$0")"
mkdir -p data/live logs
CAMS_ARG=(); [ -n "$CAMS" ] && CAMS_ARG=(--cams "$CAMS")
caffeinate -dims &
CAF=$!
# FEEDERS=default = 피더 12곳(선행지표, 12~19시) · WATCH 기본값 = 강 건너 관람 명당 6곳(17~23시). 키별 예산은 --budget 로 확인
FEEDERS=${FEEDERS:-default} .venv/bin/python src/collector_api.py >> logs/api.log 2>&1 &
P1=$!
INTERVAL=${CCTV_INTERVAL:-60} .venv/bin/python src/collector_cctv.py "${CAMS_ARG[@]}" >> logs/cctv.log 2>&1 &
P2=$!
( while true; do .venv/bin/python src/nowcast.py >> logs/nowcast.log 2>&1; .venv/bin/python src/publish.py >> logs/publish.log 2>&1; sleep 300; done ) &
P3=$!
echo "running: api=$P1 cctv=$P2 nowcast/publish=$P3 caffeinate=$CAF  (logs/ 에 기록)"
trap "kill $P1 $P2 $P3 $CAF 2>/dev/null; echo stopped" INT TERM
wait
