#!/usr/bin/env python3
"""docs/report.html → 외부 의존 없는 단일 HTML (submission/report_standalone.html).

인라인하는 것
  - 글꼴: Pretendard(로컬 OTF 5종) · 마루부리 3종 · Hahmlet(가변) · IBM Plex Mono 2종 — 본문에 쓰인 글자만 서브셋해 woff2 base64
  - KaTeX 0.16.11: css(글꼴 20종 base64) + katex.min.js + auto-render + onload 호출
  - 파비콘(ico)
바꾸는 것
  - 상대 링크(report_easy·deck·index·go .html) → GitHub Pages 절대 URL
필요: fontTools · brotli (pip). 원본 파일은 --assets 디렉터리에 미리 받아 둔다(아래 ASSETS 참고).

  python tools/build_standalone.py --assets /path/to/sa [--out submission/report_standalone.html]
"""
import argparse
import base64
import html
import io
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report.html"
PAGES = "https://jaefit.github.io/hanwha-ai-challenge/"
LOCAL_FONTS = Path.home() / "Library/Fonts"

# family, weight(or range), source file (assets 상대경로 또는 절대), 유형
FONTS = [
    ("Pretendard Variable", "400", LOCAL_FONTS / "Pretendard-Regular.otf"),
    ("Pretendard Variable", "500", LOCAL_FONTS / "Pretendard-Medium.otf"),
    ("Pretendard Variable", "600", LOCAL_FONTS / "Pretendard-SemiBold.otf"),
    ("Pretendard Variable", "700", LOCAL_FONTS / "Pretendard-Bold.otf"),
    ("Pretendard Variable", "800", LOCAL_FONTS / "Pretendard-ExtraBold.otf"),
    ("MaruBuriW", "400", "fonts/MaruBuri-Regular.woff2"),
    ("MaruBuriW", "600", "fonts/MaruBuri-SemiBold.woff2"),
    ("MaruBuriW", "700", "fonts/MaruBuri-Bold.woff2"),
    ("Hahmlet", "100 900", "fonts/Hahmlet.ttf"),
    ("IBM Plex Mono", "400", "fonts/IBMPlexMono-Regular.ttf"),
    ("IBM Plex Mono", "600", "fonts/IBMPlexMono-SemiBold.ttf"),
]


def used_chars(src_html: str) -> str:
    body = re.sub(r"<script.*?</script>", "", src_html, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", body))
    txt += " ".join(re.findall(r"<script[^>]*>(.*?)</script>", src_html, flags=re.S))
    txt += " ".join(re.findall(r"<style[^>]*>(.*?)</style>", src_html, flags=re.S))
    chars = set(txt) | {chr(c) for c in range(0x20, 0x7F)}
    chars |= set("·—–…“”‘’「」『』×÷≈≤≥±→←↔↑↓•※℃㎡㎢㎞°′″€£¥₩¹²³½¼¾①②③④⑤⑥⑦⑧⑨⑩▶◀▲▼■□●○◆◇★☆✓")
    return "".join(sorted(c for c in chars if ord(c) >= 0x20 and c not in "\r\n\t"))


def subset_font(path: Path, text: str) -> bytes:
    font = TTFont(str(path))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.drop_tables += ["DSIG"]
    sub = subset.Subsetter(opts)
    sub.populate(text=text)
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return buf.getvalue()


def b64(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", required=True, help="katex/·fonts/ 가 있는 디렉터리")
    ap.add_argument("--out", default=str(ROOT / "submission" / "report_standalone.html"))
    args = ap.parse_args()
    A = Path(args.assets)
    s = SRC.read_text(encoding="utf-8")
    text = used_chars(s)
    print(f"글자 {len(text)}자")

    # 1) 글꼴 서브셋 → @font-face
    faces, total = [], 0
    for family, weight, src in FONTS:
        p = Path(src) if isinstance(src, Path) else A / src
        if not p.exists():
            sys.exit(f"글꼴 없음: {p}")
        data = subset_font(p, text)
        total += len(data)
        faces.append(f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;font-display:swap;'
                     f'src:url({b64(data, "font/woff2")}) format("woff2")}}')
        print(f"  {family} {weight}: {len(data) / 1024:.0f}KB")
    print(f"글꼴 합계 {total / 1024:.0f}KB")

    # 2) KaTeX css (글꼴 base64) + js
    kcss = (A / "katex/katex.min.css").read_text(encoding="utf-8")
    kcss = re.sub(r',url\(fonts/[^)]+\.(?:woff|ttf)\) format\("[^"]+"\)', "", kcss)

    def repl(m):
        f = A / "katex" / m.group(1)
        return f"url({b64(f.read_bytes(), 'font/woff2')})"
    kcss = re.sub(r"url\((fonts/[^)]+\.woff2)\)", repl, kcss)
    assert "url(fonts/" not in kcss
    kjs = (A / "katex/katex.min.js").read_text(encoding="utf-8")
    ajs = (A / "katex/auto-render.min.js").read_text(encoding="utf-8")
    for j in (kjs, ajs):
        assert "</script" not in j, "js 안에 </script 문자열"

    # 3) head 의 외부 링크 제거·치환
    def drop(pattern, count=1):
        nonlocal s
        n = len(re.findall(pattern, s))
        assert n == count, f"{pattern!r}: {n}개(기대 {count})"
        s = re.sub(pattern, "", s)
    drop(r'<link rel="icon" type="image/png" href="assets/favicon.png">\n')
    drop(r'<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">\n')
    drop(r'<link rel="stylesheet" href="https://cdn\.jsdelivr\.net/gh/orioncactus/pretendard[^"]+">\n')
    drop(r'<link rel="preconnect" href="https://fonts\.g(?:oogleapis|static)\.com"[^>]*>\n', 2)
    drop(r'<link rel="stylesheet" href="https://fonts\.googleapis\.com/[^"]+">\n')
    ico = (ROOT / "docs/assets/favicon.ico").read_bytes()
    s = s.replace('<link rel="icon" href="assets/favicon.ico" sizes="any">',
                  f'<link rel="icon" href="{b64(ico, "image/x-icon")}" sizes="any">', 1)
    katex_link = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">'
    assert s.count(katex_link) == 1
    s = s.replace(katex_link, "<style>\n" + "\n".join(faces) + "\n</style>\n<style>" + kcss + "</style>", 1)

    # 마루부리 원격 @font-face 3줄 → 위 인라인이 대신한다
    n = len(re.findall(r'@font-face\{font-family:MaruBuriW;[^}]*hangeul\.pstatic\.net[^}]*\}', s))
    assert n == 3, n
    s = re.sub(r'@font-face\{font-family:MaruBuriW;[^}]*hangeul\.pstatic\.net[^}]*\}', "", s)

    # 4) KaTeX 스크립트 인라인 (onload 호출은 뒤에 별도 스크립트로)
    m = re.search(r'<script defer src="https://cdn\.jsdelivr\.net/npm/katex@0\.16\.11/dist/katex\.min\.js"></script>\s*'
                  r'<script defer src="https://cdn\.jsdelivr\.net/npm/katex@0\.16\.11/dist/contrib/auto-render\.min\.js" onload="(.*?)"></script>', s, re.S)
    assert m, "KaTeX 스크립트 태그를 못 찾았다"
    onload = html.unescape(m.group(1))
    s = s[:m.start()] + f"<script>{kjs}</script>\n<script>{ajs}</script>\n<script>{onload}</script>" + s[m.end():]

    # 5) 상대 링크 → Pages 절대 URL
    s, n = re.subn(r'href="((?:report_easy|deck|index|go)\.html[^"]*)"', lambda mm: f'href="{PAGES}{mm.group(1)}"', s)
    print(f"링크 {n}개 → 절대 URL")

    # 6) 남은 외부 참조 점검 (a href 는 허용)
    leftovers = [x for x in re.findall(r'(?:src|href)="(https?://[^"]+)"', s)
                 if not re.search(r'<a [^>]*href="' + re.escape(x), s)]
    leftovers += re.findall(r'url\((https?://[^)]+)\)', s)
    leftovers += re.findall(r'(?:src|href)="((?:assets|data|app)/[^"]+)"', s)
    if leftovers:
        sys.exit(f"외부 참조 남음: {leftovers[:5]}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(s, encoding="utf-8")
    print(f"{out}  {out.stat().st_size / 1024 / 1024:.2f}MB")


if __name__ == "__main__":
    main()
