#!/bin/zsh
# 소개 영상 빌드: 녹음본(소리 버림) + Hyunsu TTS + 자막 → video/out/*.mp4
#
#   video/build/run.sh SRC.mp4 [OUT.mp4] [--extend] [--size-mb N] [--groups "1-6,7-11,12"]
#
# 단계  asr(없을 때만) → timeline → tts → subs → render.  work/ 는 gitignore.
# 환경  video/work/.venv (uv, python 3.12: edge-tts · mlx-whisper · pillow). 없으면 만든다.
set -euo pipefail
HERE=${0:a:h}
VIDEO=${HERE:h}
WORK=$VIDEO/work
VENV=$WORK/.venv
PY=$VENV/bin/python

SRC=${1:?원본 mp4 경로}
OUT=${2:-$VIDEO/out/fireworks_intro.mp4}
shift $(( $# >= 2 ? 2 : 1 ))
EXTEND=""; SIZE=0; GROUPS="1-6,7-11,12"; MODE="hold"
while (( $# )); do
  case $1 in
    --extend) EXTEND="--extend";;
    --size-mb) SIZE=$2; shift;;
    --groups) GROUPS=$2; shift;;
    --mode) MODE=$2; shift;;
    *) echo "모르는 옵션 $1" >&2; exit 2;;
  esac
  shift
done

mkdir -p "$WORK"
if [[ ! -x $PY ]]; then
  uv venv -q -p 3.12 "$VENV"
  uv pip install -q -p "$PY" edge-tts mlx-whisper pillow
fi

if [[ ! -f $WORK/asr.json ]]; then
  echo "▶ asr"
  ffmpeg -hide_banner -loglevel error -y -i "$SRC" -vn -ac 1 -ar 16000 "$WORK/rec16k.wav"
  "$PY" "$HERE/asr.py" "$WORK/rec16k.wav" "$WORK/asr.json"
fi

VLEN=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$SRC")
echo "▶ timeline";  "$PY" "$HERE/timeline.py"
echo "▶ tts";       "$PY" "$HERE/tts.py" --mode "$MODE" --groups "$GROUPS" --video-len "$VLEN"
echo "▶ subs";      "$PY" "$HERE/subs.py"
echo "▶ render";    "$PY" "$HERE/render.py" "$SRC" "$OUT" $EXTEND --size-mb "$SIZE"
