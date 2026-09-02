"""모델 불변식 테스트. 실행: .venv/bin/python -m pytest tests -q
데이터 파일(data/derived/*.json)이 있어야 하는 테스트는 파일 없으면 skip.
"""
import json, math, pathlib, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import nowcast as N      # noqa: E402
import baseline as B     # noqa: E402
import backtrack as BT   # noqa: E402

DER = ROOT / "data" / "derived"


# ── 도달 지연 (거리 ÷ 밀도별 속도) ──
def test_lag_table_fractions_sum_to_one():
    for st, fr in N.lag_table().items():
        assert abs(sum(fr.values()) - 1.0) < 1e-9, st
        assert all(v >= 0 for v in fr.values()), st


def test_default_density_reproduces_legacy_40_60_for_yeouido5():
    same = N.lag_table()["여의도(5)"].get(0, 0.0)
    assert 0.25 <= same <= 0.45   # 기존 상수 40% 근처 (이벤트광장→여의도역 ≈39분)


def test_kladek_monotone_and_floor():
    speeds = [N.kladek(r) for r in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 5.4)]
    assert all(a >= b for a, b in zip(speeds, speeds[1:]))
    assert speeds[0] <= 1.34 + 1e-9
    assert N.kladek(5.0) >= 0.1 and N.kladek(5.4) >= 0.1   # 정체 하한: Kladek 원식은 5명/m² 에서 0.04 → 하한 없으면 도달시간이 발산


def test_arrival_split_edges():
    assert N.arrival_split(0) == {0: 1.0, 1: 0.0}
    s = N.arrival_split(90)
    assert abs(s[1] - 0.5) < 1e-9 and abs(s[2] - 0.5) < 1e-9


def test_denser_zone_means_later_arrival():
    early = N.lag_table({z: 1.5 for z in N.ZONES})["여의도(5)"].get(0, 0)
    late = N.lag_table({z: 4.0 for z in N.ZONES})["여의도(5)"].get(0, 0)
    assert early > late


# ── 배정·수요 보존·통제 ──
def test_assign_rows_sum_to_one():
    for d, row in N.ASSIGN.items():
        assert abs(sum(row.values()) - 1.0) < 1e-9, d
        assert set(row) <= set(N.CAP), d


def test_demand_is_conserved_without_lag():
    total = {h: 10000.0 for h in range(15, 25)}
    dirs = {"서": 0.4, "북서": 0.1, "북동": 0.2, "남": 0.1, "남동": 0.1, "기타": 0.1}
    lags = {st: {0: 1.0} for st in N.CAP}
    ex = N.compute_exits(total, dirs, 0.5, lags, hours=tuple(range(15, 25)))
    got = sum(v["demand"] for st in ex for v in ex[st].values())
    assert abs(got - 10 * 10000 * 0.5) / (10 * 10000 * 0.5) < 0.002   # 반올림 오차만


def test_closure_moves_yeouinaru_demand_to_yeouido5():
    total = {h: 10000.0 for h in range(15, 25)}
    dirs = {"북동": 1.0}   # 여의나루 0.7 / 여의도(5) 0.3
    lags = {st: {0: 1.0} for st in N.CAP}
    ex = N.compute_exits(total, dirs, 1.0, lags, hours=(19, 20, 21, 22))
    assert ex["여의나루(5)"][20]["closed"] and ex["여의나루(5)"][20]["demand"] == 0
    assert ex["여의나루(5)"][19]["demand"] > 0
    assert ex["여의도(5)"][20]["demand"] == pytest.approx(10000, rel=0.001)   # 0.3 + 0.7 이관
    assert ex["여의도(5)"][19]["demand"] == pytest.approx(3000, rel=0.001)


def test_load_is_demand_over_capacity_and_wait_nonnegative():
    total = {h: 50000.0 for h in range(15, 25)}
    dirs = {"서": 1.0}
    lags = {st: {0: 1.0} for st in N.CAP}
    ex = N.compute_exits(total, dirs, 1.0, lags, hours=(20, 21))
    v = ex["여의도(5)"][20]
    assert v["load"] == pytest.approx(v["demand"] / v["capacity"], abs=0.002)
    assert v["wait_min"] >= 0 and v["backlog"] >= 0


def test_observed_mode_conserves_station_totals_and_reassigns_closure():
    total = {h: 1.0 for h in range(15, 25)}          # 형태만 (정규화됨)
    lags = {st: {0: 1.0} for st in N.CAP}
    E = {st: 1000.0 for st in N.CAP}
    ex = N.compute_exits(total, None, None, lags, hours=(19, 20, 21, 22, 23), station_totals=E)
    got = {st: sum(v["demand"] for v in ex[st].values()) for st in ex}
    for st in N.CAP: assert got[st] == pytest.approx(1000, abs=3), st    # 역별 E 보존 (평가창 19~23시 안에서 분배, 재배정 없음)
    assert ex["여의나루(5)"][20]["demand"] == 0 and ex["여의나루(5)"][21]["demand"] == 0   # 통제 시간대 0
    # 통제 중 도착분은 해제 후 첫 개방 시간대로 이월 (2026-08-30 결정: 21:40 해제 직후 승차 → 22시). 평평한 곡선이면 19:22:23 = 1:3:1
    assert ex["여의나루(5)"][22]["demand"] == pytest.approx(600, abs=2)
    assert ex["여의나루(5)"][19]["demand"] == pytest.approx(200, abs=2) and ex["여의나루(5)"][23]["demand"] == pytest.approx(200, abs=2)
    assert ex["여의도(5)"][20]["demand"] == pytest.approx(200, abs=2)   # 개방 역은 이월 없음 (19~23 균등)


@pytest.mark.skipif(not (DER / "exit_shares.json").exists(), reason="exit_shares.json 없음")
def test_exit_shares_file_consistency():
    e = json.loads((DER / "exit_shares.json").read_text(encoding="utf-8"))
    for y, v in e["by_year"].items():
        assert abs(sum(v["share"].values()) - 1.0) < 1e-3, y
        assert set(v["E"]) == set(N.CAP), y
        assert all(x > 0 for x in v["E"].values()), y
    assert 0.95 < e["by_year"]["2024"]["total"] / e["by_year"]["2025"]["total"] < 1.05   # 규모 앵커: 2년 총량 안정


# ── 쇼 종료 앵커 ──
def test_shift_for_show_end():
    assert N.shift_for((21, 10)) == 40
    assert N.shift_for((21, 25)) == 55
    assert N.shift_for((20, 30)) == 0


# ── 출발지 → 키 · 회랑 ──
def test_origin_key_and_corridor():
    assert BT.origin_key("11560540") == "영등포" and B.corridor("11560540") == "서"
    assert BT.origin_key("41190000") == "부천" and B.corridor("41190000") == "서"
    assert BT.origin_key("28110000") == "인천" and B.corridor("28110000") == "서"
    assert BT.origin_key("11680000") == "강남" and B.corridor("11680000") == "남동"
    assert B.corridor("11440000") == "북서" and B.corridor("11110000") == "북동" and B.corridor("11590000") == "남"


# ── 사전 예측표 스키마 (파일 있을 때만) ──
@pytest.mark.skipif(not (DER / "exit_forecast_2026.json").exists(), reason="exit_forecast_2026.json 없음")
def test_prior_forecast_schema_and_bands():
    e = json.loads((DER / "exit_forecast_2026.json").read_text(encoding="utf-8"))
    assert set(e["exits"]) == set(N.CAP)
    for st, byh in e["exits"].items():
        assert set(byh) == {"19", "20", "21", "22", "23"}, st
        for h, v in byh.items():
            if v["closed"]:
                assert v["load"] is None
            else:
                assert v["load_lo"] <= v["load"] <= v["load_hi"], (st, h)
                assert 0 <= v["load"] < 5
    assert e["exits"]["여의나루(5)"]["20"]["closed"] and e["exits"]["여의나루(5)"]["21"]["closed"]
    for h, rank in e["ranking_by_hour"].items():
        loads = [r[1] for r in rank]
        assert loads == sorted(loads), h
    assert abs(sum(e["direction_share"].values()) - 1.0) < 0.02


# ── 백테스트 회귀 가드 (src/backtest.py 산출물 있을 때만) ──
@pytest.mark.skipif(not (DER / "backtest.json").exists(), reason="backtest.json 없음")
def test_backtest_errors_within_recorded_bounds():
    b = json.loads((DER / "backtest.json").read_text(encoding="utf-8"))
    A, B = b["modes"]["A_in_sample"], b["modes"]["B_cross_year"]
    for y in ("2024", "2025"):
        assert A[y]["total_err_boarding"] <= 0.35, (y, A[y]["total_err_boarding"])      # 2026-08-30 기록 0.24/0.29 — 넘으면 모델 회귀
        assert B[y]["total_err_boarding"] <= 0.55, (y, B[y]["total_err_boarding"])      # cross-year 0.44/0.44 (연도 간 규모 이동 포함)
        assert A[y]["grade_hit_rate"] >= 0.8, y
        assert B[y]["source_year"] != y and A[y]["source_year"] == y
        for st, v in A[y]["stations"].items():
            for h, r in v["by_hour"].items():
                if r["closed"]: assert r["pred"] == 0, (y, st, h)


# ── α 데이터동화 (격자 사후분포) ──
def test_assimilate_no_obs_is_prior():
    r = N.assimilate([])
    p10, p50, p90 = r["alpha"]
    assert abs(p50 - 1.0) < 0.01 and abs(p10 - 0.73) < 0.03 and abs(p90 - 1.38) < 0.04   # LogNormal(0, 0.25)
    assert r["n_obs"] == 0 and not r["edge_hit"]
    assert abs(sum(r["weights"]) - 1.0) < 1e-9


def test_assimilate_double_obs_shifts_and_narrows():
    obs = [(1000.0, 500.0, 0.0, 0.15, 25.0, "alighting")] * 14        # y = 2 × A → α≈2
    r = N.assimilate(obs)
    p10, p50, p90 = r["alpha"]
    prior = N.assimilate([])["alpha"]
    assert p50 > 1.5 and p10 <= p50 <= p90
    assert (p90 - p10) < 0.5 * (prior[2] - prior[0])
    assert abs(sum(r["weights"]) - 1.0) < 1e-9


def test_assimilate_affine_obs_uses_baseline_term():
    obs = [(1300.0, 500.0, 800.0, 0.2, 0.0, "boarding")] * 9           # y = A·1 + B → α≈1
    p10, p50, p90 = N.assimilate(obs)["alpha"]
    assert abs(p50 - 1.0) < 0.05


def test_assimilate_extreme_obs_hits_edge_and_clamps():
    obs = [(2500.0, 500.0, 0.0, 0.15, 0.0, "alighting")] * 14          # y = 5 × A → 격자 상한 3.0
    r = N.assimilate(obs)
    assert r["edge_hit"] and r["alpha"][1] <= 3.0


def test_observations_coverage_fallback_and_estimate():
    ex1 = {h: 10000.0 for h in range(15, 25)}; base = {h: 1000.0 for h in range(5, 25)}
    obs, meta = N._observations([], ex1, base)
    assert obs == [] and meta["coverage_c"] == 1.3 and meta["coverage_basis"] == "fallback"
    def rec(area, hhmm, on=None, off=None):
        s = {}
        if on is not None: s |= {"SUB_30WTHN_GTON_PPLTN_MIN": str(on - 50), "SUB_30WTHN_GTON_PPLTN_MAX": str(on + 50)}
        if off is not None: s |= {"SUB_30WTHN_GTOFF_PPLTN_MIN": str(off - 50), "SUB_30WTHN_GTOFF_PPLTN_MAX": str(off + 50)}
        return {"kind": "citydata", "area": area, "ts": f"2026-09-05T{hhmm}:10", "sub_live": s}
    recs = [rec("여의도", f"{h:02d}:{m:02d}", on=1000) for h in (14, 15, 16) for m in (25, 55)]   # 30분 승차 1000 = 평시 500 × 2 → c=2
    recs += [rec("여의도한강공원", "16:55", off=2 * N.YEOUINARU_GTOFF_BASE[16] // 2)]              # 16:30~17:00 하차 = 기준 2배
    recs += [rec("여의도", "21:55", on=3000)]
    obs, meta = N._observations(recs, ex1, base)
    assert meta["coverage_basis"] == "same_day_14_17h" and abs(meta["coverage_c"] - 2.0) < 0.05
    kinds = [o[5] for o in obs]
    assert kinds.count("alighting") == 1 and kinds.count("boarding") == 1
    y, A, B, rel, ab, k = [o for o in obs if o[5] == "boarding"][0]
    assert A == pytest.approx(2.0 * 10000 / 2) and B == pytest.approx(2.0 * 1000 / 2) and rel == 0.2


def test_assimilate_single_small_obs_keeps_band_wide():
    # 관측 1건(y = 0.6·A)으로 밴드가 ±5% 로 붕괴하면 안 된다. σ 는 관측값과 α=1 예측 중 큰 쪽 기준(과신 방지, α 무관)
    one = N.assimilate([(1200.0, 2000.0, 0.0, 0.15, 0.0, "alighting")])["alpha"]
    many = N.assimilate([(1200.0, 2000.0, 0.0, 0.15, 0.0, "alighting")] * 14)["alpha"]
    assert 0.6 < one[1] < 0.85 and (one[2] - one[0]) > 0.25          # 1건: 관측 0.6 과 사전 1.0 사이로 수축, 밴드 넓게 유지
    assert abs(many[1] - 0.6) < 0.05 and (many[2] - many[0]) < (one[2] - one[0]) / 2   # 14건: 관측으로 수렴, 밴드 절반 이하


# ── 오차표 (evaluate.py) ──
def test_evaluate_first_forecast_and_ape():
    import evaluate as E
    recs = [
        {"area": "여의도한강공원", "ts": "2026-09-05T12:05:00", "fcst": [{"t": "2026-09-05 14:00", "min": 100, "max": 200, "lvl": "보통"}], "ppltn_min": 90, "ppltn_max": 110},
        {"area": "여의도한강공원", "ts": "2026-09-05T12:10:00", "fcst": [{"t": "2026-09-05 14:00", "min": 999, "max": 999}], "ppltn_min": 100, "ppltn_max": 120},
        {"area": "여의도한강공원", "ts": "2026-09-05T13:58:00", "fcst": [], "ppltn_min": 140, "ppltn_max": 160},
    ]
    fc = E.first_forecast_for(recs)
    assert fc["2026-09-05 14:00"]["min"] == 100 and fc["2026-09-05 14:00"]["lead_min"] == 115   # 가장 이른 스냅샷이 이긴다
    act = E.actual_pop(recs)
    assert act["2026-09-05 14:00"] == 150 and act["2026-09-05 12:00"] == 100                     # 정시 최근접(±30분)
    assert E.ape(100, 150) == 0.5 and E.ape(0, 5) is None


# ── 관람지(watch) 수집 — 쿼터·배정·게이팅 (9/1 추가) ──
def _collector():
    import importlib, os
    os.environ.setdefault("FEEDERS", "default"); os.environ.setdefault("WATCH", "default")
    import collector_api as C
    return importlib.reload(C)


def test_subway_key_budget_within_daily_limit():
    """실시간 지하철 인증키는 하루 1,000건(열린데이터광장 이용방법). 일반키·피더키는 일 한도 미공지 — 2026-09-02 정정."""
    C = _collector()
    over = {k: v for k, v in C.budget().items() if k.startswith("지하철키") and v > 1000}
    assert not over, over


def test_watch_does_not_shift_feeder_key_assignment():
    """관람지를 뒤에 붙였으므로 기존 피더의 키 배정이 그대로여야 재현 가능하다."""
    C = _collector()
    if len(C.FEEDER_KEYS) < 2: pytest.skip("피더 전용 키 2개 필요")
    for i, name in enumerate(C.FEEDERS):
        assert C.feeder_key(name) == C.FEEDER_KEYS[i % len(C.FEEDER_KEYS)], name


def test_watch_roles_and_core_key_isolation():
    C = _collector()
    assert C.role_of("여의도한강공원") == "core"
    assert C.role_of("노들섬") == "watch"
    assert C.role_of("강남역") == "feeder"
    if C.FEEDER_KEYS:                                   # 코어 쿼터에 관람지가 섞이면 안 됨
        assert all(C.feeder_key(w) != C.KG for w in C.WATCH)


def test_feeder_pool_reads_numbered_feeder_keys_only():
    """전용 피더키 FEEDER, FEEDER2, FEEDER3 … 를 번호순으로. 빈 값 제외. 지하철키는 섞지 않는다(1,000/일은 지하철 호출에만 쓸 것)."""
    C = _collector()
    env = {"SEOUL_KEY_GENERAL": "g", "SEOUL_KEY_SUBWAY": "s1", "SEOUL_KEY_SUBWAY2": "s2",
           "SEOUL_KEY_FEEDER3": "f3", "SEOUL_KEY_FEEDER": "f1", "SEOUL_KEY_FEEDER2": ""}
    assert C.feeder_pool(env) == ["f1", "f3"]
    assert C.feeder_pool({"SEOUL_KEY_GENERAL": "g", "SEOUL_KEY_SUBWAY": "s1"}) == []


def test_missing_feeder_keys_fall_back_to_general_key(monkeypatch):
    # 일반 인증키는 일 한도가 없다(열린데이터광장 이용방법, 2026-09-02 확인) → 피더키 없으면 끄지 말고 일반키로 수집한다
    C = _collector()
    monkeypatch.setattr(C, "FEEDER_KEYS", [])
    assert C.feeder_key("강남역") == C.KG and C.feeder_key("노들섬") == C.KG


def test_budget_counts_every_planned_call_once_per_actual_key():
    """budget() 은 키 실체 기준으로 합산한다 — 같은 값이 두 이름으로 등록돼 있어도 한 줄, 빠지는 호출도 없어야 한다."""
    C = _collector()
    if not C.FEEDER_KEYS: pytest.skip("피더키 없음")
    ticks = 3600 // C.INTERVAL
    planned = (len(C.CORE) * 24 * ticks + len(C.STATIONS) * len(C.SUBWAY_HOURS) * ticks
               + len(C.FEEDERS) * len(C.FEEDER_HOURS) * ticks + len(C.WATCH) * len(C.WATCH_HOURS) * ticks)
    b = C.budget()
    assert abs(sum(b.values()) - planned) <= len(C.SUBWAY_KEYS)   # 지하철 회전은 올림 배정 → 키 수만큼 오차 허용
    assert len(b) == len({C.KG, *C.SUBWAY_KEYS, *C.FEEDER_KEYS})   # 같은 키가 두 줄로 나뉘면 안 된다


def test_watch_hours_are_festival_window_only():
    C = _collector()
    assert set(C.WATCH_HOURS) == set(range(17, 24))
    assert not (set(C.WATCH_HOURS) & set(range(0, 17)))


# ── 당일 운영 방어 (2026-09-01 red team C2·C4·C5·H5) ──
@pytest.fixture
def show_end_file():
    """data/live/show_end.txt 를 쓰고 원상복구."""
    p = N.LIVE / "show_end.txt"; orig = p.read_text(encoding="utf-8") if p.exists() else None
    def write(text):
        p.write_text(text, encoding="utf-8"); return N.show_end_actual([])
    yield write
    if orig is None: p.unlink(missing_ok=True)
    else: p.write_text(orig, encoding="utf-8")


def test_show_end_arg_missing_value_exits_instead_of_crashing():
    # C4: 값 없이 --show-end 만 치면 IndexError 로 죽었다 → 사용법 안내 후 종료여야 한다
    with pytest.raises(SystemExit) as e:
        N.show_end_actual(["--show-end"])
    assert e.value.code != 0


def test_show_end_arg_without_colon_exits_instead_of_crashing():
    # C4: '2110' 은 ValueError(unpack) 로 죽었다
    with pytest.raises(SystemExit) as e:
        N.show_end_actual(["--show-end", "2110"])
    assert e.value.code != 0


def test_show_end_arg_valid_is_accepted():
    assert N.show_end_actual(["--show-end", "21:25"]) == ((21, 25), "arg")


def test_show_end_file_bad_format_is_reported_not_silently_ignored(show_end_file):
    # C4: 형식이 틀리면 조용히 planned 로 떨어져 "기입했는데 반영 안 됨" 을 알 수 없었다
    for bad in ("2110", "21시10분", ""):
        se, src = show_end_file(bad)
        assert se == N.SHOW_END_2026 and src == "planned_invalid_file", bad


def test_show_end_file_out_of_range_is_rejected(show_end_file):
    # C4: '25:99' 가 통과해 유출 곡선이 369분(6시간) 밀렸다
    for bad in ("25:99", "03:00", "18:59"):
        se, src = show_end_file(bad)
        assert se == N.SHOW_END_2026 and src == "planned_invalid_file", bad


def test_show_end_file_valid_is_used(show_end_file):
    assert show_end_file("21:35\n") == ((21, 35), "file")


def _cov_recs(pairs):
    """[(hh, mm, 30분 승차)] → citydata 레코드"""
    return [{"kind": "citydata", "area": "여의도", "ts": f"2026-09-05T{h:02d}:{m:02d}:10",
             "sub_live": {"SUB_30WTHN_GTON_PPLTN_MIN": str(v - 50), "SUB_30WTHN_GTON_PPLTN_MAX": str(v + 50)}}
            for h, m, v in pairs]


def test_coverage_window_includes_17h():
    # H5: 주석·문서·보고서 §3.4 는 "14~17시" 인데 코드는 14~16 시만 봤다
    ex1 = {h: 10000.0 for h in range(15, 25)}; base = {h: 1000.0 for h in range(5, 25)}
    recs = _cov_recs([(17, 25, 1000), (17, 55, 1000), (16, 55, 1000)])
    _, meta = N._observations(recs, ex1, base)
    assert meta["coverage_basis"] == "same_day_14_17h" and abs(meta["coverage_c"] - 2.0) < 0.05


def test_coverage_rejects_wildly_spread_samples():
    # H5: c 는 α 에 반비례한다. 창끼리 크게 어긋나면 중앙값을 믿지 말고 고정값으로
    ex1 = {h: 10000.0 for h in range(15, 25)}; base = {h: 1000.0 for h in range(5, 25)}
    recs = _cov_recs([(14, 25, 400), (14, 55, 1000), (15, 25, 2800), (15, 55, 600), (16, 25, 2400)])
    _, meta = N._observations(recs, ex1, base)
    assert meta["coverage_basis"] == "fallback_spread" and meta["coverage_c"] == N.COVERAGE_FALLBACK
    assert meta["coverage_spread"] > 0.3


def test_coverage_keeps_tight_samples():
    ex1 = {h: 10000.0 for h in range(15, 25)}; base = {h: 1000.0 for h in range(5, 25)}
    recs = _cov_recs([(14, 25, 980), (14, 55, 1000), (15, 25, 1020), (15, 55, 1000)])
    _, meta = N._observations(recs, ex1, base)
    assert meta["coverage_basis"] == "same_day_14_17h" and meta["coverage_spread"] <= 0.3


def test_collector_non_json_body_surfaces_api_message():
    # C5: 인증 실패·쿼터 초과는 HTTP 200 + XML 로 온다. JSONDecodeError 한 줄로 뭉개면 당일 원인 판별 불가
    C = _collector()
    body = "<RESULT><CODE>INFO-100</CODE><MESSAGE><![CDATA[인증키가 유효하지 않습니다.]]></MESSAGE></RESULT>"
    with pytest.raises(Exception) as e:
        C.parse_body(body)
    assert "INFO-100" in str(e.value) and "인증키" in str(e.value)


def test_collector_redacts_keys_from_error_text():
    # 오류 문자열을 로그에 그대로 쓰므로 키가 섞여 들어갈 여지를 막는다
    C = _collector()
    key = C.KG
    assert len(key) >= 12
    out = C.redact(f"boom {key} tail")
    assert key not in out and "boom" in out and "tail" in out


def test_publish_ignores_generated_when_deciding_to_republish():
    # C2: 비교 대상에 generated(now) 가 들어 있어 "변경 없으면 커밋 생략" 이 한 번도 성립하지 않았다
    import publish as P
    a = {"generated": "2026-09-05T20:00:00", "forecast": {"alpha": 1.0}, "cctv": {}}
    b = {"generated": "2026-09-05T20:05:00", "forecast": {"alpha": 1.0}, "cctv": {}}
    c = {"generated": "2026-09-05T20:05:00", "forecast": {"alpha": 1.2}, "cctv": {}}
    assert P.same_payload(P.render(a), b)
    assert not P.same_payload(P.render(a), c)


def test_dashboard_closure_copy_is_conditional_per_hour():
    # H2: 통제 문구가 고정 문자열이라 20시 탭에서도 "무정차 통과" 로 단정했다 (실제 20:00~20:40 정차)
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "CLOSED_NOTE" in html, "시간대별 통제 문구 분기가 없다"
    assert "예년엔 조기 무정차" in html, "예년 조기 무정차 이력을 알리는 문구가 없다"


def test_report_has_table_3_3():
    # L1: 표 번호가 3-2 → 3-4 로 건너뛰었다
    html = (ROOT / "docs" / "report.html").read_text(encoding="utf-8")
    assert "표 3-3" in html


def test_push_aborts_a_conflicting_rebase_instead_of_leaving_it_in_progress(tmp_path, monkeypatch):
    """C2 후속: pull --rebase 가 충돌하면 rebase 진행 상태로 남아 이후 모든 틱의 커밋이 실패한다.
    실패는 실패대로 알리되, 저장소는 깨끗한 상태로 돌려놓아야 한다."""
    import subprocess as sp
    import publish as P

    def git(cwd, *a): return sp.run(["git", *a], cwd=cwd, capture_output=True, text=True)
    origin = tmp_path / "origin.git"; sp.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    def clone(name):
        d = tmp_path / name; sp.run(["git", "clone", "-q", str(origin), str(d)], check=True)
        git(d, "config", "user.email", "t@t"); git(d, "config", "user.name", "t")
        git(d, "config", "rebase.autoStash", "false")
        return d
    a = clone("a")
    (a / "f.json").write_text("base"); git(a, "add", "-A"); git(a, "commit", "-qm", "base")
    git(a, "branch", "-M", "main"); git(a, "push", "-q", "origin", "main")
    b = clone("b"); git(b, "checkout", "-q", "main")
    # 두 기기가 같은 파일을 서로 다르게 고쳐 올린다 → rebase 충돌
    (b / "f.json").write_text("from-other-machine"); git(b, "add", "-A"); git(b, "commit", "-qm", "other")
    git(b, "push", "-q", "origin", "main")
    (a / "f.json").write_text("from-us"); git(a, "add", "-A"); git(a, "commit", "-qm", "ours")

    monkeypatch.setattr(P, "ROOT", a)
    monkeypatch.setattr(P, "FAIL_STREAK", tmp_path / "streak")
    assert P.push() is False                       # 충돌은 push 로 해결되지 않는다 — 실패로 알려야 한다
    assert not (a / ".git" / "rebase-merge").exists() and not (a / ".git" / "rebase-apply").exists(), \
        "rebase 진행 상태가 남았다 — 이후 모든 틱의 커밋이 실패한다"
    assert git(a, "status", "--porcelain").stdout.strip() == ""    # 작업트리도 깨끗해야 다음 틱이 돈다


def test_publish_carries_confidence_fields_to_web():
    """혼잡장이 신뢰도로 가중하려면 density·calibrated·confidence·flags 가 브라우저까지 가야 한다.
    이게 빠져 있어서 공개 대시보드가 count 1.0명인 카메라를 '심각'으로 칠하고 있었다."""
    import publish as P
    src = (ROOT / "src" / "publish.py").read_text(encoding="utf-8")
    for f in ("density", "calibrated", "confidence", "flags"):
        assert f'"{f}"' in src, f"publish 화이트리스트에 {f} 없음"
    rec = {"ts": "2026-09-05T20:00:00", "cam_id": "331", "name": "63빌딩", "ok": True, "count": 1.0,
           "occupancy": 1.0, "flow": 0.9, "density": 0.0, "level": "심각",
           "confidence": "low", "flags": ["bg_fail"], "calibrated": True}
    out = P.slim_cctv(rec)
    assert out["confidence"] == "low" and out["flags"] == ["bg_fail"]
    assert out["density"] == 0.0 and out["calibrated"] is True


def _strip_js(src):
    """주석·문자열·정규식 리터럴을 지운다 — 그 안의 낱말이 호출로 보이면 안 된다."""
    import re
    src = re.sub(r"/\*[\s\S]*?\*/", " ", src)
    src = re.sub(r"//[^\n]*", " ", src)
    src = re.sub(r"`(?:\\.|[^`\\])*`", '""', src)
    src = re.sub(r"'(?:\\.|[^'\\\n])*'", '""', src)
    src = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', src)
    return src


def test_dashboard_has_no_undefined_local_functions():
    """정규식 패치가 함수를 통째로 삼킨 적이 있다 — 8d605a7 에서 routeRisk 교체가
    RouteHeap·routeAstar 를 먹었고, 경로 찾기가 'routeAstar is not defined' 로 죽었다.
    node --check 는 문법만 보므로 못 잡는다. 호출되는데 정의가 없는 이름을 찾는다."""
    import re
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    script = _strip_js("\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html)))
    field_js = _strip_js((ROOT / "docs" / "app" / "field.js").read_text(encoding="utf-8"))

    def defs(src):
        d = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", src))
        d |= set(re.findall(r"\bclass\s+([A-Za-z_$][\w$]*)", src))
        # 선언 형태 name(...){ — 클래스 메서드·getter·축약 메서드까지 잡는다
        d |= set(re.findall(r"([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{", src))
        # 대입 대상 (const a=1,b=2 처럼 콤마로 이어진 것 포함). 넓게 잡아도 목적은 유지된다 —
        # 통째로 사라진 이름은 어디에도 대입되지 않는다.
        d |= set(re.findall(r"([A-Za-z_$][\w$]*)\s*=[^=>]", src))
        return d

    defined = defs(script) | defs(field_js)
    keywords = {"if", "for", "while", "switch", "catch", "return", "typeof", "function", "new",
                "await", "delete", "void", "in", "of", "do", "else", "yield"}
    globals_ = {"Math", "Number", "String", "Object", "Array", "Map", "Set", "JSON", "Date", "Image",
                "Error", "Promise", "RegExp", "Float64Array", "Boolean",
                "parseInt", "parseFloat", "isFinite", "isNaN", "encodeURIComponent", "decodeURIComponent",
                "setTimeout", "setInterval", "clearTimeout", "requestAnimationFrame", "addEventListener",
                "fetch", "getComputedStyle", "console", "maplibregl", "Field", "localStorage",
                "document", "window", "performance", "alert"}
    called = set(re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", script))
    missing = sorted(called - defined - keywords - globals_)
    assert not missing, f"정의 없이 호출되는 이름: {missing}"
