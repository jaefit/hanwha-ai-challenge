#!/usr/bin/env python3
"""녹음 전사. mlx-whisper large-v3-turbo, 한국어, 단어 타임스탬프.  asr.py IN.wav OUT.json"""
import json
import sys

import mlx_whisper

PROMPT = "불꽃배웅 소개 영상. 여의나루역, 이벤트광장, 스냅샷, 출구 상태판, 혼잡도, 운영 화면, 관람객 화면."

src, dst = sys.argv[1], sys.argv[2]
r = mlx_whisper.transcribe(src, path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language="ko",
                           word_timestamps=True, initial_prompt=PROMPT)
json.dump(r, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for sg in r["segments"]:
    print(f'{sg["start"]:7.2f} {sg["end"]:7.2f} {sg["text"].strip()}')
