"""피치 덱 슬라이드용 데이터 내보내기 — 읽기 전용.

모델 코드(`src/nowcast.py` · `src/backtest.py` · `docs/app/field.js` · routing)는 건드리지 않는다.
여기서는 이미 만들어진 `data/derived/*.json` 을 읽고, `nowcast` 의 순수 함수를 호출만 한다.

출력이 `docs/deck/` 인 이유: `src/publish.py:109` 가 `git add docs/data` 로 디렉터리를 통째로
스테이징한다. 덱 데이터를 그 아래 두면 5분마다 도는 발행 커밋이 반쯤 쓴 파일을 쓸어담는다.

실행: .venv/bin/python tools/deck_data.py
"""
import json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import nowcast as N      # noqa: E402

DER = ROOT / "data" / "derived"
OUT = ROOT / "docs" / "deck"


def _load(name):
    return json.loads((DER / f"{name}.json").read_text(encoding="utf-8"))


# ── ① 피더 선행 (실측) ─────────────────────────────────────────────
def feeder():
    """피더 승차가 여의도 도착을 1시간 선행한다 — X 를 1시간 밀면 두 곡선이 포개진다.

    단서를 데이터에 같이 싣는다. X 는 순수 관측이 아니라 OD 총량 제약으로 귀속한 값이고,
    Y 는 5호선(여의도·여의나루) 하차 초과분만이다. 슬라이드가 이 문구를 그대로 쓴다.
    """
    d = _load("feeder_leadlag")
    years = {}
    for y, v in d["by_year"].items():
        years[y] = {
            "x": v["X_attributed_by_hour"],
            "y": v["Y_alight_excess_by_hour"],
            "r_lag0": v["pearson_lag0"],
            "r_lag1": v["pearson_lag1"],
            "n": v["n"],
        }
    top = [{"name": k, "lines": v["lines"], "gu": v["gu"], "share": v["share_of_attributed"],
            "travel_min": v["travel_min_est"]}
           for k, v in sorted(d["top_feeders"].items(), key=lambda kv: -kv[1]["share_of_attributed"])][:6]
    return {
        "hours": d["hours"],
        "years": years,
        "pooled_r_lag1": d["pooled"]["lag1"]["pearson"],
        "pooled_n": d["pooled"]["lag1"]["n"],
        "top_feeders": top,
        "caveats": d["notes"],
        "source": "data/derived/feeder_leadlag.json",
    }


# ── ③ 백테스트 (실측) ─────────────────────────────────────────────
def backtest():
    """타임머신 시험 — 한 해로 만든 모델이 다른 해를 맞히나 (B_cross_year).

    역·시간별 예측/실측과 등급을 그대로 낸다. 슬라이드는 막대가 차오르며 등급 적중을 센다.
    """
    d = _load("backtest")
    modes = {}
    for mode in ("A_in_sample", "B_cross_year"):
        m = d["modes"][mode]
        years = {}
        for y in ("2024", "2025"):
            v = m[y]
            rows = []
            for st, sv in v["stations"].items():
                for h, hv in sorted(sv["by_hour"].items(), key=lambda kv: int(kv[0])):
                    rows.append({"station": st, "hour": int(h), "pred": hv["pred"], "obs": hv["obs"],
                                 "pred_grade": hv["pred_grade"], "obs_grade": hv["obs_grade"],
                                 "closed": hv["closed"]})
            years[y] = {"rows": rows, "grade_hit_rate": v["grade_hit_rate"],
                        "grade_hits": v["grade_hits"], "grade_n": v["grade_n"],
                        "err_boarding": v["total_err_boarding"], "err_excess": v["total_err_excess"]}
        modes[mode] = {"years": years, "summary": m["summary"]}
    return {"modes": modes, "hours": d["hours"], "stations": d["stations"],
            "observed_source": d["observed_source"], "source": "data/derived/backtest.json"}


# ── ② α 격자 사후분포 (방법 설명 — 관측 y 는 만든 값) ──────────────
ALPHA_TRUE = 1.15   # 이 값을 기계가 찾아내는지 보이려는 것이다. 측정값이 아니다.


def alpha():
    """사후분포가 관측을 먹으며 좁아지는 과정.

    **실측이 아니다.** 사전분포·격자·σ 식·A(2년 평균 30분 기준 하차)는 전부 코드의 실제 값이고,
    관측 y 만 α=ALPHA_TRUE 를 가정해 만들었다. 슬라이드에 그대로 적는다 —
    2025 하차의 연도별 시간대 실측이 derived 에 없어(`YEOUINARU_GTOFF_BASE` 는 2년 평균 상수)
    실제 재생은 9/5 관측 이후에야 가능하다.

    `nowcast.assimilate` 를 그대로 호출한다. 여기서 격자·사전·σ 를 다시 구현하지 않는다.
    """
    obs, frames = [], []
    for h in range(12, 19):
        for half in (0, 1):
            A = N.o1_base_inc(h, half, 0)
            if A < N.O1_MIN_BASE_INC:
                continue
            y = round(A * ALPHA_TRUE)
            obs.append((y, A, 0.0, N.O1_REL_SIGMA, 0.0, "alighting"))
            post = N.assimilate(obs)
            frames.append({"n": len(obs), "label": f"{h}:{'00' if half == 0 else '30'}",
                           "y": y, "A": round(A, 1),
                           "alpha": post["alpha"], "weights": [round(w, 6) for w in post["weights"]],
                           "edge_hit": post["edge_hit"]})
    prior = N.assimilate([])
    return {
        "grid": [round(a, 4) for a in N.ALPHA_GRID],
        "prior_sigma": N.PRIOR_SIGMA,
        "prior_weights": [round(w, 6) for w in prior["weights"]],
        "prior_alpha": prior["alpha"],
        "frames": frames,
        "alpha_true": ALPHA_TRUE,
        "synthetic": True,
        "note": ("사전분포·격자 61점·σ 식·A(2년 평균 30분 기준 하차)는 코드의 실제 값. "
                 f"관측 y 만 α={ALPHA_TRUE} 를 가정해 만들었다 — 추정기가 그 값을 찾아가는지 보이려는 것이다."),
        "source": "src/nowcast.py assimilate()/o1_base_inc()",
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("feeder_lag", feeder), ("backtest_bars", backtest), ("alpha_grid", alpha)):
        p = OUT / f"{name}.json"
        p.write_text(json.dumps(fn(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.1f}KB")


if __name__ == "__main__":
    main()
