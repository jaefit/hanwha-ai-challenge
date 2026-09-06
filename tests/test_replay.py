"""발행 스냅샷 재생(`?at=YYYYMMDDTHHMM`) 검사 — 2026-09-06 Task 12.

재생은 "그 시각 화면을 그대로 다시 보여준다"가 전부다. 그러려면 ① 재생 파일이 당일 발행분과 같은 모양·같은 값이어야 하고
② 두 화면의 시계가 전부 재생 시각으로 묶여야 한다. 시계가 하나라도 실제 `Date.now()` 를 보면 "12시간 넘게 오래됨 → 사전표"
폴백이 튀어 재생 화면이 사전 예측표로 바뀐다. 그래서 `Date.now()`·`new Date()` 잔류를 정적으로 센다.
"""
import json, pathlib, re, shutil, subprocess, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
REPLAY_DIR = ROOT / "docs" / "data" / "replay" / "20260905"
PAGES = {"index": ROOT / "docs" / "index.html", "go": ROOT / "docs" / "go.html"}


def _index():
    p = REPLAY_DIR / "index.json"
    if not p.exists():
        pytest.skip("docs/data/replay/20260905/index.json 없음 — tools/replay_build.py 먼저 실행")
    return json.loads(p.read_text(encoding="utf-8"))


def test_replay_chips_match_deck_times():
    """덱 s11 과 재생 칩은 같은 6시각이어야 한다 — 한쪽만 바꾸면 발표 중 버튼이 빈 화면을 연다."""
    from deck_data import REPLAY_AT
    idx = _index()
    assert [c["at"] for c in idx["chips"]] == [a for a, _ in REPLAY_AT]
    for c in idx["chips"]:
        assert (REPLAY_DIR / f"{c['at']}.json").exists(), c


def test_replay_files_are_latest_shaped_verbatim_snapshots():
    """재생 파일 = latest.json 모양(generated·forecast·cctv). forecast 는 발행 스냅샷 그대로, CCTV 는 그 분 이전 마지막 레코드."""
    idx = _index()
    hist = ROOT / "data" / "live" / "forecast_history" / "20260905"
    for c in idx["chips"]:
        d = json.loads((REPLAY_DIR / f"{c['at']}.json").read_text(encoding="utf-8"))
        assert set(d) >= {"generated", "forecast", "cctv", "replay"}, c
        g = d["generated"]
        assert g[11:13] + g[14:16] == c["at"], f"{c['at']}: generated {g}"
        assert len(d["forecast"]["exits"]) == 7 and d["forecast"]["alpha"] is not None
        assert d["replay"]["at"] == f"20260905T{c['at']}"
        for cam, v in d["cctv"].items():
            assert v["ts"] <= g, f"{c['at']} cam {cam}: CCTV {v['ts']} 가 발행 뒤다"
            assert set(v) >= {"ts", "name", "level", "count", "occupancy", "flow", "ok"}, cam
        if hist.exists():
            snap = json.loads((hist / f"{c['at']}.json").read_text(encoding="utf-8"))
            assert d["forecast"] == snap, f"{c['at']}: forecast 가 발행 스냅샷과 다르다 — 재계산 금지"


@pytest.mark.parametrize("page", sorted(PAGES))
def test_page_clock_is_fully_overridable(page):
    """두 화면의 시계는 NOW() 하나로만 읽는다. 캐시버스터(`?"+Date.now()`)와 NOW 정의만 예외."""
    html = PAGES[page].read_text(encoding="utf-8")
    assert '<script src="app/replay.js"></script>' in html, "replay.js 미포함"
    assert "Replay.parse(location.search)" in html and re.search(r"const NOW=\(\)=>REPLAY\?REPLAY\.now:Date\.now\(\)", html), "NOW() 정의 없음"
    stray = []
    for m in re.finditer(r"Date\.now\(\)", html):
        ctx = html[max(0, m.start() - 24): m.start()]
        if ctx.endswith('?"+') or "REPLAY?REPLAY.now:" in ctx:
            continue
        stray.append(html[max(0, m.start() - 60): m.end() + 10])
    assert not stray, f"{page}: NOW() 밖 Date.now() 잔류 {len(stray)}건\n" + "\n".join(stray)
    bare = re.findall(r"new Date\(\)", html)
    assert not bare, f"{page}: 인자 없는 new Date() {len(bare)}건 — new Date(NOW()) 로"
    assert re.search(r"if\(!REPLAY\)setInterval\(load", html), f"{page}: 재생 중 자동 갱신이 안 꺼진다"
    assert "Replay.mount(" in html, f"{page}: 재생 배너 없음"


def test_go_replay_skips_geolocation():
    """재생 중 발표자의 실제 위치(여의도 밖)를 잡으면 경로가 엉뚱해진다 — 이벤트광장 기준으로 고정."""
    html = PAGES["go"].read_text(encoding="utf-8")
    assert re.search(r"if\(REPLAY\)setGeo\(\"denied\"\);else askGeo\(\);", html)


def test_replay_module_spec():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    r = subprocess.run([node, str(ROOT / "tests" / "replay_spec.mjs")], cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip(), f"replay_spec.mjs 결과 없음\n{r.stderr[:1500]}"
    res = json.loads(r.stdout)
    failed = [x for x in res if not x["ok"]]
    assert not failed, "\n".join(f"{x['name']}: {x.get('detail')}" for x in failed)
    assert len(res) >= 6
