"""관람객 화면 v2(docs/go.html) — "묻지 않는" 화면 가드.

2026-09-04 Claude Design 「귀가 내비 v2」(GoScreen.dc.html) 이식. 렌더는 헤드리스로 못 본다(WebGL) —
그래서 묻지 않는다는 약속을 문자열로 본다: 드롭다운·시간 탭이 다시 들어오면 여기서 잡힌다.
"""
import pathlib, re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GO = ROOT / "docs" / "go.html"


@pytest.fixture(scope="module")
def html():
    return GO.read_text(encoding="utf-8")


def test_visitor_page_asks_nothing(html):
    """출발지·목적지·시각을 사용자에게 묻지 않는다."""
    assert "<select" not in html, "목적지 드롭다운이 남아 있다"
    assert 'role="tab"' not in html, "시간 탭이 남아 있다"
    assert "navigator.geolocation" in html, "출발지를 위치 권한으로 자동으로 잡지 않는다"
    assert "이벤트광장" in html and "위치 켜기" in html, "위치 거절 흐름(이벤트광장 기본 + 위치 켜기)이 없다"
    assert "Board.defaultHour(" in html, "시각 기본값이 '지금'이 아니다"


def test_visitor_page_recommends_by_walk_plus_wait(html):
    """1위 = 도보 + 대기 시간 (2026-09-04 결정). 부하율 순위는 운영 화면(index.html)에 남는다."""
    assert "rankByTime(" in html, "도보+대기 시간 순위 함수가 없다"
    assert "Board.rank(" in html, "공용 판정(Board.rank)을 거치지 않는다"
    assert "waitMin" in html, "대기 시간이 순위에 안 들어간다"


def test_visitor_page_reports_freshness_without_alerts(html):
    """신선도는 필 하나로 — 실시간 · N분 전 · 수집 끊김 · 오프라인. 경고창 없음."""
    assert "Board.freshness(" in html, "공용 신선도 판정을 쓰지 않는다 (H10)"
    for word in ("실시간", "수집 끊김", "오프라인"):
        assert word in html, f"신선도 상태 문구 '{word}' 가 없다"
    assert "alert(" not in html and "confirm(" not in html, "경고창을 띄운다"


def test_visitor_page_is_single_light_theme(html):
    """디자인 결정: 라이트 단일. 토글이 다시 들어오면 두 팔레트를 관리해야 한다."""
    assert 'data-theme' not in html, "테마 토글이 남아 있다"


def test_visitor_page_keeps_field_ramp_in_sync_with_operator_page(html):
    """지도 혼잡장 램프는 두 화면이 같은 시각에 같은 색을 내야 한다 — index.html 과 같은 원색."""
    for hexv in ("#2E7D5B", "#B8860B", "#C2622B", "#B3352B"):
        assert hexv in html, f"혼잡장 램프 색 {hexv} 가 없다"
    for c in ("lenShort:150", "lenLong:1200", "F_FEATHER=.18", "F_PAD=.012"):
        assert c in html, f"혼잡장 상수 {c} 가 운영 화면과 다르다"


def test_visitor_page_keeps_safety_notice(html):
    assert "숫자는 예측" in html, "예측 고지가 빠졌다"
    assert "OpenStreetMap" in html, "지도 저작권 표시가 빠졌다"


def _node_geometry(js_body):
    """go.html 의 WAY 와 path() 를 그대로 떼어 node 로 돌린다 — 화면 코드와 갈리지 않게 파일에서 읽는다."""
    import json, shutil, subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    html = GO.read_text(encoding="utf-8")
    way = re.search(r"const WAY=\{.*?\};", html, re.S)
    path = re.search(r"// @pure path start\n(.*?)// @pure path end", html, re.S)
    assert way and path, "go.html 에서 WAY 나 path() 를 찾지 못했다 — 표식 주석이 빠졌나"
    src = ("const Field=require('./docs/app/field.js');const distM=(a,b)=>Field.distanceM(a,b);let ORIGIN=null;"
           + way.group(0) + path.group(1) + js_body)
    r = subprocess.run([node, "-e", src], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)


def test_route_from_moved_pin_does_not_walk_back_to_the_plaza():
    """핀을 국회 쪽으로 끌었는데 경로가 광장 옆 첫 경유점으로 되돌아갔다(2026-09-04 사용자 발견).

    시작 경유점은 남은 길이가 가장 짧아지는 곳이어야 한다 — 뒤에 있는 경유점은 버린다.
    """
    out = _node_geometry("""
      ORIGIN=[126.9215,37.5290];                       // 국회 서쪽 — 광장(126.932) 보다 훨씬 서쪽
      const p=path('yd9'), total=(P)=>P.slice(1).reduce((s,c,i)=>s+distM(P[i],c),0);
      const viaAll=total([ORIGIN].concat(WAY.yd9));
      ORIGIN=WAY.saet[WAY.saet.length-1];              // 역 위에 서 있으면 경로는 점 하나
      console.log(JSON.stringify({first:p[1], total:total(p), viaAll, atStation:path('saet').length}));
    """)
    assert out["first"] != [126.9318, 37.5268], "여전히 광장 옆 첫 경유점으로 되돌아간다"
    assert out["total"] < out["viaAll"], "경유점을 버렸는데 더 길다"
    assert out["atStation"] == 2, "역 위에 있으면 원점→역 한 구간이어야 한다"


def test_visitor_page_routes_on_walk_graph_with_approx_fallback(html):
    """경로는 운영 화면과 같은 보행망 A* (2026-09-04 결정, 근사 경유점은 보행망을 받기 전 폴백).

    선이 길을 따라가고 붐비는 곳을 돌아가려면 보행망이 필요하다 — 근사 직선은 시간만 혼잡 반영하고 우회를 못 한다.
    """
    for need in ("data/routing/walk_graph.json", "app/routing_extra.js", "withExtraEdges", "function astar(", "Field.V_FREE"):
        assert need in html, f"go.html 에 {need} 가 없다 — 보행망 A* 가 빠졌다"
    assert "// @pure path start" in html, "보행망을 받기 전 폴백(근사 경유점)이 없다"
    assert "근사" in html, "보행망을 받기 전엔 화면에 근사라고 적어야 한다"
