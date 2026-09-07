#!/usr/bin/env python3
"""블록별 TTS(edge-tts Hyunsu)를 녹음 타임라인의 슬롯에 맞춰 만들고 한 트랙으로 잇는다.

입력  work/timeline.json     timeline.py 산출
      video/script_v2_read.md
      --mode hold (기본)      자연 속도. 블록 대사가 화면 구간보다 길면 그만큼 구간 마지막 프레임을
                              정지로 붙잡는다(work/remap.json → render.py). 영상은 길어지고 잘리지 않는다.
      --mode fit --groups "1-6,7-11,12"
                              같은 말 속도를 쓰는 블록 묶음. 묶음 안 블록은 첫 블록 시작 시각부터
                              GAP 초 간격으로 이어 붙이고, 묶음 전체가 그 구간(첫 블록 시작 → 다음
                              묶음 첫 블록 시작)에 들어가도록 edge 의 rate 를 고른다.
출력  work/tts/bN.mp3         블록별 음성 (fit 모드면 rate 적용, 필요하면 atempo 잔여 보정)
      work/cues.json          단어 단위 절대 시각 [{n, text, start, end}] — 출력 타임라인 기준
      work/remap.json         hold 모드: [{src_start, src_end, hold}] 원본 구간과 정지 길이
      work/voice.wav          48k 스테레오, loudnorm -16 LUFS, 길이 = max(영상, 음성 끝)
      stdout                  블록별 자연 길이·슬롯·적용 rate·최종 길이 표. 음성이 영상보다 길면 경고

edge 의 rate 는 프로소디를 유지하는 속도 조절이라 atempo 보다 자연스럽다. rate 상한을 넘겨야
들어가는 묶음은 표에 '초과'로 남기고 atempo 로 마저 맞춘다(상한 ATEMPO_MAX).
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
TTS_DIR = WORK / "tts"
SCRIPT = ROOT / "script_v2_read.md"

VOICE = "ko-KR-HyunsuMultilingualNeural"
GAP = 0.35            # 묶음 안 블록 사이 무음(초)
RATE_MAX = 30         # edge rate 상한(%)
RATE_MIN = -10
ATEMPO_MAX = 1.08     # edge 로 못 맞춘 잔여를 atempo 로 보정하는 상한
VIDEO_LEN = 210.0     # 원본 영상 길이(초). render 가 실제 값으로 덮어쓴다


def load_blocks():
    text = SCRIPT.read_text(encoding="utf-8")
    blocks = {}
    for m in re.finditer(r"^## (\d+) (.+?)\n(.+?)(?=\n## |\Z)", text, re.M | re.S):
        body = m.group(3).strip()
        if "[" in body:
            sys.exit(f"블록 {m.group(1)} 에 [ ] 자리가 남아 있다 — 화면 값으로 채운 뒤 다시 돌릴 것")
        blocks[int(m.group(1))] = {"title": m.group(2).strip(), "text": body}
    return blocks


def parse_groups(spec: str):
    groups = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        a = int(a)
        b = int(b) if b else a
        groups.append(list(range(a, b + 1)))
    return groups


def duration(path: Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(path)])
    return float(out)


async def synth(text: str, rate: int, out: Path):
    """mp3 + WordBoundary 목록(초 단위, 파일 내 상대 시각)."""
    sign = "+" if rate >= 0 else "-"
    com = edge_tts.Communicate(text, VOICE, rate=f"{sign}{abs(rate)}%", boundary="WordBoundary")
    words = []
    with open(out, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"text": chunk["text"], "start": chunk["offset"] / 1e7,
                              "end": (chunk["offset"] + chunk["duration"]) / 1e7})
    return words


def atempo(src: Path, dst: Path, factor: float):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                    "-filter:a", f"atempo={factor:.4f}", str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["hold", "fit"], default="hold")
    ap.add_argument("--groups", default="1-6,7-11,12")
    ap.add_argument("--video-len", type=float, default=VIDEO_LEN)
    args = ap.parse_args()

    blocks = load_blocks()
    tl = {r["n"]: r for r in json.loads((WORK / "timeline.json").read_text(encoding="utf-8"))}
    groups = parse_groups(args.groups)
    TTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1) 자연 속도 길이
    natural = {}
    for n, b in blocks.items():
        p = TTS_DIR / f"nat{n}.mp3"
        asyncio.run(synth(b["text"], 0, p))
        natural[n] = duration(p)

    cues, placed = [], {}
    audio_end = 0.0
    remap_path = WORK / "remap.json"
    if args.mode == "hold":
        # 자연 속도(nat 파일 그대로). 출력 시각 = 앞 블록들의 max(슬롯, 대사+GAP) 누적
        remap, out_t = [], 0.0
        first = tl[min(tl)]["start"]
        if first > 0:
            remap.append({"src_start": 0.0, "src_end": first, "hold": 0.0})
            out_t = first
        print(f"{'n':>2} {'자연':>6} {'슬롯':>6} {'정지':>6} {'시작':>7} {'끝':>7}  제목")
        for n in sorted(tl):
            src_s = tl[n]["start"]
            src_e = tl[n]["slot_end"] or args.video_len
            slot = src_e - src_s
            p = TTS_DIR / f"nat{n}.mp3"
            words = asyncio.run(synth(blocks[n]["text"], 0, p))
            d = duration(p)
            hold = max(0.0, d + GAP - slot)
            placed[n] = {"path": p, "start": out_t, "end": out_t + d}
            for w in words:
                cues.append({"n": n, "text": w["text"], "start": round(out_t + w["start"], 3), "end": round(out_t + w["end"], 3)})
            remap.append({"src_start": round(src_s, 3), "src_end": round(src_e, 3), "hold": round(hold, 3)})
            print(f"{n:>2} {d:6.1f} {slot:6.1f} {hold:6.1f} {out_t:7.2f} {out_t + d:7.2f}  {tl[n]['title']}")
            audio_end = out_t + d
            out_t += slot + hold
        remap_path.write_text(json.dumps(remap, ensure_ascii=False, indent=1), encoding="utf-8")
        total_video = out_t
        print(f"\n출력 영상 {total_video:.1f}s (원본 {args.video_len:.1f}s + 정지 {total_video - args.video_len:.1f}s) · 음성 끝 {audio_end:.1f}s")
        args.video_len = total_video
        groups = []
    elif remap_path.exists():
        remap_path.unlink()

    # 2) fit 모드: 묶음별 rate 결정 → 생성 → 배치
    if groups:
        print(f"{'n':>2} {'자연':>6} {'슬롯':>6} {'rate':>5} {'최종':>6} {'시작':>7} {'끝':>7}  비고")
    for gi, g in enumerate(groups):
        region_start = tl[g[0]]["start"]
        region_end = tl[groups[gi + 1][0]]["start"] if gi + 1 < len(groups) else args.video_len
        region = region_end - region_start
        need = sum(natural[n] for n in g) + GAP * (len(g) - 1)
        ratio = need / region
        rate = int(round((ratio - 1) * 100)) if ratio > 1 else max(RATE_MIN, int(round((ratio - 1) * 100)))
        rate = max(RATE_MIN, min(RATE_MAX, rate))

        # edge rate 의 실제 배율은 비선형이라 한 번 더 잰다
        gen = {}
        for n in g:
            p = TTS_DIR / f"b{n}.mp3"
            gen[n] = (p, asyncio.run(synth(blocks[n]["text"], rate, p)), duration(p))
        got = sum(gen[n][2] for n in g) + GAP * (len(g) - 1)
        if got > region + 0.05 and rate < RATE_MAX:
            rate = min(RATE_MAX, rate + int(round((got / region - 1) * 100)) + 1)
            for n in g:
                p = TTS_DIR / f"b{n}.mp3"
                gen[n] = (p, asyncio.run(synth(blocks[n]["text"], rate, p)), duration(p))
            got = sum(gen[n][2] for n in g) + GAP * (len(g) - 1)

        factor = 1.0
        note = ""
        if got > region + 0.05:
            factor = min(ATEMPO_MAX, got / region)
            note = f"초과 {got - region:+.1f}s → atempo {factor:.3f}"
            if got / factor > region + 0.05:
                note += f" 그래도 {got / factor - region:+.1f}s 남음"

        t = region_start
        for n in g:
            p, words, d = gen[n]
            if factor != 1.0:
                q = TTS_DIR / f"b{n}_fit.mp3"
                atempo(p, q, factor)
                p, d = q, duration(q)
                words = [{"text": w["text"], "start": w["start"] / factor, "end": w["end"] / factor} for w in words]
            placed[n] = {"path": p, "start": t, "end": t + d}
            for w in words:
                cues.append({"n": n, "text": w["text"], "start": round(t + w["start"], 3), "end": round(t + w["end"], 3)})
            slot = (tl[n]["slot_end"] or tl[n]["end"]) - tl[n]["start"]
            print(f"{n:>2} {natural[n]:6.1f} {slot:6.1f} {rate:+4d}% {d:6.1f} {t:7.2f} {t + d:7.2f}  {note if n == g[0] else ''}")
            t += d + GAP
        audio_end = max(audio_end, t - GAP)

    (WORK / "cues.json").write_text(json.dumps(cues, ensure_ascii=False, indent=0), encoding="utf-8")

    # 3) 한 트랙으로: adelay → amix(normalize=0) → apad → loudnorm
    total = max(args.video_len, audio_end + 0.5)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for n in sorted(placed):
        cmd += ["-i", str(placed[n]["path"])]
    parts = []
    for i, n in enumerate(sorted(placed)):
        ms = int(round(placed[n]["start"] * 1000))
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(placed)))
    parts.append(f"{mix}amix=inputs={len(placed)}:normalize=0:duration=longest,apad,atrim=0:{total:.3f},"
                 f"loudnorm=I=-16:TP=-1.5:LRA=11[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "48000", str(WORK / "voice.wav")]
    subprocess.run(cmd, check=True)
    (WORK / "voice.json").write_text(json.dumps({"audio_end": round(audio_end, 3), "total": round(total, 3),
                                                 "video_len": args.video_len}, indent=1), encoding="utf-8")
    print(f"음성 끝 {audio_end:.1f}s · 트랙 길이 {total:.1f}s · 영상 {args.video_len:.1f}s")
    if args.mode == "fit" and audio_end > args.video_len + 0.05:
        print(f"경고: 음성이 영상보다 {audio_end - args.video_len:.1f}s 길다 — render.py --extend 로 마지막 프레임을 늘리거나 대본을 줄일 것")


if __name__ == "__main__":
    main()
