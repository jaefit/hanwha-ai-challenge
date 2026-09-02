"""docs/app/board.js (출구 판정 규칙) 검증 — node 로 tests/board_spec.mjs 를 돌리고 항목별로 본다.

관람객용 화면(docs/go.html)과 운영용 화면(docs/index.html)이 같은 규칙을 쓰게 하려고 뺀 모듈이다.
두 화면이 조용히 어긋나는 것을 막는 정합 검사도 여기 있다.
"""
import json, pathlib, re, shutil, subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests" / "board_spec.mjs"


def _run():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음 — 브라우저 측 검증 생략")
    r = subprocess.run([node, str(SPEC)], cwd=ROOT, capture_output=True, text=True)
    if not r.stdout.strip():
        pytest.fail(f"board_spec.mjs 가 결과를 내지 못했다.\nstdout: {r.stdout[:500]}\nstderr: {r.stderr[:1500]}")
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def board_results():
    return _run()


def test_board_spec_all_pass(board_results):
    failed = [r for r in board_results if not r["ok"]]
    assert not failed, "\n".join(f"  ✗ {r['name']}: {r.get('detail','')}" for r in failed)


def test_board_spec_covers_expected_cases(board_results):
    assert len(board_results) >= 10, f"검증 항목이 {len(board_results)}개뿐"


def test_visitor_page_exists_and_uses_shared_rules():
    go = ROOT / "docs" / "go.html"
    assert go.exists(), "docs/go.html 이 없다"
    html = go.read_text(encoding="utf-8")
    for need in ("app/board.js", "app/routing_extra.js", "data/latest.json"):
        assert need in html, f"go.html 이 {need} 를 쓰지 않는다"


def test_visitor_page_omits_operator_only_material():
    """관람객 화면에 운영·방법론 지표를 끌고 오면 나눈 의미가 없다."""
    html = (ROOT / "docs" / "go.html").read_text(encoding="utf-8")
    for banned in ("가우시안", "길이척도", "사후 표준편차", "edge_hit", "coverage_c"):
        assert banned not in html, f"관람객 화면에 운영용 표현이 있다: {banned}"


def test_two_pages_share_grade_thresholds():
    """index.html 의 LV 와 board.js 의 grade 가 어긋나면 같은 데이터가 두 화면에서 다른 등급으로 보인다."""
    idx = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    board = (ROOT / "docs" / "app" / "board.js").read_text(encoding="utf-8")
    m = re.search(r"const LV=\(x,closed\)=>closed\?\"심각\":x>=(\S+?)\?\"심각\":x>=(\S+?)\?\"경계\":x>=(\S+?)\?\"주의\":\"여유\"", idx)
    assert m, "index.html 의 LV 정의를 찾지 못했다 — 형태가 바뀌었으면 이 검사를 고쳐야 한다"
    severe, alert, caution = m.groups()
    for label, value in (("심각", severe), ("경계", alert), ("주의", caution)):
        assert re.search(rf">=\s*{re.escape(value)}\s*\?\s*\"{label}\"", board), \
            f"board.js 의 {label} 경계가 index.html({value}) 과 다르다"
