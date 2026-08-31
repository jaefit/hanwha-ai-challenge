#!/usr/bin/env python3
"""forecast_latest.json + 최신 CCTV 집계 → docs/data/latest.json 으로 복사하고 커밋·푸시 (GitHub Pages 갱신).

  .venv/bin/python src/publish.py          # 1회
  변경 없으면 커밋하지 않는다. 5분 루프는 run_all.sh 에서 돈다.
"""
import json, sys, pathlib, subprocess, datetime, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE, DOCS = ROOT / "data" / "live", ROOT / "docs" / "data"
DOCS.mkdir(parents=True, exist_ok=True)


def latest_cctv(date):
    fn = LIVE / f"cctv_{date}.jsonl"
    if not fn.exists(): return {}
    last = collections.OrderedDict()
    for l in fn.read_text(encoding="utf-8").splitlines():
        if l.strip():
            r = json.loads(l); last[r["cam_id"]] = r
    return {k: {kk: v.get(kk) for kk in ("ts", "name", "level", "count", "occupancy", "flow", "ok")} for k, v in last.items()}


def main():
    date = datetime.datetime.now().strftime("%Y%m%d")
    fc = json.loads((LIVE / "forecast_latest.json").read_text(encoding="utf-8")) if (LIVE / "forecast_latest.json").exists() else {}
    payload = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "forecast": fc, "cctv": latest_cctv(date)}
    out = DOCS / "latest.json"
    new = json.dumps(payload, ensure_ascii=False, indent=1)
    if out.exists() and out.read_text(encoding="utf-8") == new:
        print("no change"); return
    out.write_text(new, encoding="utf-8")
    # 예측 스냅샷 이력 (T6 evaluate.py 입력) — "그 시점에 뭐라고 예측했었나"를 사후 재현. repo 밖(data/live), 당일 종료 후 커밋
    hdir = LIVE / "forecast_history" / date; hdir.mkdir(parents=True, exist_ok=True)
    (hdir / f"{datetime.datetime.now():%H%M}.json").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    hist = DOCS / f"history_{date}.jsonl"
    with hist.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": payload["generated"], "alpha": fc.get("alpha"), "outflow": fc.get("outflow_forecast"), "live": fc.get("live_snapshot"), "cctv": {k: v.get("level") for k, v in payload["cctv"].items()}}, ensure_ascii=False) + "\n")
    if "--dry" in sys.argv: print("dry — git 생략, history 저장됨"); return
    subprocess.run(["git", "add", "docs/data"], cwd=ROOT, check=True)
    r = subprocess.run(["git", "commit", "-q", "-m", f"data: latest {payload['generated']}"], cwd=ROOT)
    if r.returncode == 0:
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=ROOT)
        print("published", payload["generated"])


if __name__ == "__main__":
    main()
