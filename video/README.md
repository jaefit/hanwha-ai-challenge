# 소개 영상 — 대본·TTS·자막 빌드 (2026-09-07)

제출용 소개 영상의 작업 공간. 화면 녹화는 사람이 하고, 소리(TTS)와 자막은 여기 스크립트가 붙인다.

| 파일 | 내용 |
| :-- | :-- |
| `script_v1.md` | 대본 초안(장면표·스냅샷 URL 표) |
| `script_v2_read.md` | **실제 녹화 때 읽은 대본** 12블록. TTS·자막은 이 문장을 그대로 쓴다 |
| `build/` | 빌드 스크립트 5개 (아래) |
| `samples/` | 목소리·속도·자막 미리보기 (git 제외) |
| `work/` | 중간 산출물: 전사·타임라인·블록별 mp3·자막 PNG·voice.wav (git 제외) |
| `out/` | 최종 mp4 (git 제외) |

## 흐름

```
녹화 mp4 ─┬─ asr.py       mlx-whisper 전사(단어 시각)            → work/asr.json
          ├─ timeline.py  전사 ↔ 대본 블록 정렬                   → work/timeline.json
          ├─ tts.py       블록별 Hyunsu TTS, 슬롯에 맞춰 배치      → work/tts/*.mp3 · cues.json · voice.wav
          ├─ subs.py      단어 시각 → 자막 큐 → PNG (Pretendard)   → work/subs/*.png · subs.json · subs.srt
          └─ render.py    원본 프레임 그대로 + voice.wav + PNG overlay → out/*.mp4
```

한 번에: `video/build/run.sh 녹화.mp4 [out.mp4] [--mode fit|hold] [--groups "1-6,7-12"] [--size-mb N]`

- **영상 프레임·길이는 손대지 않는다**(fit 모드, 기본은 이걸 쓴다). 대사가 화면 구간보다 길면 edge-tts 의 rate 로 말 속도를 올려 맞춘다. 묶음(`--groups`) 단위로 같은 속도, 묶음 첫 블록에서 화면과 다시 맞춘다.
- hold 모드는 자연 속도 + 정지 프레임으로 영상을 늘리는 방식. 2026-09-07 사용자 결정으로 쓰지 않는다.
- ffmpeg 에 libass 가 없어 자막은 Pillow 로 그린 PNG 를 `overlay` 로 얹는다. 한 줄, 38px, 프레임 아래 띠에 위치(화면 카드 안 가림).
- 목소리 `ko-KR-HyunsuMultilingualNeural`(edge-tts, 무료). 단어 시각은 `boundary="WordBoundary"` 로 받는다 — 7.2.x 기본은 문장 단위라 지정 필수.

## 2026-09-07 녹화본

`~/Downloads/2팀_2파트.mp4` 1920×1080 · 24fps · 3:30 · 210초에서 의도적으로 끊음. 대본 1,172자, Hyunsu 자연 속도 4:04 → **+19% 로 12블록 전부 209.5초 안**(묶음 1–6 · 7–12). 자막 큐 51개.
