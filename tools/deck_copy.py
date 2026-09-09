"""덱 워딩 추출 — docs/deck.html 의 장별 킥커·헤드라인·본문·범례·발표자 노트를 deck_copy.md 로 낸다.

다른 사람(또는 다른 모델)에게 문장 교정을 받을 때 쓴다. 차트가 캔버스에 그리는 글자(패널 제목·타일·축 라벨)와
live_result·process 같은 JSON 문구는 여기 없다 — 그건 docs/deck/*.json 과 docs/app/deck_charts.js 다.
재실행: .venv/bin/python tools/deck_copy.py
"""
import html as H, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DECK = ROOT / "docs" / "deck.html"
OUT = ROOT / "deck_copy.md"


def strip(s):
    s = re.sub(r"<br\s*/?>", " / ", s)
    s = re.sub(r"(</(?:b|span|em|strong|sub|small)>)(?=\s*<)", r"\1 ", s)     # 인라인 요소가 맞붙은 자리만 띄운다 — "당일층실측" 방지, "상태만" 은 그대로
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", H.unescape(s)).strip()


def blocks(body):
    """본문을 나오는 순서대로 — 제목·문단·항목·카드 글자. 캔버스·iframe·아이콘은 뺀다."""
    b = re.sub(r"<canvas[^>]*></canvas>|<iframe.*?</iframe>|<img[^>]*>|<i [^>]*></i>|<aside class=\"notes\">.*?</aside>", "", body, flags=re.S)
    out = []
    for m in re.finditer(r"<(h[123]|p|li|button|figcaption|span|div|b)\b[^>]*>(.*?)</\1>", b, re.S):
        tag, inner = m.group(1), m.group(2)
        if re.search(r"<(h[123]|p|li|div|figcaption)\b", inner):
            continue                          # 자식이 블록이면 자식에서 잡는다
        t = strip(inner)
        if len(t) < 2 or t in ("—", "▶ 재생"):
            continue
        if tag in ("span", "b") and len(t) < 12:
            continue                          # 범례 조각·강조어 — 부모 문장에 이미 들어 있다
        if out and t in out[-1]:
            continue                          # 강조 span 이 부모 문장 안에 있으면 중복
        out.append(t)
    # 강조 span 조각(짧은 것)이 부모 문장 안에 다시 잡힌 경우만 정리 — 카드 제목 같은 독립 짧은 글은 남긴다
    dedup = []
    for i, t in enumerate(out):
        if len(t) < 12 and any(t != u and t in u for u in out[max(0, i - 2):i + 3]):
            continue
        if t not in dedup:
            dedup.append(t)
    return dedup


def main():
    h = DECK.read_text(encoding="utf-8")
    secs = re.findall(r"<!-- (\d+) ─ ([^>]*?) -->\n<section data-label=\"([^\"]+)\"(.*?)</section>", h, re.S)
    lines = ["# 불꽃배웅 피치 덱 — 워딩 (자동 추출)", "",
             f"원본 `docs/deck.html` {len(secs)}장 · 생성 `tools/deck_copy.py` · 교정본은 이 파일이 아니라 deck.html 에 반영한다.",
             "발표 5분 대면 + 질의. 심사위원은 비전공. 한 장 = 헤드라인 1 + 시각 요소 1 + 보조 ≤2줄. 노트는 장당 60~170자(≈25초).",
             "**숫자는 고치지 말 것** — 전부 `docs/deck/*.json` 과 테스트가 대조한다. 문장·어순·조사·톤만.", ""]
    for n, cm, lab, body in secs:
        heads = [strip(x) for x in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", body, re.S)]
        kick = re.search(r"<span class=\"kick\">(.*?)</span>", body, re.S) or re.search(r"<div (?:class=\"kicker\" )?data-rv style=\"--i:0;[^\"]*\">(.*?)</div>", body, re.S)
        notes = re.search(r"<aside class=\"notes\">(.*?)</aside>", body, re.S)
        lines.append(f"## {int(n)}. {lab[3:]}")
        lines.append("")
        if kick:
            lines.append(f"- 킥커: {strip(kick.group(1))}")
        for hd in heads:
            lines.append(f"- 헤드라인: **{hd}**")
        bl = [t for t in blocks(body) if t not in heads and (not kick or t != strip(kick.group(1)))]
        if bl:
            lines.append("- 본문:")
            lines.extend(f"  - {t}" for t in bl)
        if notes:
            nt = strip(notes.group(1))
            lines.append(f"- 발표자 노트 ({len(nt)}자): {nt}")
        lines.append("")
    lines += ["## 캔버스·JSON 문구 (여기 없음)", "",
              "- 8장 패널 제목 「① 최단 — 봉우리를 통과 / ② 혼잡 회피 — 돌아간다 / ③ 겹쳐 보기」 → `docs/app/deck_charts.js` TITLE",
              "- 10장 타일·카드(287 발행 · 21:27 기입 · 9배 · 23시 꼬리) → `docs/deck/live_result.json` (evaluate.py 산출, 고치지 않는다)",
              "- 5장 lag 차트 라벨 「피더역 승차 (탄다) / 여의도 도착 (내린다) / 정점 17시 → 18시」 → deck_charts.js drawFeeder", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}  {len(secs)}장  {OUT.stat().st_size / 1024:.1f}KB")


if __name__ == "__main__":
    main()
