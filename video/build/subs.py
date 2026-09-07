#!/usr/bin/env python3
"""단어 시각(cues.json)을 자막 큐로 묶고, 큐마다 PNG 를 그린다. ffmpeg 에 libass 가 없어 overlay 로 얹는다.

입력  work/cues.json          tts.py 산출 (edge WordBoundary, 절대 시각)
      video/script_v2_read.md 문장부호가 있는 원문 — 큐를 문장 단위로 끊는 기준
출력  work/subs/cNNN.png      큐 이미지 (투명 배경, 가로 1920)
      work/subs.json          [{start, end, png, h, text}]
      work/subs.srt           같은 큐, 플레이어용 sidecar

큐 규칙: 문장 끝(. ? !)에서 끊고, 한 큐가 MAX_LINES×LINE_MAX 자를 넘으면 쉼표(양쪽 ≥MIN_PIECE 자) → 가운데 띄어쓰기 순으로 나눈다. MERGE_UNDER 자 미만 조각은 다음 큐에 붙인다.
표시 시각은 첫 단어 시작 → 마지막 단어 끝 + TAIL, 다음 큐와 겹치지 않게, 최소 MIN_DUR.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
SUBS = WORK / "subs"
SCRIPT = ROOT / "script_v2_read.md"

FONT = Path.home() / "Library/Fonts/Pretendard-SemiBold.otf"
W = 1920
FONT_SIZE = 38
LINE_H = 50
PAD_X, PAD_Y = 28, 12
RADIUS = 12
BOX_RGBA = (10, 12, 20, 170)
TEXT_RGB = (255, 255, 255)
LINE_MAX = 44          # 한 줄 최대 글자(공백 포함). 자막은 한 줄만 — 화면 카드를 안 가리려고 프레임 아래 띠에 얹는다
MAX_LINES = 1
MIN_PIECE = 8          # 쉼표로 나눌 때 각 조각 최소 글자
MERGE_UNDER = 6        # 이보다 짧은 큐는 다음 큐와 합친다
TAIL = 0.25
MIN_DUR = 0.9
SENT_END = re.compile(r"[.?!]$")


def load_blocks():
    text = SCRIPT.read_text(encoding="utf-8")
    return {int(m.group(1)): m.group(3).strip()
            for m in re.finditer(r"^## (\d+) (.+?)\n(.+?)(?=\n## |\Z)", text, re.M | re.S)}


STRIP = re.compile(r"[\s,.!?‘’'\"…·—\-()]")


def tokens_with_times(block_text: str, words: list):
    """원문 토큰(문장부호 포함)에 edge 단어 시각을 붙인다.

    edge 의 WordBoundary 하나가 토큰 여러 개를 덮을 수 있다("9월 5일에"). 문장부호·공백을 뺀
    글자 수로 토큰을 소비해 가며 맞추고, 한 경계가 덮는 토큰들은 그 경계의 시각을 글자 비례로 나눈다.
    글자 수가 끝까지 안 맞으면 블록 전체를 비례 배분한다.
    """
    toks = block_text.split()
    out, ti = [], 0
    try:
        for w in words:
            need = len(STRIP.sub("", w["text"]))
            group, got = [], 0
            while got < need and ti < len(toks):
                group.append(toks[ti])
                got += len(STRIP.sub("", toks[ti]))
                ti += 1
            if got != need or not group:
                raise ValueError(f"경계 「{w['text']}」 vs 토큰 {group}")
            total = sum(len(STRIP.sub("", t)) for t in group)
            acc = 0
            for t in group:
                s = w["start"] + (w["end"] - w["start"]) * acc / total
                acc += len(STRIP.sub("", t))
                e = w["start"] + (w["end"] - w["start"]) * acc / total
                out.append({"text": t, "start": s, "end": e})
        if ti != len(toks):
            raise ValueError(f"토큰 {len(toks) - ti}개 남음")
        return out
    except ValueError as err:
        print(f"  경고: 토큰 정렬 실패({err}) — 블록 전체 비례 배분", file=sys.stderr)
    t0, t1 = words[0]["start"], words[-1]["end"]
    total = sum(len(t) for t in toks)
    out, acc = [], 0
    for t in toks:
        s = t0 + (t1 - t0) * acc / total
        acc += len(t)
        e = t0 + (t1 - t0) * acc / total
        out.append({"text": t, "start": s, "end": e})
    return out


def wrap(text: str):
    """≤LINE_MAX 자 줄로 나눈다. 2줄 안에 들어가면 그 줄 목록, 아니면 None."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= LINE_MAX:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) == 1 and len(lines[0]) > LINE_MAX:
        return None
    return lines if len(lines) <= MAX_LINES else None


def split_long(toks):
    """2줄에 안 들어가는 문장을 쉼표 → 가운데 띄어쓰기 순으로 나눈다(재귀)."""
    text = " ".join(t["text"] for t in toks)
    if wrap(text) is not None:
        return [toks]
    n = len(toks)
    def piece_len(a, b):
        return len(" ".join(t["text"] for t in toks[a:b]))
    commas = [i + 1 for i, t in enumerate(toks[:-1]) if t["text"].endswith(",")
              and piece_len(0, i + 1) >= MIN_PIECE and piece_len(i + 1, n) >= MIN_PIECE]
    if commas:
        cut = min(commas, key=lambda c: abs(piece_len(0, c) - piece_len(c, n)))
    else:
        cut = min(range(1, n), key=lambda c: abs(piece_len(0, c) - piece_len(c, n)))
    return split_long(toks[:cut]) + split_long(toks[cut:])


def build_cues(blocks, cues_words):
    by_block = {}
    for w in cues_words:
        by_block.setdefault(w["n"], []).append(w)
    out = []
    for n in sorted(by_block):
        toks = tokens_with_times(blocks[n], by_block[n])
        sent, cur = [], []
        for t in toks:
            cur.append(t)
            if SENT_END.search(t["text"]):
                sent.append(cur)
                cur = []
        if cur:
            sent.append(cur)
        for s in sent:
            for piece in split_long(s):
                out.append({"start": piece[0]["start"], "end": piece[-1]["end"] + TAIL,
                            "text": " ".join(t["text"] for t in piece)})
    # 짧은 조각은 다음 큐에 붙인다(한 줄에 들어갈 때만)
    merged = []
    for c in out:
        if merged and len(merged[-1]["text"]) < MERGE_UNDER and wrap(merged[-1]["text"] + " " + c["text"]):
            merged[-1] = {"start": merged[-1]["start"], "end": c["end"], "text": merged[-1]["text"] + " " + c["text"]}
        else:
            merged.append(c)
    out = merged
    # 겹침 제거·최소 길이
    for a, b in zip(out, out[1:]):
        a["end"] = min(a["end"], b["start"] - 0.04)
        if a["end"] - a["start"] < MIN_DUR:
            a["end"] = min(a["start"] + MIN_DUR, b["start"] - 0.04)
    return out


def render(cue, idx, font):
    lines = wrap(cue["text"]) or [cue["text"]]
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [tmp.textlength(l, font=font) for l in lines]
    box_w = int(max(widths)) + PAD_X * 2
    box_h = LINE_H * len(lines) + PAD_Y * 2
    img = Image.new("RGBA", (W, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (W - box_w) // 2
    d.rounded_rectangle([x0, 0, x0 + box_w, box_h], radius=RADIUS, fill=BOX_RGBA)
    for i, (l, w) in enumerate(zip(lines, widths)):
        x = (W - w) / 2
        y = PAD_Y + i * LINE_H + (LINE_H - FONT_SIZE) / 2 - 4
        d.text((x + 1, y + 2), l, font=font, fill=(0, 0, 0, 120))
        d.text((x, y), l, font=font, fill=TEXT_RGB)
    p = SUBS / f"c{idx:03d}.png"
    img.save(p)
    return p, box_h


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    if not FONT.exists():
        sys.exit(f"폰트 없음: {FONT}")
    blocks = load_blocks()
    words = json.loads((WORK / "cues.json").read_text(encoding="utf-8"))
    cues = build_cues(blocks, words)
    SUBS.mkdir(parents=True, exist_ok=True)
    for old in SUBS.glob("c*.png"):
        old.unlink()
    font = ImageFont.truetype(str(FONT), FONT_SIZE)
    rows, srt = [], []
    for i, c in enumerate(cues):
        p, h = render(c, i, font)
        rows.append({"start": round(c["start"], 3), "end": round(c["end"], 3), "png": str(p), "h": h, "text": c["text"]})
        srt.append(f"{i + 1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n")
    (WORK / "subs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (WORK / "subs.srt").write_text("\n".join(srt), encoding="utf-8")
    longest = max(rows, key=lambda r: len(r["text"]))
    print(f"자막 큐 {len(rows)}개 · 가장 긴 큐 {len(longest['text'])}자 「{longest['text']}」")
    for r in rows[:6]:
        print(f"  {r['start']:7.2f}–{r['end']:7.2f}  {r['text']}")
    print("  …")


if __name__ == "__main__":
    main()
