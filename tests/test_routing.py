"""docs/app/routing_extra.js (마포대교 보행 연결) 검증 — node 로 tests/routing_spec.mjs 를 돌리고 항목별로 본다.

tests/test_field.py 와 같은 방식이다. 배포되는 파일을 그대로 실행하므로 사본이 어긋날 일이 없다.
node 가 없으면 skip (수집·모델 실행에는 node 가 필요 없다).
"""
import json, pathlib, shutil, subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests" / "routing_spec.mjs"


def _run():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음 — 브라우저 측 검증 생략")
    r = subprocess.run([node, str(SPEC)], cwd=ROOT, capture_output=True, text=True)
    if not r.stdout.strip():
        pytest.fail(f"routing_spec.mjs 가 결과를 내지 못했다.\nstdout: {r.stdout[:500]}\nstderr: {r.stderr[:1500]}")
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def routing_results():
    return _run()


def test_routing_spec_all_pass(routing_results):
    failed = [r for r in routing_results if not r["ok"]]
    assert not failed, "\n".join(f"  ✗ {r['name']}: {r.get('detail','')}" for r in failed)


def test_routing_spec_covers_expected_cases(routing_results):
    """스펙이 조용히 비어버리는 걸 막는다."""
    assert len(routing_results) >= 8, f"검증 항목이 {len(routing_results)}개뿐"


def test_dashboard_loads_routing_extra():
    """모듈을 만들어 두고 화면에서 안 불러오면 아무 효과가 없다."""
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "app/routing_extra.js" in html, "index.html 이 routing_extra.js 를 로드하지 않는다"
    assert "withExtraEdges" in html, "routeGraph 가 병합 함수를 부르지 않는다"
