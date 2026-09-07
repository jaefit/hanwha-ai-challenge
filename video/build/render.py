#!/usr/bin/env python3
"""원본 영상(소리 버림) + work/voice.wav + 자막 PNG overlay → 최종 mp4.

사용  render.py SRC.mp4 OUT.mp4 [--extend] [--crf 20] [--size-mb 0]
      work/remap.json 이 있으면(tts.py hold 모드) 원본을 구간별로 잘라 각 구간 끝을 hold 초만큼 정지로
      붙잡아 이어 붙인다. 없으면 원본을 그대로 쓴다.
      --extend    (remap 없을 때) 음성이 영상보다 길면 마지막 프레임을 그만큼 늘린다(tpad clone)
      --size-mb   0 보다 크면 그 크기에 맞춰 2-pass 비트레이트 인코딩(crf 무시)

자막은 큐마다 PNG 한 장을 입력으로 넣고 overlay 의 enable=between(t,s,e) 로 켠다. 큐 60개 안팎이면
ffmpeg 가 한 번에 처리한다. 위치는 가로 중앙, 아래 여백 BOTTOM px.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
BOTTOM = 14     # 프레임 베젤·월페이퍼 띠 위. 한 줄 박스(62px)가 화면 내용을 12px 만 덮는다
HEIGHT = 1080


def duration(path: Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(path)])
    return float(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--extend", action="store_true")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--size-mb", type=float, default=0)
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subs = json.loads((WORK / "subs.json").read_text(encoding="utf-8"))
    voice = json.loads((WORK / "voice.json").read_text(encoding="utf-8"))
    vlen = duration(src)
    remap_path = WORK / "remap.json"
    remap = json.loads(remap_path.read_text(encoding="utf-8")) if remap_path.exists() else None
    if remap:
        total = sum(r["src_end"] - r["src_start"] + r["hold"] for r in remap)
        extra = 0.0
    else:
        extra = max(0.0, voice["audio_end"] + 0.5 - vlen)
        if extra > 0 and not args.extend:
            print(f"경고: 음성이 영상 끝을 {extra:.1f}s 넘는다. --extend 없이는 잘린다", file=sys.stderr)
        total = vlen + (extra if args.extend else 0)

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats", "-y", "-i", str(src), "-i", str(WORK / "voice.wav")]
    for s in subs:
        cmd += ["-i", s["png"]]

    chain = []
    cur = "[0:v]"
    if remap:
        segs = []
        for i, r in enumerate(remap):
            seg = f"[0:v]trim=start={r['src_start']:.3f}:end={r['src_end']:.3f},setpts=PTS-STARTPTS"
            if r["hold"] > 0:
                seg += f",tpad=stop_mode=clone:stop_duration={r['hold']:.3f}"
            chain.append(f"{seg}[s{i}]")
            segs.append(f"[s{i}]")
        chain.append(f"{''.join(segs)}concat=n={len(segs)}:v=1:a=0[v0]")
        cur = "[v0]"
    elif args.extend and extra > 0:
        chain.append(f"{cur}tpad=stop_mode=clone:stop_duration={extra:.3f}[v0]")
        cur = "[v0]"
    for i, s in enumerate(subs):
        y = HEIGHT - BOTTOM - s["h"]
        nxt = f"[v{i + 1}]"
        chain.append(f"{cur}[{i + 2}:v]overlay=(W-w)/2:{y}:enable='between(t,{s['start']:.3f},{s['end']:.3f})'{nxt}")
        cur = nxt
    chain.append(f"{cur}format=yuv420p[vout]")

    common = ["-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "1:a",
              "-t", f"{total:.3f}", "-r", "24", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
    if args.size_mb > 0:
        # 목표 크기에서 오디오 몫을 뺀 영상 비트레이트, 2-pass
        vbit = int((args.size_mb * 8 * 1024 * 1024 * 0.96) / total - 128 * 1024)
        log = str(WORK / "x264")
        p1 = cmd + common + ["-c:v", "libx264", "-preset", "slow", "-b:v", str(vbit), "-pass", "1",
                             "-passlogfile", log, "-an", "-f", "mp4", "/dev/null"]
        p2 = cmd + common + ["-c:v", "libx264", "-preset", "slow", "-b:v", str(vbit), "-pass", "2",
                             "-passlogfile", log, str(out)]
        subprocess.run(p1, check=True)
        subprocess.run(p2, check=True)
    else:
        subprocess.run(cmd + common + ["-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), str(out)], check=True)

    size = out.stat().st_size / 1024 / 1024
    holds = sum(r["hold"] for r in remap) if remap else (extra if args.extend else 0)
    print(f"\n{out}  {duration(out):.1f}s  {size:.1f}MB  자막 {len(subs)}개  정지 합계 {holds:.1f}s")


if __name__ == "__main__":
    main()
