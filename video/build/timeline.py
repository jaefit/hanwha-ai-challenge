#!/usr/bin/env python3
"""녹음 전사(ASR, 단어 타임스탬프)와 대본 블록을 정렬해 블록별 시작·끝 시각을 낸다.

입력  work/asr.json            mlx-whisper transcribe 결과 (word_timestamps=True)
      video/script_v2_read.md  '## N 제목' 블록 12개
출력  work/timeline.json       [{n, title, start, end, slot_end, text}]
      stdout                   블록 표 + 대본에 [ ] 자리가 있으면 그 구간에서 ASR 이 들은 말

정렬 방법: 두 글자열(공백·문장부호 제거)을 difflib 로 맞추고, 대본 블록의 첫/끝 글자가
ASR 의 몇 번째 글자에 대응하는지로 단어 시각을 찾는다. 대응이 없는 글자는 앞뒤 대응점
사이를 선형으로 보간한다.
"""
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # video/
WORK = ROOT / "work"
SCRIPT = ROOT / "script_v2_read.md"

STRIP = re.compile(r"[\s,.!?‘’'\"…·—\-()\[\]]")


def norm(s: str) -> str:
    return STRIP.sub("", s)


def load_blocks(path: Path):
    text = path.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"^## (\d+) (.+?)\n(.+?)(?=\n## |\Z)", text, re.M | re.S):
        out.append({"n": int(m.group(1)), "title": m.group(2).strip(), "text": m.group(3).strip()})
    if len(out) != 12:
        sys.exit(f"블록 수가 12가 아니다: {len(out)}")
    return out


def load_words(path: Path):
    asr = json.loads(path.read_text(encoding="utf-8"))
    words = []
    for seg in asr["segments"]:
        for w in seg.get("words", []):
            t = norm(w["word"])
            if t:
                words.append({"text": t, "start": float(w["start"]), "end": float(w["end"])})
    if not words:
        sys.exit("ASR 에 단어 타임스탬프가 없다 — word_timestamps=True 로 다시 돌릴 것")
    return words


def main():
    blocks = load_blocks(SCRIPT)
    words = load_words(WORK / "asr.json")

    # ASR 글자열과 각 글자가 속한 단어 인덱스
    asr_chars, owner = [], []
    for i, w in enumerate(words):
        for ch in w["text"]:
            asr_chars.append(ch)
            owner.append(i)
    asr_str = "".join(asr_chars)

    # 대본 글자열과 각 글자가 속한 블록·블록 안 위치
    script_chars, blk_of = [], []
    spans = []
    for b in blocks:
        t = norm(b["text"])
        spans.append((len(script_chars), len(script_chars) + len(t) - 1))
        for ch in t:
            script_chars.append(ch)
            blk_of.append(b["n"])
    script_str = "".join(script_chars)

    sm = difflib.SequenceMatcher(None, script_str, asr_str, autojunk=False)
    # 대본 글자 인덱스 → ASR 글자 인덱스 (대응된 것만)
    mapping = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            mapping[a + k] = b + k
    ratio = sm.ratio()

    def asr_index(i: int) -> int:
        if i in mapping:
            return mapping[i]
        lo = max((k for k in mapping if k < i), default=None)
        hi = min((k for k in mapping if k > i), default=None)
        if lo is None and hi is None:
            return 0
        if lo is None:
            return max(0, mapping[hi] - (hi - i))
        if hi is None:
            return min(len(asr_str) - 1, mapping[lo] + (i - lo))
        f = (i - lo) / (hi - lo)
        return int(round(mapping[lo] + f * (mapping[hi] - mapping[lo])))

    rows = []
    for b, (s0, s1) in zip(blocks, spans):
        w0 = words[owner[min(asr_index(s0), len(owner) - 1)]]
        w1 = words[owner[min(asr_index(s1), len(owner) - 1)]]
        rows.append({"n": b["n"], "title": b["title"], "start": round(w0["start"], 2),
                     "end": round(w1["end"], 2), "text": b["text"]})
    for i, r in enumerate(rows):
        r["slot_end"] = rows[i + 1]["start"] if i + 1 < len(rows) else None

    # 단조 증가 검사
    for a, b in zip(rows, rows[1:]):
        if b["start"] < a["end"]:
            print(f"경고: 블록 {a['n']} 끝 {a['end']} > 블록 {b['n']} 시작 {b['start']}", file=sys.stderr)

    WORK.mkdir(exist_ok=True)
    (WORK / "timeline.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"정렬 유사도 {ratio:.3f} · ASR 단어 {len(words)}개 · 마지막 단어 끝 {words[-1]['end']:.1f}s")
    print(f"{'n':>2} {'start':>7} {'end':>7} {'slot':>6} {'말한':>6}  제목")
    for r in rows:
        slot = (r["slot_end"] or r["end"]) - r["start"]
        print(f"{r['n']:>2} {r['start']:7.2f} {r['end']:7.2f} {slot:6.1f} {r['end']-r['start']:6.1f}  {r['title']}")

    # [ ] 자리가 있는 블록: 그 구간에서 ASR 이 들은 말을 보여준다
    for r in rows:
        if "[" in r["text"]:
            heard = " ".join(w["text"] for w in words if r["start"] <= w["start"] <= r["end"])
            print(f"\n블록 {r['n']} 에 [ ] 자리 있음. ASR 이 들은 말:\n  {heard}")


if __name__ == "__main__":
    main()
