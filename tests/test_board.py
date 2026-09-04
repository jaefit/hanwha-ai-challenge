"""docs/app/board.js (출구 판정 규칙) 검증 — node 로 tests/board_spec.mjs 를 돌리고 항목별로 본다.

관람객용 화면(docs/go.html)과 운영용 화면(docs/index.html)이 같은 규칙을 쓰게 하려고 뺀 모듈이다.
두 화면이 조용히 어긋나는 것을 막는 정합 검사도 여기 있다.
"""
import json, pathlib, re, shutil, subprocess, sys

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
    # 2026-09-04 v2: 보행망 A* 는 운영 화면에만 남는다(관람객 화면은 역별 근사 경유점) — routing_extra 요구를 뺐다
    for need in ("app/board.js", "app/field.js", "data/latest.json"):
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


def test_three_places_share_collection_stale_threshold():
    """수집 끊김 판정 기준(15분)이 세 곳에 흩어져 있다 — nowcast(생산) · board.js(관람객) · index.html(운영).
    하나만 바뀌면 한 화면은 "실시간", 다른 화면은 "수집 끊김" 이라 말한다 (결함 H10, 2026-09-03)."""
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import nowcast as N
    idx = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    board = (ROOT / "docs" / "app" / "board.js").read_text(encoding="utf-8")
    mi = re.search(r"const COLLECT_STALE_MIN=(\d+);", idx)
    mb = re.search(r"var COLLECT_STALE_MIN = (\d+);", board)
    assert mi and mb, "COLLECT_STALE_MIN 정의를 찾지 못했다 — 형태가 바뀌었으면 이 검사를 고쳐야 한다"
    assert int(mi.group(1)) == int(mb.group(1)) == N.SOURCE_MAX_AGE_MIN, \
        f"기준 불일치: index.html {mi.group(1)} · board.js {mb.group(1)} · nowcast {N.SOURCE_MAX_AGE_MIN}"


# ── 생산자–소비자 계약 (2026-09-02 T7 드라이런에서 발견) ──────────────────────
# board_spec.mjs 는 board.js 에 {prior:true} 를 **손으로 넣어** 통과한다. 그래서 nowcast 가 그 키를 아예
# 안 준다는 사실을 구조적으로 못 잡았고, 관측 0건인 평일 예측이 공개 화면에서 "실시간 반영 · α 1.00" 으로
# 나갔다 (Pages 서빙본 2026-09-02T18:33:16 에서 확인). M6 은 소비자 쪽만 닫혀 있었다.

def _nowcast(tmp_path, date):
    out = tmp_path / f"fc_{date}.json"
    r = subprocess.run([sys.executable, "src/nowcast.py", "--date", date, "--out", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, f"nowcast 실패\n{r.stderr[-1500:]}"
    assert out.exists(), "--out 이 파일을 쓰지 않았다 (라이브 forecast_latest.json 을 건드리면 안 된다)"
    return json.loads(out.read_text(encoding="utf-8"))


def test_nowcast_marks_prior_when_no_observations(tmp_path):
    """관측 0건이면 payload 에 prior=True 가 있어야 한다. 없으면 board.js 가 사전값을 측정값으로 말한다."""
    fc = _nowcast(tmp_path, "20200101")          # 수집 데이터가 없는 날
    assert fc["assimilation"]["n_obs"] == {"alighting": 0, "boarding": 0}
    assert fc.get("prior") is True, "관측이 없는데 prior 가 True 가 아니다 — 화면이 '실시간 반영' 으로 읽는다"


def test_nowcast_clears_prior_when_observations_exist(tmp_path):
    """관측이 우도에 들어가면 prior 는 False 여야 한다 (항상 True 로 박아 두면 실황을 사전값이라 말한다).

    불변식은 **"prior ⇔ 사후분포가 곧 사전분포"** 이지 "prior ⇔ 관측 0건" 이 아니다. 지금은 둘이 같지만,
    프리즈 전 C1(관측이 적으면 사전 밴드로 클램프)이 들어가면 갈라진다 — 그때는 이 검사도 같이 옮겨야
    하고, 이 테스트를 "관측 1건이면 무조건 live" 라는 사양으로 읽으면 안 된다.
    """
    src = ROOT / "data" / "live" / "api_20260829.jsonl"
    if not src.exists():
        pytest.skip("data/live/api_20260829.jsonl 없음 (git 미추적) — 수집분이 있는 기기에서만 도는 검사")
    fc = _nowcast(tmp_path, "20260829")          # 실제 수집분이 있는 날
    n = fc["assimilation"]["n_obs"]
    assert n["alighting"] + n["boarding"] > 0, "이 날짜에 관측이 없다 — 고정값을 바꿔야 한다"
    assert fc.get("prior") is False


def test_nowcast_emits_freshness_keys_board_reads(tmp_path):
    """board.js freshness() 가 읽는 키를 nowcast 가 실제로 내는지. board_spec 은 손으로 넣은 객체로 통과하므로
    이 계약이 없으면 화면은 수집 끊김을 영영 못 본다 (결함 H10 — prior 때와 같은 구멍)."""
    fc = _nowcast(tmp_path, "20200101")
    assert "data_freshness" in fc and "degraded_sources" in fc
    assert set(fc["data_freshness"]) >= {"citydata", "subway"}
    for k, v in fc["data_freshness"].items():
        assert set(v) == {"last_ok", "age_min", "stale"}, k
    # 수집 기록이 없는 날은 '끊김' 이 아니라 '시작 전' 이다
    assert fc["degraded_sources"] == []
    assert all(v["last_ok"] is None for v in fc["data_freshness"].values())


def test_board_reads_nowcast_prior_end_to_end(tmp_path):
    """실제 nowcast 산출물을 board.js 에 먹여 라벨까지 확인한다 — 두 모듈이 같은 키를 쓰는지가 요점이다."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    fc = _nowcast(tmp_path, "20200101")
    (tmp_path / "fc.json").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    script = (
        "const B=require(process.argv[1]);const fc=require(process.argv[2]);"
        "const r=B.rank(fc,'21');"
        "console.log(JSON.stringify({mode:r.mode,note:r.modeNote,alpha:B.alphaLabel(fc)}));"
    )
    r = subprocess.run([node, "-e", script, str(ROOT / "docs" / "app" / "board.js"), str(tmp_path / "fc.json")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    got = json.loads(r.stdout)
    assert got["mode"] == "prior", f"관측 없는 예측을 {got['mode']} 로 읽는다 — {got}"
    assert "실시간" not in got["note"], got["note"]
    assert got["alpha"].startswith("사전값"), f"α 라벨이 측정값처럼 보인다: {got['alpha']}"


def test_map_pages_use_style_json_not_raster_template():
    """지도 바닥이 실제로 그려지는가 — URL 형태로 본다.

    OpenFreeMap 은 벡터 타일과 스타일 JSON 만 낸다. `/styles/<name>/{z}/{x}/{y}.png` 는 존재하지
    않아 요청이 전부 404 이고, 화면에는 컨트롤과 저작권 표시만 남아 바닥이 회색으로 비어 보인다.
    2026-09-03: docs/go.html 이 그 형태를 type:"raster" 로 물고 있어 관람객 화면의 길찾기가
    통째로 못 쓰는 상태였다. 헤드리스 검증은 WebGL 이 없어 이 종류를 잡지 못한다 — 그래서 정적으로 본다.
    """
    bad = re.compile(r"tiles\.openfreemap\.org/styles/[a-z]+/\{z\}")
    for name in ("go.html", "index.html"):
        html = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert not bad.search(html), f"{name}: OpenFreeMap 에 없는 래스터 타일 URL(404) 을 쓴다"
        assert "tiles.openfreemap.org/styles/" in html, f"{name}: 지도 스타일 URL 이 없다"
