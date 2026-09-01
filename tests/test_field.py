"""docs/app/field.js (GP 혼잡장) 검증 — node 로 tests/field_spec.mjs 를 돌리고 결과를 항목별로 본다.

JS 구현을 파이썬으로 다시 쓰지 않기 위해 실제 배포되는 코드를 그대로 실행한다.
node 가 없으면 skip (수집·모델 실행에는 node 가 필요 없다).
"""
import json, pathlib, shutil, subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests" / "field_spec.mjs"


def _run():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음 — 브라우저 측 검증 생략")
    r = subprocess.run([node, str(SPEC)], cwd=ROOT, capture_output=True, text=True)
    if not r.stdout.strip():
        pytest.fail(f"field_spec.mjs 가 결과를 내지 못했다.\nstdout: {r.stdout[:500]}\nstderr: {r.stderr[:1500]}")
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def field_results():
    return _run()


def test_field_spec_all_pass(field_results):
    failed = [r for r in field_results if not r["ok"]]
    assert not failed, "\n".join(f"  ✗ {r['name']}: {r.get('detail','')}" for r in failed)


def test_field_spec_covers_expected_cases(field_results):
    """스펙이 조용히 비어버리는 걸 막는다."""
    assert len(field_results) >= 15, f"검증 항목이 {len(field_results)}개뿐"
