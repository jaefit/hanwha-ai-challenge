"""피치 덱 슬라이드용 데이터 내보내기 — 읽기 전용.

모델 코드(`src/nowcast.py` · `src/backtest.py` · `docs/app/field.js` · routing)는 건드리지 않는다.
여기서는 이미 만들어진 `data/derived/*.json` 을 읽고, `nowcast` 의 순수 함수를 호출만 한다.

출력이 `docs/deck/` 인 이유: `src/publish.py:109` 가 `git add docs/data` 로 디렉터리를 통째로
스테이징한다. 덱 데이터를 그 아래 두면 5분마다 도는 발행 커밋이 반쯤 쓴 파일을 쓸어담는다.

실행: .venv/bin/python tools/deck_data.py
"""
import json, math, pathlib, re, sys

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


# ── ④ 출구 7개 실측 비중 (사전층 ①) ──────────────────────────────────
def exit_bars():
    """E_st — 작년에 실제로 그 출구로 나간 인원의 비중. 2년 평균, 초과 승차 기준(exit_shares.py)."""
    d = _load("exit_shares")
    rows = [{"name": k, "share": v, "E": d["E_mean"][k]}
            for k, v in sorted(d["share_mean"].items(), key=lambda kv: -kv[1])]
    return {"exits": rows, "total": d["total_mean"], "festival_days": d["festival_days"],
            "source": "data/derived/exit_shares.json share_mean·E_mean (2년 평균 초과 승차)"}


# ── ⑤ 피더 12곳 방사형 (사전층 ②) ────────────────────────────────────
def _bearing(lat1, lng1, lat2, lng2):
    """(lat1,lng1) 에서 본 (lat2,lng2) 의 방위각 — 북 0°, 시계 방향."""
    dl = math.radians(lng2 - lng1)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _coord(stations, name):
    """역 좌표. all_coords 가 '낙성대'·'잠실' 처럼 짧은 이름을 갖고, stations 는 '낙성대(강감찬)' 식이라 all_coords 먼저."""
    ac = stations["all_coords"].get(name)
    if ac:
        return ac[0]["lat"], ac[0]["lng"]
    st = stations["stations"].get(name)
    if st:
        return st["lat"], st["lng"]
    raise KeyError(f"stations.json 에 {name} 좌표가 없다")


def feeder_map():
    """보고서 그림 1 과 같은 도식 — 방위는 실제, 중심 거리는 지하철 소요시간(추정), 원 크기는 2년 귀속 인원."""
    d = _load("feeder_leadlag")
    st = _load("stations")
    clat, clng = _coord(st, "여의도")
    rows = []
    for name, v in d["top_feeders"].items():
        lat, lng = _coord(st, name)
        rows.append({"name": name, "lines": v["lines"], "gu": v["gu"],
                     "persons": v["attributed_2yr"], "share": v["share_of_attributed"],
                     "travel_min": v["travel_min_est"], "bearing_deg": round(_bearing(clat, clng, lat, lng), 1),
                     "r_lag0": v["pearson_lag0_pooled"], "r_lag1": v["pearson_lag1_pooled"], "phase": v["phase"]})
    rows.sort(key=lambda r: -r["persons"])
    return {"center": {"name": "여의도", "lat": clat, "lng": clng}, "rings_min": [10, 20, 30],
            "feeders": rows, "travel_min_basis": d.get("travel_min_basis", ""),
            "source": "data/derived/feeder_leadlag.json top_feeders · stations.json 좌표"}


# ── ⑥ 결함 대장 건수 (검증) ──────────────────────────────────────────
GRADE_KO = {"C": "치명", "H": "높음", "M": "중간", "L": "낮음"}


def redteam_counts():
    """redteam-20260901.md 에 등재된 결함 ID 를 센다 — 표 첫 칸 또는 `### ID.` 제목. `### 철회 — ID` 는 따로."""
    txt = (ROOT / "redteam-20260901.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| *\**([CHML]\d+)\b", txt, re.M)) | set(re.findall(r"^### ([CHML]\d+)\.", txt, re.M))
    retracted = set(re.findall(r"^### 철회 — ([CHML]\d+)", txt, re.M))
    listed -= retracted
    by = {g: sorted((i for i in listed if i[0] == g), key=lambda s: int(s[1:])) for g in "CHML"}
    return {"by_grade": {GRADE_KO[g]: len(by[g]) for g in "CHML"},
            "ids": {GRADE_KO[g]: by[g] for g in "CHML"},
            "total": len(listed), "retracted": sorted(retracted),
            "source": "redteam-20260901.md",
            "rule": "표 첫 칸 `| ID` 또는 `### ID.` 제목의 고유 ID. `### 철회 — ID` 는 철회로 분리"}


# ── ⑦ 코드 스트립 — 소스에서 앵커를 찾아 N줄 ─────────────────────────
STRIPS = [
    ("demand", "src/backtrack.py", "def exit_forecast(", 6, "사전층 — 유출 곡선을 쇼 종료만큼 밀고 출구에 배분한다"),
    ("alpha", "src/nowcast.py", "def assimilate(", 8, "당일층 — 격자 사후분포 w(α) ∝ 사전 × Π N(y; A·α+B, σ)"),
    ("blend", "docs/app/field.js", "function blendSeconds(", 3, "화면층 — 간선을 걷는 시간 = 거리 ÷ 속도(확신도 혼합 밀도)"),
]


def code_strips():
    """손으로 베끼지 않는다. 앵커(함수 시그니처)를 찾아 그 줄부터 N줄. 줄 번호는 지금 계산한다."""
    out = []
    for sid, rel, anchor, n, cap in STRIPS:
        lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
        idx = next(i for i, l in enumerate(lines) if anchor in l)
        out.append({"id": sid, "file": rel, "start": idx + 1, "lines": lines[idx: idx + n], "caption": cap})
    return out


# ── ⑧ 9/5 실전 결과 자리 ─────────────────────────────────────────────
def live_result():
    """채워진 파일은 덮어쓰지 않는다. 비어 있으면 자리만.

    채울 때 형태(9/6, evaluate.py 결과로): {"filled": true, "date": "2026-09-05",
    "grade_hit": "88% (15/17)", "alpha_final": "1.08 [0.95~1.21]", "ticks": 144, "restarts": 0, "note": "…"}
    """
    p = OUT / "live_result.json"
    if p.exists():
        cur = json.loads(p.read_text(encoding="utf-8"))
        if cur.get("filled"):
            return cur
    return {"filled": False, "date": "2026-09-05",
            "note": "9/6 evaluate.py 결과로 채운다. 12~24시 자동 수집 · 5분 발행 · 쇼 종료 실시각 현장 기입"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("feeder_lag", feeder), ("backtest_bars", backtest), ("alpha_grid", alpha),
                     ("exit_bars", exit_bars), ("feeder_map", feeder_map), ("redteam_counts", redteam_counts),
                     ("code_strips", code_strips), ("live_result", live_result)):
        p = OUT / f"{name}.json"
        p.write_text(json.dumps(fn(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.1f}KB")


if __name__ == "__main__":
    main()
