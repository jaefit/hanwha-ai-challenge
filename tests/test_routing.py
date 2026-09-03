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


def test_both_pages_route_by_walking_time_not_a_penalty_weight():
    """경로 비용은 '거리 × 벌점' 이 아니라 '그 간선을 걷는 데 걸리는 시간' 이어야 한다.

    옛 비용은 `거리 × (1 + 1.25 × 혼잡)` 이었다. 1.25 는 출처가 없었고(보고서 §3.10 이
    그렇게 적었다), 최소화 대상이 사람이 신경 쓰는 값도 아니었다. 더 나쁜 것은 경로는
    벌점으로 고르면서 화면에 뜨는 소요 시간은 따로 계산해 둘이 따로 놀았다는 점이다.
    이제 두 화면 모두 field.js 의 walkSeconds 를 쓴다 — 고르는 기준과 보여주는 값이 같다.
    """
    for name in ("go.html", "index.html"):
        html = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "Field.blendSeconds" in html, f"{name}: 경로 비용이 확신도 혼합 시간이 아니다"
        assert "ROUTE_CROWD_WEIGHT" not in html, f"{name}: 출처 없는 벌점 상수가 남아 있다"
        # 표시 시간 함수가 둘이면 또 갈린다 — 고르는 비용과 보여주는 시간은 한 함수(blendSeconds)
        assert "pathSeconds" not in html, f"{name}: 표시용 별도 시간 함수가 남아 있다"
        assert "app/field.js" in html, f"{name}: field.js 를 로드하지 않는다"


def test_walk_speed_matches_nowcast_kladek():
    """화면(field.js)과 모델(nowcast.py)의 속도식이 갈리면 안 된다.

    같은 인파에서 화면이 말하는 소요 시간과 모델이 쓰는 도착 지연이 어긋나게 된다.
    """
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import nowcast as N  # noqa: E402

    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    script = (
        "const F=require(process.argv[1]);"
        "console.log(JSON.stringify([0.5,1.5,3.0,4.0,5.4].map(r=>F.walkSpeed(r))));"
    )
    r = subprocess.run([node, "-e", script, str(ROOT / "docs" / "app" / "field.js")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    got = json.loads(r.stdout)
    for rho, v in zip([0.5, 1.5, 3.0, 4.0, 5.4], got):
        assert abs(v - N.kladek(rho)) < 1e-12, f"밀도 {rho}: field.js {v} vs nowcast {N.kladek(rho)}"
