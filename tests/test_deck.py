"""피치 덱(docs/deck.html)과 그 데이터(docs/deck/*.json) 검사.

덱은 사람이 읽는 문서라 숫자가 손으로 적힌다. 그 숫자가 근거 파일과 갈리는 순간
발표에서 방어할 수 없게 되므로, 손으로 적은 값과 원본을 여기서 대조한다.
렌더는 헤드리스로 못 본다(WebGL·캔버스) — 그래서 URL 형태와 값만 정적으로 본다.
"""
import json, pathlib, re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DECK = ROOT / "docs" / "deck.html"
DATA = ROOT / "docs" / "deck"
DER = ROOT / "data" / "derived"


@pytest.fixture(scope="module")
def html():
    return DECK.read_text(encoding="utf-8")


def _json(name):
    p = DATA / f"{name}.json"
    if not p.exists():
        pytest.skip(f"{p.relative_to(ROOT)} 없음 — tools/deck_data.py 먼저 실행")
    return json.loads(p.read_text(encoding="utf-8"))


def test_deck_data_lives_outside_docs_data():
    """publish.py 가 `git add docs/data` 로 디렉터리를 통째로 스테이징한다(:109).

    덱 데이터를 그 아래 두면 5분마다 도는 발행 커밋이 반쯤 쓴 파일을 쓸어담는다.
    """
    assert not (ROOT / "docs" / "data" / "deck").exists(), \
        "덱 데이터가 docs/data 아래 있다 — publish.py 의 자동 커밋에 딸려 들어간다"
    assert DATA.is_dir(), "docs/deck 이 없다"


def test_every_chart_has_its_data_file(html):
    keys = set(re.findall(r'data-chart="([a-z]+)"', html))
    assert keys == {"feeder", "alpha", "backtest", "field", "route"}, keys
    for name in ("feeder_lag", "alpha_grid", "backtest_bars", "field_grid", "route_demo"):
        assert (DATA / f"{name}.json").exists(), f"{name}.json 이 없다"


def test_route_numbers_in_copy_match_export(html):
    """슬라이드 본문의 경로 수치가 내보내기와 같은가."""
    d = _json("route_demo")
    short = d["routes"]["shortest"]["meters"]
    assert f"{short:,}m" in html, f"본문에 최단 {short:,}m 이 없다"
    assert f"{d['straight_m']:,}m" in html, f"본문에 직선 {d['straight_m']:,}m 이 없다"
    ratio = round(short / d["straight_m"], 2)
    assert f"{ratio:.2f}배" in html, f"본문 우회비가 {ratio:.2f}배 와 다르다"
    n, e = d["graph_size"]["nodes"], d["graph_size"]["edges"]
    assert f"{n:,}" in html and f"{e:,}" in html


def test_route_export_reproduces_measured_distance():
    """이벤트광장→마포역 1,907m 은 2026-09-02 e4b9a1a 에서 실측된 값이다.

    이 값이 재현되지 않으면 보행망이나 비용식이 바뀐 것이고, 덱의 경로 수치를 믿을 수 없다.
    """
    d = _json("route_demo")
    assert d["mapo_check_m"] == 1907, f"마포역 {d['mapo_check_m']}m — 1,907m 이 재현되지 않는다"


def test_feeder_correlation_in_copy_matches_source(html):
    d = _json("feeder_lag")
    y = d["years"]["2025"]
    assert f"{y['r_lag0']:.2f} → {y['r_lag1']:.2f}" in html, \
        f"본문 상관계수가 원본({y['r_lag0']:.2f} → {y['r_lag1']:.2f})과 다르다"
    assert str(d["pooled_r_lag1"]) in html, "두 해 통합 r 이 본문에 없다"
    src = json.loads((DER / "feeder_leadlag.json").read_text(encoding="utf-8"))
    assert y["r_lag1"] == src["by_year"]["2025"]["pearson_lag1"], "내보내기가 derived 와 갈렸다"


def test_backtest_hit_rate_in_copy_matches_source(html):
    d = _json("backtest_bars")
    hit = d["modes"]["B_cross_year"]["years"]["2025"]["grade_hit_rate"]
    assert f"{round(hit * 100)}%" in html, f"본문에 등급 적중 {round(hit * 100)}% 이 없다"
    src = json.loads((DER / "backtest.json").read_text(encoding="utf-8"))
    assert hit == src["modes"]["B_cross_year"]["2025"]["grade_hit_rate"]


def test_synthetic_layers_are_labelled_as_such(html):
    """실측이 아닌 두 그림(α 관측 · 혼잡장 등급)은 화면에 그렇다고 적혀 있어야 한다."""
    alpha = _json("alpha_grid")
    assert alpha["synthetic"] is True
    assert f"α={alpha['alpha_true']} 가정" in html, "α 슬라이드에 가정 표기가 없다"
    field = _json("field_grid")
    assert field["synthetic_grades"] is True
    assert "등급 배치는 예시" in html, "혼잡장 슬라이드에 예시 표기가 없다"


def test_alpha_band_narrows_and_contains_truth():
    """추정기가 참값을 담은 채 좁아지는가 — 이 성질이 깨지면 슬라이드의 주장이 거짓이 된다."""
    d = _json("alpha_grid")
    first, last = d["frames"][0], d["frames"][-1]
    width = lambda f: (f["alpha"][2] - f["alpha"][0]) / f["alpha"][1]
    assert width(last) < width(first), "관측이 쌓였는데 밴드가 안 좁아진다"
    for f in d["frames"]:
        assert f["alpha"][0] <= d["alpha_true"] <= f["alpha"][2], \
            f"n={f['n']} 에서 밴드 {f['alpha']} 가 참값 {d['alpha_true']} 를 배제한다"


def test_deck_uses_katex_and_no_dead_tile_url(html):
    """H11 과 같은 종류 — 외부 자원 URL 형태를 정적으로 본다."""
    assert "katex@0.16.11" in html, "KaTeX 가 없다"
    assert "renderMathInElement" in html, "KaTeX auto-render 호출이 없다"
    assert not re.search(r"tiles\.openfreemap\.org/styles/[a-z]+/\{z\}", html)
