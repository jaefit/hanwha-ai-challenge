"""발행 스냅샷 → 재생 파일 (Task 12, 2026-09-06). 읽기 전용 재조립, 계산 없음.

`data/live/forecast_history/20260905/<hhmm>.json` 은 nowcast 가 그 시각 발행한 forecast 그대로다. 화면은 `latest.json`
(= {generated, forecast, cctv}) 을 읽으므로 같은 모양으로 감싸고, CCTV 는 `cctv_20260905.jsonl` 에서 발행 시각 이전
마지막 레코드를 카메라별로 골라 `publish.slim_cctv` 로 얇게 만든다 — 당일 publish.py 가 한 것과 같은 규칙.

출력: docs/data/replay/20260905/<hhmm>.json + index.json (칩 목록). 시각 6개는 tools/deck_data.REPLAY_AT 이 기준
(덱 s11 과 같은 목록이어야 한다 — tests/test_replay.py 가 대조).

실행: .venv/bin/python tools/replay_build.py
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "tools"))
from publish import slim_cctv          # noqa: E402
from deck_data import REPLAY_AT        # noqa: E402

DATE = "20260905"
HIST = ROOT / "data" / "live" / "forecast_history" / DATE
CCTV = ROOT / "data" / "live" / f"cctv_{DATE}.jsonl"
OUT = ROOT / "docs" / "data" / "replay" / DATE


def cctv_records():
    if not CCTV.exists():
        return []
    rows = []
    for line in CCTV.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: r.get("ts", ""))
    return rows


def cctv_at(rows, ts):
    """발행 시각 이전 카메라별 마지막 레코드 — publish.latest_cctv 와 같은 선택, 시각만 고정."""
    last = {}
    for r in rows:
        if r.get("ts", "") > ts:
            break
        last[r["cam_id"]] = r
    return {k: slim_cctv(v) for k, v in last.items()}


def main():
    if not HIST.exists():
        sys.exit(f"{HIST} 없음 — 발행 스냅샷은 수집한 맥에만 있다")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = cctv_records()
    chips = []
    for at, label in REPLAY_AT:
        snap = json.loads((HIST / f"{at}.json").read_text(encoding="utf-8"))
        ts = snap["ts"]
        payload = {"generated": ts, "forecast": snap, "cctv": cctv_at(rows, ts),
                   "replay": {"at": f"{DATE}T{at}", "label": label, "source": f"data/live/forecast_history/{DATE}/{at}.json",
                              "note": "당일 발행분 재조립 — forecast 그대로, CCTV 는 발행 시각 이전 마지막 레코드"}}
        p = OUT / f"{at}.json"
        p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        chips.append({"at": at, "hhmm": f"{at[:2]}:{at[2:]}", "label": label, "generated": ts, "cctv_n": len(payload["cctv"])})
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.1f}KB  cctv {len(payload['cctv'])}")
    (OUT / "index.json").write_text(json.dumps({"date": DATE, "chips": chips,
        "note": "재생 시각 6개 — tools/deck_data.REPLAY_AT 과 같은 목록. 화면은 ?at=YYYYMMDDTHHMM 으로 연다"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{(OUT / 'index.json').relative_to(ROOT)}  chips {len(chips)}")


if __name__ == "__main__":
    main()
