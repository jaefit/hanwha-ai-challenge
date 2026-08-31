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
