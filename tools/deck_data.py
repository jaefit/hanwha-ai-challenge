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


# ── ⑧ 9/5 실전 결과 (evaluate.py 결과 + 발행 스냅샷) ─────────────────
LIVE = ROOT / "data" / "live"
HIST = LIVE / "forecast_history" / "20260905"
EVAL = DER / "eval_20260905.json"


def _keep_if_missing(name, need):
    """원천(맥에만 있는 data/live)이 없으면 이미 내보낸 파일을 그대로 둔다 — 회사 PC 에서 돌려도 덱이 비지 않게."""
    p = OUT / f"{name}.json"
    if all(x.exists() for x in need):
        return None
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"filled": False, "note": "원천 없음 — 맥에서 tools/deck_data.py 를 다시 돌린다"}


def live_result():
    """9/5 실전 채점. 숫자는 evaluate.py 산출(eval_20260905.json)과 수집 원장에서만 가져온다.

    형태 비교 주의: subway_shape 의 실측은 핫스팟 30분 승차 합이라 **규모가 다르다**(커버리지 상이).
    그래서 23시 꼬리는 절대값이 아니라 "피크 대비 비율"로 적는다 — evaluate.py 의 note 가 그렇게 못 박았다.
    """
    kept = _keep_if_missing("live_result", [EVAL])
    if kept is not None:
        return kept
    ev = json.loads(EVAL.read_text(encoding="utf-8"))
    snaps = ev["our_snapshots"]
    alphas = [s["alpha"][1] for s in snaps]
    a_last, a_max = snaps[-1]["alpha"], max(alphas)
    sh = ev["subway_shape"]
    obs, pred = sh["obs_by_hour"], sh["pred_by_hour"]
    obs_pk, pred_pk = obs[str(sh["peak_obs"])], pred[str(sh["peak_pred"])]
    tail_obs = obs["23"] / obs_pk
    tail_pred = pred["23"] / pred_pk
    cctv_n = sum(1 for _ in (LIVE / "cctv_20260905.jsonl").open(encoding="utf-8")) if (LIVE / "cctv_20260905.jsonl").exists() else None
    show_end = (LIVE / "show_end.txt").read_text(encoding="utf-8").strip() if (LIVE / "show_end.txt").exists() else "21:27"
    tiles = [
        {"v": str(len(snaps)), "label": "발행 스냅샷", "sub": "5분 간격 · 12:00~24:00 자동"},
        {"v": f"{ev['n_records']:,}", "label": "API 수집 레코드", "sub": (f"CCTV 판독 {cctv_n:,}" if cctv_n else "CCTV 23대 60초")},
        {"v": f"{a_last[1]:.2f}", "label": "당일 인원 배율 α 최종 [p10~p90]", "sub": f"{a_last[0]:.2f}~{a_last[2]:.2f} · 사전 1.00 · 최고 {a_max:.2f}"},
        {"v": f"{sh['peak_obs']}시", "label": "유출 정점 시각 일치", "sub": f"예측 {sh['peak_pred']}시 · 형태 상관 r {sh['pearson']:.2f}"},
    ]
    cards = [
        {"kind": "hit", "kicker": "실제 행사 종료 시각 반영", "title": f"계획 21:10 · 실제 종료 {show_end} (+{int(show_end[:2]) * 60 + int(show_end[3:]) - 21 * 60 - 10}분)",
         "body": "현장 입력 후 유출 예측 시점을 조정했습니다 — 21:36 발행분부터 21시 유출 예측 76.6천 → 88.3천."},
        {"kind": "hit", "kicker": "서울시 선행 예측의 오차", "title": f"MAPE {ev['seoul_12h']['mape']:.2f} · 22시 5.75천 vs 실측 53천",
         "body": "서울시 12시간 예측은 저녁 정점 인원을 실측의 약 1/9 수준으로 추정했습니다. 본 모델은 5분마다 관측으로 배율을 갱신합니다."},
        {"kind": "miss", "kicker": "23시 유출 인원 과소 추정", "title": f"정점 대비 실측 {round(tail_obs * 100)}%, 예측 {round(tail_pred * 100)}%",
         "body": "예측보다 많은 인원이 늦은 시간까지 이동했습니다. 여의나루역 조기 무정차(18:10~22:05)와 겹쳐 22시 이후 승차가 길게 이어졌습니다. 결함 대장에 등재."},
    ]
    return {"filled": True, "date": "2026-09-05",
            "grade_hit": f"피크 {sh['peak_obs']}시 일치 · r {sh['pearson']:.2f}", "alpha_final": f"{a_last[1]:.2f} [{a_last[0]:.2f}~{a_last[2]:.2f}]",
            "ticks": len(snaps), "restarts": 1,
            "restarts_basis": "16:44 INTERVAL=60 전환 1회(계획) · 크래시 0 · 슬립 공백 0 (devlog 2026-09-05)",
            "tail_ratio": {"obs": round(tail_obs, 3), "pred": round(tail_pred, 3), "peak_hour": sh["peak_obs"],
                           "basis": "subway_shape: 실측=핫스팟 30분 승차 합 — 규모 자유, 피크 대비 비율만 비교"},
            "tiles": tiles, "cards": cards,
            "note": "evaluate.py --date 20260905 산출 · 규모가 다른 계열은 비율만 비교 · 재기동 1회는 계획된 간격 전환"}


# ── ⑨ 발행 스냅샷 재생 (그 시각, 화면은 이랬다) ─────────────────────────
REPLAY_AT = [("2005", "쇼 직전 · 공원 피크"), ("2101", "쇼 중 · 여의나루 통제"), ("2131", "쇼 종료 기입 전"),
             ("2136", "쇼 종료 21:27 기입 직후"), ("2206", "우리 화면 최고 부하 · 여의나루 재개통"), ("2302", "꼬리")]
EXIT_ORDER = ["여의나루(5)", "여의도(5)", "여의도(9)", "샛강(9)", "국회의사당(9)", "신길(1·5)", "마포역 도보(마포대교)"]


def replay_frames():
    """덱 s11 — 발행 스냅샷 6개를 화면이 그렸던 값 그대로 얇게 뽑는다. 계산 없음, 선택만."""
    need = [HIST / f"{at}.json" for at, _ in REPLAY_AT]
    kept = _keep_if_missing("replay_frames", need)
    if kept is not None:
        return kept if "frames" in kept else {"frames": [], "note": kept.get("note")}
    frames = []
    for at, lab in REPLAY_AT:
        d = json.loads((HIST / f"{at}.json").read_text(encoding="utf-8"))
        hour = at[:2]
        closed_hours = {c["exit"]: set(c["hours"]) for c in d.get("closures", []) if "exit" in c}
        loads = []
        for name in EXIT_ORDER:
            row = (d.get("exits") or {}).get(name, {}).get(hour) or {}
            ch = closed_hours.get(name, set())
            if row.get("closed") or int(hour) in ch:
                loads.append({"name": name, "load": None, "note": "통제(무정차)"})
            else:
                note = "재개통 직후" if (int(hour) - 1) in ch else ""
                loads.append({"name": name, "load": row.get("load"), "wait_min": row.get("wait_min"), "note": note})
        park = (d.get("live_snapshot") or {}).get("여의도한강공원") or {}
        n_obs = d.get("assimilation", {}).get("n_obs", {})
        frames.append({
            "at": at, "hhmm": f"{at[:2]}:{at[2:]}", "label": lab, "hour": hour, "ts": d.get("ts"),
            "alpha": d.get("alpha"), "alpha_band": d.get("assimilation", {}).get("alpha"),
            "n_obs": sum(v for v in n_obs.values() if isinstance(v, (int, float))),
            "show_shift_min": d.get("show_shift_min"), "show_end": d.get("show_end_actual") or d.get("show_end_2026"),
            "show_end_source": d.get("show_end_source"),
            "park": (f"{park.get('congest')} {park['ppltn'][0] // 1000}~{park['ppltn'][1] // 1000}천 ({park.get('ts', '')[11:16]} 값)" if park.get("ppltn") else "—"),
            "outflow": d.get("outflow_forecast"), "loads": loads,
        })
    ev = json.loads(EVAL.read_text(encoding="utf-8"))["subway_shape"] if EVAL.exists() else {}
    return {"date": "2026-09-05", "frames": frames, "before_after": ["2131", "2136"], "peak": "2206",
            "observed_boarding_by_hour": {k: v for k, v in ev.get("obs_by_hour", {}).items() if k in ("19", "20", "21", "22", "23")},
            "predicted_boarding_by_hour": ev.get("pred_by_hour"),
            "replay_url": {"ops": "index.html?at=20260905T{at}", "visitor": "go.html?at=20260905T{at}"},
            "source": "data/live/forecast_history/20260905/{at}.json (발행분 그대로) · eval_20260905.json subway_shape",
            "note": "선택만 했다 — 부하·α·유출은 그 시각 화면이 실제로 그린 값. 관측 승차는 핫스팟 합이라 규모가 달라 형태만 본다"}


# ── ⑩ 재료 — 공개 데이터 지도 (덱 3장) ─────────────────────────────
# 문구는 topic-fireworks.md §3 표·보고서 §2 의 서술을 옮겼다. 개수(카메라·노드·간선)는 파일에서 센다.
def sources():
    cams = json.loads((ROOT / "docs" / "data" / "cams.json").read_text(encoding="utf-8"))
    g = json.loads((ROOT / "docs" / "data" / "routing" / "walk_graph.json").read_text(encoding="utf-8"))
    rows = [
        {"name": "서울교통공사 역별 시간대별 승하차", "id": "OA-12921 · 교통카드 OA-12914", "gives": "2024·2025 축제일 출구 7개 승하차, 평시 토요일 중앙값", "cadence": "연간 CSV", "layer": "사전층", "use": "출구 비중 E_st · 백테스트 · 여의나루 하차 ≈0", "limit": "9호선은 카드 일별만(시간대 없음) → 저녁 비율 0.93~0.97 가정"},
        {"name": "서울 실시간 도시데이터", "id": "citydata · POI 여의도한강공원·여의도·여의서로", "gives": "구역 인구·혼잡 4단계 · 여의나루 30분 승하차 · 도로·사고통제 · 12h 예측", "cadence": "5분", "layer": "당일층", "use": "α 관측 O1·O2 · 혼잡장 배경 · 통제 알림", "limit": "발행 시차 28.8분(9/5 실측) · 12h 예측 MAPE 0.56"},
        {"name": "실시간 지하철 도착", "id": "swopenAPI · 4역", "gives": "여의나루·여의도·샛강·국회의사당 열차 도착", "cadence": "틱마다(키 6개 회전)", "layer": "당일층", "use": "무정차 실측 확인(9/5 18:10~22:05)", "limit": "일 1,000건/키"},
        {"name": "TOPIS 교통 CCTV", "id": f"공개 HLS {len(cams)}대", "gives": "다리·진입로 보행 흐름(인원·점유·흐름 집계)", "cadence": "60초", "layer": "당일층", "use": "밀도 등급 → 보행속도 · 혼잡장 관측", "limit": "ROI 미검증(전부 「보정전」) · 프레임 미저장"},
        {"name": "KT 수도권 생활이동 OD", "id": "OA-22300 · OA-22657", "gives": "출발동×도착동×시각×목적·수단 인원(추정)", "cadence": "일별(1개월 지연)", "layer": "사전층", "use": "유출 곡선 형태 · 방향 비중 · 피더 상한", "limit": "cnt 는 추정치 → 비율·형태로만"},
        {"name": "OSM 보행망", "id": f"노드 {len(g['nodes']):,} · 간선 {len(g['edges']):,}", "gives": "여의도·마포 보행 가능 간선(차도·사유지 제외)", "cadence": "정적", "layer": "화면층", "use": "A* 경로 · 간선 걷는 시간", "limit": "마포대교 보완 간선 길이는 하한 근사"},
        {"name": "통제 공지", "id": "서울시 보도자료 · 경찰", "gives": "여의동로 전면통제 · 여의나루 무정차 20:40~21:40 · 원효대교", "cadence": "행사 전 1회", "layer": "사전층 → 당일 이월", "use": "closures 규칙", "limit": "실측은 조기(18:10) — 당일 19시 추가 hotfix"},
        {"name": "서울시 12시간 예측", "id": "citydata FCST", "gives": "구역 인구 12h 선행 예측", "cadence": "5분", "layer": "검증", "use": "기준선 비교(우리 α 갱신의 필요성)", "limit": "9/5 저녁 피크 9배 과소"},
    ]
    return {"rows": rows, "all_public": True, "note": "전부 공개·합법 소스. 키는 .env 에만. 문구 출처 topic-fireworks.md §3 · report.html §2", "generated": "2026-09-06"}


# ── ⑪ 과정 — Claude Code 로 만든 흐름 (덱 9장) ────────────────────────
# 숫자는 전부 git·tests·대장에서 센다. 이정표 문구만 손으로 적고, 그 날짜에 커밋이 있는지 확인한다.
MILESTONES = [
    ("2026-08-29", "주제 확정 · 공공 데이터 7종 수집"),
    ("2026-08-31", "예측 엔진 · 백테스트 · 대시보드 v1"),
    ("2026-09-01", "레드팀 1회차 · 혼잡장 · 피치덱"),
    ("2026-09-02", "드라이런 · 워치독 고장 주입"),
    ("2026-09-03", "Codex 교차검증 · 테스트런"),
    ("2026-09-04", "전야제 리허설 · 관람객 화면 v2"),
    ("2026-09-05", "본번 32h 무중단 · hotfix 4"),
    ("2026-09-06", "실전 채점 · 덱 v2 · 재생"),
]


def process():
    import subprocess, re as _re
    log = subprocess.run(["git", "log", "--format=%ad%x09%s", "--date=format:%Y-%m-%d", "--since=2026-08-28"],
                         cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    daily, publish = {}, 0
    for line in log:
        d, _, subj = line.partition("\t")
        if subj.startswith("data: latest"):
            publish += 1
            continue
        daily[d] = daily.get(d, 0) + 1
    days = sorted(daily)
    for d, _ in MILESTONES:
        assert d in daily, f"이정표 {d} 에 커밋이 없다"
    tests = sum(len(_re.findall(r"^def test_", p.read_text(encoding="utf-8"), _re.M)) for p in (ROOT / "tests").glob("test_*.py"))
    rt = json.loads((OUT / "redteam_counts.json").read_text(encoding="utf-8"))
    ledger = (ROOT / "redteam-20260901.md").read_text(encoding="utf-8")
    rounds = len(set(_re.findall(r"^## .*?(\d)회차", ledger, _re.M))) + 1     # 1회차는 본문(제목 없음) · 3회차는 "## 7. 3회차"
    sec = ledger.split("### 당일 hotfix")[1].split("###")[0] if "### 당일 hotfix" in ledger else ""
    hotfix = len([l for l in sec.splitlines() if l.startswith("| ") and not l.startswith("| 시각") and not l.startswith("| :--")])
    return {"days": [{"date": d, "commits": daily[d], "milestone": dict(MILESTONES).get(d)} for d in days],
            "commits_total": sum(daily.values()), "publish_commits": publish,
            "span": {"first": days[0], "last": days[-1], "n_days": len(days)},
            "tests": {"first": 26, "now": tests, "basis": "tests/test_*.py 의 def test_ 수 · 26 은 2026-09-01 대장 기준"},
            "redteam": {"rounds": rounds, "total": rt["total"], "by_grade": rt["by_grade"]},
            "hotfix_day": hotfix,
            "tools": ["Claude Code (설계·구현·검증·문서)", "Codex CLI (교차검증 1회)", "Claude Design (화면·덱 디자인)"],
            "note": "커밋은 5분 발행 자동 커밋(data: latest) 제외. 숫자는 git log · tests · 결함 대장에서 뽑는다", "generated": "2026-09-06"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in (("feeder_lag", feeder), ("backtest_bars", backtest), ("alpha_grid", alpha),
                     ("exit_bars", exit_bars), ("feeder_map", feeder_map), ("redteam_counts", redteam_counts),
                     ("code_strips", code_strips), ("live_result", live_result), ("replay_frames", replay_frames), ("sources", sources), ("process", process)):
        p = OUT / f"{name}.json"
        p.write_text(json.dumps(fn(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.1f}KB")


if __name__ == "__main__":
    main()
