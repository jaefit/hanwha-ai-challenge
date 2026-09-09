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


CHART_FILES = {"exits": "exit_bars", "radial": "feeder_map", "feeder": "feeder_lag", "alpha": "alpha_grid",
               "field": "field_grid", "route": "route_demo", "live": "live_result"}
# 2026-09-09 v3(파이프라인 순서 11장) — route·backtest·redteam·replay·sources·process·route_real 은 JSON 과 데이터 테스트만 남고 덱엔 안 그린다


def test_every_chart_has_its_data_file(html):
    keys = set(re.findall(r'data-chart="([a-z]+)"', html))
    assert keys <= set(CHART_FILES), keys - set(CHART_FILES)
    assert keys == set(CHART_FILES), f"차트 7종이 전부 있어야 한다 — 빠진 것: {set(CHART_FILES) - keys}"
    for k in keys:
        assert (DATA / f"{CHART_FILES[k]}.json").exists(), f"{CHART_FILES[k]}.json 이 없다"


def test_route_numbers_in_copy_match_export(html):
    """8장(최단시간 경로 3패널) 본문의 경로 수치가 내보내기와 같은가."""
    d = _json("route_demo")
    short = d["routes"]["shortest"]["meters"]
    assert f"{short:,}m" in html, f"본문에 최단 {short:,}m 이 없다"
    assert f"{d['straight_m']:,}m" in html, f"본문에 직선 {d['straight_m']:,}m 이 없다"
    ratio = round(short / d["straight_m"], 2)
    assert f"{ratio:.2f}배" in html, f"본문 우회비가 {ratio:.2f}배 와 다르다"
    n, e = d["graph_size"]["nodes"], d["graph_size"]["edges"]
    assert f"{n:,}" in html and f"{e:,}" in html
    m = d["minutes"]
    assert f"{short:,}m · {m['shortest']}분" in html, f"최단 보행시간 {m['shortest']}분 이 본문과 다르다"
    assert f"{d['routes']['avoiding']['meters']:,}m · {m['avoiding']}분" in html
    assert re.search(rf"{m['shortest'] - m['avoiding']}분 (빠른|줄어|단축)", html), "절약 분이 본문과 다르다"
    modes = re.findall(r'<canvas data-mode="([a-z]+)"', html)
    assert modes == ["shortest", "avoiding", "both"], "① 최단 ② 회피 ③ 겹쳐 보기 세 패널 (사용자 결정 9/9)"
    assert 'data-chart="route" data-play="manual"' in html and html.count('<button type="button" class="btn') == 3, "패널마다 ▶ 재생 버튼 (사용자 결정 9/9)"
    js = (ROOT / "docs" / "app" / "deck_charts.js").read_text(encoding="utf-8")
    assert 'getAttribute("data-play") === "manual"' in js and 'button[data-play]' in js


def test_route_export_reproduces_measured_distance():
    """이벤트광장→마포역 1,907m 은 2026-09-02 e4b9a1a 에서 실측된 값이다.

    이 값이 재현되지 않으면 보행망이나 비용식이 바뀐 것이고, 덱의 경로 수치를 믿을 수 없다.
    """
    d = _json("route_demo")
    assert d["mapo_check_m"] == 1907, f"마포역 {d['mapo_check_m']}m — 1,907m 이 재현되지 않는다"


def test_feeder_correlation_in_copy_matches_source(html):
    d = _json("feeder_lag")
    y = d["years"]["2025"]
    text = re.sub(r"<[^>]+>", "", html)     # v3 디자인은 0.98 만 <b> 로 강조한다
    assert f"{y['r_lag0']:.2f} → {y['r_lag1']:.2f}" in text, \
        f"본문 상관계수가 원본({y['r_lag0']:.2f} → {y['r_lag1']:.2f})과 다르다"
    assert str(d["pooled_r_lag1"]) in text, "두 해 통합 r 이 본문에 없다"
    src = json.loads((DER / "feeder_leadlag.json").read_text(encoding="utf-8"))
    assert y["r_lag1"] == src["by_year"]["2025"]["pearson_lag1"], "내보내기가 derived 와 갈렸다"


def test_backtest_hit_rate_in_copy_matches_source(html):
    d = _json("backtest_bars")
    hit = d["modes"]["B_cross_year"]["years"]["2025"]["grade_hit_rate"]
    text = re.sub(r"<[^>]+>", "", html)     # 디자인은 88 과 % 를 다른 span 에 둔다
    assert f"{round(hit * 100)}%" in text, f"본문에 등급 적중 {round(hit * 100)}% 이 없다"
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


# ── v2 (2026-09-04) — 내보내기 5종 ────────────────────────────────────
def test_exit_bars_are_seven_exits_summing_to_one():
    d = _json("exit_bars")
    assert len(d["exits"]) == 7
    assert abs(sum(e["share"] for e in d["exits"]) - 1.0) < 0.01
    shares = [e["share"] for e in d["exits"]]
    assert shares == sorted(shares, reverse=True), "비중 내림차순이어야 막대 순서가 읽힌다"
    src = json.loads((DER / "exit_shares.json").read_text(encoding="utf-8"))
    for e in d["exits"]:
        assert e["share"] == src["share_mean"][e["name"]]
        assert e["E"] == src["E_mean"][e["name"]]


def test_feeder_map_has_twelve_stations_with_bearing():
    d = _json("feeder_map")
    src = json.loads((DER / "feeder_leadlag.json").read_text(encoding="utf-8"))
    assert len(d["feeders"]) == 12
    assert {f["name"] for f in d["feeders"]} == set(src["top_feeders"])
    persons = [f["persons"] for f in d["feeders"]]
    assert persons == sorted(persons, reverse=True)
    for f in d["feeders"]:
        assert 0 <= f["bearing_deg"] < 360, f
        assert f["travel_min"] > 0 and f["persons"] > 0, f
        assert f["persons"] == src["top_feeders"][f["name"]]["attributed_2yr"]
    assert d["rings_min"] == [10, 20, 30]
    assert d["center"]["name"] == "여의도"


def _ledger_ids():
    """결함 대장에서 ID 를 세는 규칙 — 표 첫 칸(`| C2 …` · `| **M4** …`) 또는 `### M4.` 제목. `### 철회 — H8` 은 철회."""
    txt = (ROOT / "redteam-20260901.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| *\**([CHML]\d+)\b", txt, re.M)) | set(re.findall(r"^### ([CHML]\d+)\.", txt, re.M))
    retracted = set(re.findall(r"^### 철회 — ([CHML]\d+)", txt, re.M))
    return listed - retracted, retracted


def test_redteam_counts_match_ledger():
    d = _json("redteam_counts")
    listed, retracted = _ledger_ids()
    assert d["total"] == len(listed)
    assert sum(d["by_grade"].values()) == d["total"]
    assert set(d["retracted"]) == retracted
    for g, key in (("C", "치명"), ("H", "높음"), ("M", "중간"), ("L", "낮음")):
        assert d["by_grade"][key] == len([i for i in listed if i[0] == g]), key


def test_code_strips_match_source():
    """덱의 코드 스트립은 손으로 베낀 게 아니라 소스에서 잘라 온 것이어야 한다."""
    strips = _json("code_strips")
    assert [s["id"] for s in strips] == ["demand", "alpha", "blend"]
    for s in strips:
        lines = (ROOT / s["file"]).read_text(encoding="utf-8").splitlines()
        seg = lines[s["start"] - 1: s["start"] - 1 + len(s["lines"])]
        assert seg == s["lines"], f"{s['id']}: {s['file']}:{s['start']} 가 소스와 다르다 — tools/deck_data.py 재실행"
        assert 3 <= len(s["lines"]) <= 8


def test_live_result_placeholder_exists():
    d = _json("live_result")
    assert isinstance(d["filled"], bool)
    if d["filled"]:
        for k in ("grade_hit", "alpha_final", "ticks", "restarts"):
            assert k in d, k


def test_live_result_numbers_come_from_evaluate():
    """채워진 결과는 evaluate.py 산출(eval_20260905.json)에서만 — 손으로 적은 숫자가 끼면 발표에서 방어할 수 없다."""
    d = _json("live_result")
    if not d["filled"]:
        pytest.skip("아직 안 채움")
    src = DER / "eval_20260905.json"
    if not src.exists():
        pytest.skip("eval_20260905.json 없음")
    ev = json.loads(src.read_text(encoding="utf-8"))
    assert d["ticks"] == len(ev["our_snapshots"])
    assert len(d["tiles"]) == 4 and len(d["cards"]) == 3
    assert d["tiles"][0]["v"] == str(len(ev["our_snapshots"]))
    assert d["tiles"][1]["v"] == f"{ev['n_records']:,}"
    sh = ev["subway_shape"]
    assert d["tail_ratio"]["obs"] == round(sh["obs_by_hour"]["23"] / sh["obs_by_hour"][str(sh["peak_obs"])], 3)
    assert d["tail_ratio"]["pred"] == round(sh["pred_by_hour"]["23"] / sh["pred_by_hour"][str(sh["peak_pred"])], 3)
    assert any(k["kind"] == "miss" for k in d["cards"]), "놓친 것을 적지 않은 결과 장은 채점이 아니다"


def test_replay_frames_are_verbatim_snapshots(html):
    """발행 스냅샷을 그대로 옮긴 데이터다 — 재계산 금지. 맥에 원천이 있으면 값까지 대조한다. (12장 판엔 재생 장이 없어 데이터만 지킨다)"""
    d = _json("replay_frames")
    assert len(d["frames"]) == 6, "재생 시각 6개"
    ats = [f["at"] for f in d["frames"]]
    assert set(d["before_after"]) <= set(ats) and d["peak"] in ats
    for f in d["frames"]:
        assert len(f["loads"]) == 7, f"{f['at']}: 출구 7개"
        assert set(f["outflow"]) == {"19", "20", "21", "22", "23"}
    hist = ROOT / "data" / "live" / "forecast_history" / "20260905"
    if not hist.exists():
        pytest.skip("발행 스냅샷 원천은 맥에만 있다")
    for f in d["frames"]:
        snap = json.loads((hist / f"{f['at']}.json").read_text(encoding="utf-8"))
        assert f["alpha"] == snap["alpha"] and f["outflow"] == snap["outflow_forecast"]
        for row in f["loads"]:
            if row["load"] is not None:
                assert row["load"] == snap["exits"][row["name"]][f["hour"]]["load"], (f["at"], row["name"])


def test_sources_table_has_eight_public_rows():
    d = _json("sources")
    assert len(d["rows"]) == 8 and d["all_public"] is True
    for r in d["rows"]:
        assert all(r.get(k) for k in ("name", "id", "gives", "cadence", "layer", "use", "limit")), r["name"]
    cams = json.loads((ROOT / "docs" / "data" / "cams.json").read_text(encoding="utf-8"))
    assert f"{len(cams)}대" in d["rows"][3]["id"], "CCTV 대수는 cams.json 에서"


def test_process_numbers_come_from_git_tests_and_ledger():
    """9장 과정 — 손 숫자 금지. 커밋·테스트·대장 건수를 여기서 다시 세어 대조한다."""
    import shutil, subprocess
    d = _json("process")
    if not shutil.which("git"):
        pytest.skip("git 없음")
    log = subprocess.run(["git", "log", "--format=%s", "--since=2026-08-28"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    non_pub = [l for l in log if not l.startswith("data: latest")]
    assert abs(d["commits_total"] - len(non_pub)) <= 3, f"커밋 {d['commits_total']} vs git {len(non_pub)} — tools/deck_data.py 재실행"
    n = sum(len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), re.M)) for p in (ROOT / "tests").glob("test_*.py"))
    assert d["tests"]["now"] == n, "테스트 수가 낡았다 — tools/deck_data.py 재실행"
    rt = _json("redteam_counts")
    assert d["redteam"]["total"] == rt["total"] and d["redteam"]["rounds"] == 7
    assert d["hotfix_day"] == 4
    for x in d["days"]:
        assert x["commits"] > 0


def test_route_real_is_measured_not_scenario():
    """9/5 실측 장(route_real). 시각 6 × 목적지 6, changed 와 extra_m·saved_sec 가 서로 맞는가. 12장 판엔 안 그리지만 데이터는 지킨다."""
    d = _json("route_real")
    assert len(d["frames"]) == 6
    for f in d["frames"]:
        assert len(f["routes"]) == 6 and f["field"]["cctv_uncalibrated"] >= 15
        for r in f["routes"]:
            assert "error" not in r, r
            if r["changed"]:
                assert r["extra_m"] > 0 and r["saved_sec"] > 0, r
            else:
                assert r["extra_m"] == 0 and r["saved_sec"] == 0, r
    assert any(r["changed"] for f in d["frames"] for r in f["routes"]), "실측에서 하나도 안 바뀌면 보고서 §3.10 문구를 바꿔야 한다"


# ── v2 — 구조 ─────────────────────────────────────────────────────────
def _sections(html):
    return re.findall(r'<section [^>]*class="slide[^"]*" id="(s\d+)">(.*?)</section>', html, re.S)


N_SLIDES = 12   # 2026-09-09 v3 — 파이프라인 순서 11장 + 8장 최단시간 경로(3패널, 같은 날 추가) (스펙 docs/superpowers/specs/2026-09-09-deck-v3-design.md). 앞 판: v2 12장 7fd2a95 · 14장 07f6411


def test_twelve_sections_each_with_heading_and_notes(html):
    secs = _sections(html)
    assert [s[0] for s in secs] == [f"s{i}" for i in range(1, N_SLIDES + 1)]
    for sid, body in secs:
        assert re.search(r"<h[12]\b", body), f"{sid}: 제목 없음"
        assert '<aside class="notes">' in body, f"{sid}: 발표자 노트 없음"


def test_light_theme_tokens_and_no_dark_leftovers(html):
    """2026-09-06 Claude Design 「Pitch Deck v2」(토스풍) 토큰. 이전 판(검정 덱 · 종이색 덱) 잔재가 남으면 두 디자인이 섞인다."""
    for tok in ("--bg:#FFFFFF", "--card:#F2F4F6", "--ink:#191F28", "--rule:#E5E8EB", "--accent:#F36F21", "--dark:#17171C"):
        assert tok in html, tok
    for bad in ("#0b0d12", "Hahmlet", "fireworks-js", "#F5F4F1", "Black Han Sans", "#14110C"):
        assert bad not in html, f"이전 덱 잔재: {bad}"


def test_stage_component_and_chart_module(html):
    """1920×1080 고정 무대(deck-stage) + 차트 모듈. 무대가 없으면 인라인 px 디자인이 뷰포트에 맞지 않는다."""
    assert '<deck-stage width="1920" height="1080">' in html
    assert 'src="app/deck-stage.js"' in html and (ROOT / "docs" / "app" / "deck-stage.js").exists()
    assert 'from "./app/deck_charts.js"' in html and (ROOT / "docs" / "app" / "deck_charts.js").exists()
    assert "deck-stage:not(:defined){visibility:hidden}" in html, "정의 전 첫 슬라이드가 원본 크기로 번쩍인다"
    for sec in re.findall(r"<section [^>]*>", html):
        assert "position:" not in sec and "inset:" not in sec, "deck-stage 가 슬라이드를 직접 배치한다 — section 에 position/inset 금지"


def test_embeds_are_real_screens_replayed_without_geolocation_prompt(html):
    """3·4장 임베드는 실제 배포본을 9/5 22:06 발행분 재생(`?at=`)으로 띄운다 (2026-09-06 사용자 결정 — 라이브는 행사 뒤 사전표만 보인다).
    재생 시각은 재생 칩 목록에 있어야 한다 — 없으면 빈 화면이 뜬다."""
    go = re.search(r"<iframe[^>]*src=\"go\.html\?at=(\d{8}T\d{4})\"[^>]*>", html)
    assert go, "go.html?at= iframe 이 없다"
    assert "allow=" not in go.group(0), "위치 권한을 주면 발표 중 팝업이 뜬다 — allow 속성 금지"
    ops = re.search(r"<iframe[^>]*src=\"index\.html\?at=(\d{8}T\d{4})\"", html)
    assert ops, "index.html?at= iframe 이 없다"
    idx = ROOT / "docs" / "data" / "replay" / "20260905" / "index.json"
    if idx.exists():
        chips = {"20260905T" + c["at"] for c in json.loads(idx.read_text(encoding="utf-8"))["chips"]}
        assert go.group(1) in chips and ops.group(1) in chips, "임베드 재생 시각이 칩 목록에 없다"
    assert "deck/fallback_go.png" in html and "deck/fallback_ops.png" in html


def test_no_code_strips_on_deck(html):
    """v3 스펙(2026-09-09) — 글 밀도를 줄이려 코드 스트립·부록 없음. 수식(KaTeX)은 유지. code_strips.json 은 보고서용으로 남는다."""
    assert "data-strip=" not in html and "loadStrips" not in html, "코드 스트립이 남아 있다"
    assert html.count("katex") >= 2, "수식(KaTeX)은 남긴다"


def test_next_steps_come_from_report_and_lag_from_sources(html):
    """10장 다음 스텝 4항목은 보고서 §6.4 에 있는 것만 말한다. 3장의 발행 시차는 sources.json(9/5 실측)과 같은 값."""
    rep_html = (ROOT / "docs" / "report.html").read_text(encoding="utf-8")
    i = rep_html.index("6.4 다음 단계")
    sec = re.sub(r"<[^>]+>", " ", rep_html[i:i + 4000])
    for kw in ("M15", "LOO", "도착 시각", "ROI"):
        assert kw in html, f"덱 10장에 {kw} 가 없다"
        assert kw in sec, f"보고서 §6.4 에 {kw} 가 없다 — 덱이 보고서에 없는 계획을 말한다"
    lag = re.search(r"발행 시차 ([\d.]+)분", html)
    assert lag, "3장에 발행 시차가 없다"
    assert any(f"발행 시차 {lag.group(1)}분" in r["limit"] for r in _json("sources")["rows"]), "발행 시차 값이 sources.json 과 다르다"


def test_embed_fallback_message_respects_hidden(html):
    """2026-09-09 실기기 결함 — `.embed .fbmsg{display:flex}` 가 UA 의 `[hidden]{display:none}` 을 이겨
    "라이브 화면 — 통신 필요" 가 iframe 위를 항상 덮었다(9/6 '문구만 남았다' 의 진짜 원인). 저자 CSS 가 hidden 을 존중해야 한다."""
    assert '<div class="fbmsg" hidden>' in html
    assert re.search(r"\.fbmsg\[hidden\]\{display:none", html) or re.search(r"\.fbmsg:not\(\[hidden\]\)\{", html), \
        "fbmsg 의 display 규칙이 [hidden] 을 덮어쓴다 — .fbmsg[hidden]{display:none} 이 필요하다"


def test_fullscreen_hides_thumbnail_rail(html):
    """f 전체화면(9/9) 에서 왼쪽 썸네일 레일이 남으면 발표 화면이 아니다 — deck-stage 의 관찰 속성 `no-rail` 을 fullscreenchange 마다 맞춘다."""
    assert "toggleFullscreen" in html
    assert re.search(r'addEventListener\("fullscreenchange"', html), "fullscreenchange 리스너가 없다"
    assert 'setAttribute("no-rail"' in html and 'removeAttribute("no-rail")' in html, "no-rail 토글이 없다"


def test_radial_has_feeder_particle_flow():
    """보고서 그림 1 의 파티클 재생(피더역 → 여의도 인파 유입)을 덱 5장 방사형에도 — 사용자 요청 2026-09-09.
    규칙 동일: 유입 속도 = feeder_lag 시간대 승차 × 역별 비중. 모션 축소면 안 돌고, 슬라이드를 떠나면 멈춘다."""
    js = (ROOT / "docs" / "app" / "deck_charts.js").read_text(encoding="utf-8")
    body = js[js.index("function radialParticles"):js.index('CHARTS.radial = ["feeder_map", drawRadial];')]
    assert 'chartData("feeder_lag")' in js[js.index("function drawRadial"):js.index("function radialParticles")]
    assert "CHART_REDUCE" in body and 'hasAttribute("data-deck-active")' in body
    assert "y25.x[h]" in body and "s.share" in body, "유입 속도가 실측 시간대 × 역별 비중이어야 한다"


def test_presenter_view_wired(html):
    """p 키 → presenter.html 팝업, BroadcastChannel("deck") 로 본창·팝업·미리보기(role=cur|next) 동기화 (2026-09-09)."""
    assert (ROOT / "docs" / "presenter.html").exists()
    pres = (ROOT / "docs" / "presenter.html").read_text(encoding="utf-8")
    assert 'new BroadcastChannel("deck")' in html and 'new BroadcastChannel("deck")' in pres
    assert 'window.open("presenter.html"' in html, "p 키가 발표자 보기를 열어야 한다"
    assert 'role=cur' in pres and 'role=next' in pres and '_snthumb=1' in pres, "미리보기 iframe 은 레일 없는 role 모드"
    assert 'stage.goTo(' in html, "팝업의 ←→ 가 본창을 넘겨야 한다"


def test_progress_chain_marks_pipeline_step(html):
    """2~11장 상단 진행 사슬(디자인 항목 6, 2026-09-09) — 7단계 중 현재 단계 하나만 점등, 표지·클로징엔 없음. 되돌리면 이 테스트도 revert 된다."""
    want = {2: "문제", 3: "구성", 4: "예측", 5: "예측", 6: "실측", 7: "실측", 8: "경로", 9: "검증", 10: "검증", 11: "계획"}
    for sid, body in _sections(html):
        i = int(sid[1:])
        ons = re.findall(r'<span class="on">([^<]+)</span>', body)
        if i in want:
            assert ons == [want[i]], f"s{i}: 점등 {ons} ≠ {want[i]}"
            assert body.count('class="chain"') == 1 and len(re.findall(r'<div class="chain"[^>]*>(.*?)</div>', body)[0].split("<i>›</i>")) == 7
        else:
            assert 'class="chain"' not in body, f"s{i} 에는 사슬이 없어야 한다"


def test_speaker_notes_fit_five_minutes(html):
    """장당 ≈25초 — 한국어 발화 ≈ 분당 300자. 60~180자. 1장만 260자(인사·제품명·문제 제기까지 도입부, 2026-09-10 사용자 교체본 246자 ≈ 49초). 합계 ≤ 2,000자(≈6.7분, 시연 시간 포함 상한). 빈 노트는 발표 중 화면이 침묵한다.
    2026-09-09 밤 교정본 3차(짧은 노트)로 원래 상한 복귀."""
    notes = re.findall(r'<aside class="notes">(.*?)</aside>', html, re.S)
    assert len(notes) == N_SLIDES
    total = 0
    for i, n in enumerate(notes, 1):
        t = re.sub(r"\s+", " ", n).strip()
        cap = 260 if i == 1 else 180
        assert 60 <= len(t) <= cap, f"s{i} 노트 {len(t)}자 — 60~{cap}자로"
        total += len(t)
    assert total <= 2000, f"노트 합계 {total}자 ≈ {total / 300:.1f}분 — 5분 발표에 못 맞춘다"


def test_product_name_and_tagline_on_deck(html):
    """제품명은 2026-09-05 결정 — 「불꽃배웅」 · 「눈부신 밤의 끝, 집으로 가는 길까지.」. 덱 제목·1장·12장에 있어야 한다."""
    assert "<title>불꽃배웅 — 피치 덱</title>" in html
    assert html.count("불꽃배웅") >= 3, "이름이 1장·3장·12장에 있어야 한다"
    assert "눈부신 밤의 끝, 집으로 가는 길까지." in html
