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
    return {k: slim_cctv(v) for k, v in last.items()}


# 2026-09-01 red team: density·calibrated·confidence·flags 가 빠져 있어 브라우저가 오탐을 걸러낼 수 없었다.
# (8/29 발행분: 63빌딩 count 1.0명인데 occupancy 1.0(배경차분 실패) → level "심각". nowcast 는 걸렀지만 화면은 못 걸렀다)
# 혼잡장(docs/app/field.js)이 신뢰도를 σ 로 가중하려면 이 필드들이 있어야 한다.
CCTV_WEB_FIELDS = ("ts", "name", "level", "count", "occupancy", "flow", "ok",
                   "density", "calibrated", "confidence", "flags")


def slim_cctv(rec):
    return {k: rec.get(k) for k in CCTV_WEB_FIELDS}


# 2026-09-01 red team C2: 비교 대상에 generated(now) 가 들어 있어 "변경 없으면 커밋하지 않는다" 가 한 번도 성립하지 않았고
# (5분마다 커밋), push 반환코드를 안 봐서 한 번 거절되면 공개 대시보드가 조용히 멈췄다.
FAIL_STREAK = LIVE / "publish_fail_streak"


# 2026-09-02 M9: run_all.sh 의 nowcast/publish 루프는 서브셸이라 nowcast 가 매번 예외로 죽어도 프로세스는 살아 있다.
# CCTV 는 매분 바뀌므로 same_payload 를 통과해 발행이 계속되고, 화면은 신선해 보이는데 예측만 얼어붙는다.
FORECAST_STALE_MIN = 15   # 정상 틱 주기 5분의 3배


def forecast_stale_min(fc, now=None):
    """예측 산출 시각이 FORECAST_STALE_MIN 분 넘게 지났으면 그 분 수, 아니면 None (시각을 못 읽어도 None)."""
    try: age = ((now or datetime.datetime.now()) - datetime.datetime.fromisoformat((fc or {})["ts"])).total_seconds() / 60
    except Exception: return None
    return round(age) if age > FORECAST_STALE_MIN else None


def render(payload):
    return json.dumps(payload, ensure_ascii=False, indent=1)


def same_payload(old_text, new_payload):
    """발행 시각(generated) 만 다르면 같은 내용으로 본다."""
    try: old = json.loads(old_text)
    except Exception: return False
    drop = lambda d: {k: v for k, v in d.items() if k != "generated"}
    return drop(old) == drop(new_payload)


def _git(*args, **kw):
    return subprocess.run(["git", *args], cwd=ROOT, **kw)


def push():
    """실패하면 pull --rebase 후 1회 재시도. 연속 실패 횟수를 남겨 당일에 눈에 띄게 한다."""
    r = _git("push", "-q", "origin", "main")
    if r.returncode != 0:
        print("push 거절 — pull --rebase 후 재시도", file=sys.stderr)
        # 충돌한 rebase 를 그대로 두면 저장소가 rebase 진행 상태로 묶여 이후 모든 틱의 커밋이 실패한다.
        # 자동 병합은 하지 않는다(사람이 판단할 일) — 되돌려 놓고 경보만 올린다.
        if _git("pull", "--rebase", "--autostash", "-q", "origin", "main").returncode != 0:
            _git("rebase", "--abort")
            print("rebase 충돌 — 되돌렸다. 두 기기가 같은 파일을 고쳤다는 뜻이니 사람이 정리해야 한다.", file=sys.stderr)
        else:
            r = _git("push", "-q", "origin", "main")
    if r.returncode == 0:
        FAIL_STREAK.unlink(missing_ok=True); return True
    n = (int(FAIL_STREAK.read_text()) if FAIL_STREAK.exists() else 0) + 1
    FAIL_STREAK.write_text(str(n))
    print(f"!!! 발행 실패 {n}회 연속 — 공개 대시보드가 갱신되지 않는다. `git status` · `git log origin/main..HEAD` 확인 !!!",
          file=sys.stderr)
    return False


def main():
    date = datetime.datetime.now().strftime("%Y%m%d")
    fc = json.loads((LIVE / "forecast_latest.json").read_text(encoding="utf-8")) if (LIVE / "forecast_latest.json").exists() else {}
    payload = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "forecast": fc, "cctv": latest_cctv(date)}
    stale = forecast_stale_min(fc)
    if stale is not None:
        print(f"!!! 예측이 {stale}분째 그대로다 — nowcast 가 죽었을 수 있다(발행은 CCTV 때문에 계속된다). "
              f"logs/nowcast.log 의 Traceback 확인 !!!", file=sys.stderr)
    # 예측 스냅샷 이력 (T6 evaluate.py 입력) — "그 시점에 뭐라고 예측했었나"를 사후 재현. repo 밖(data/live), 당일 종료 후 커밋
    hdir = LIVE / "forecast_history" / date; hdir.mkdir(parents=True, exist_ok=True)
    (hdir / f"{datetime.datetime.now():%H%M}.json").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    if "--dry" in sys.argv: print("dry — history만 저장, docs/data·git 생략"); return
    out = DOCS / "latest.json"
    new = render(payload)
    if out.exists() and same_payload(out.read_text(encoding="utf-8"), payload):
        print("no change"); return
    out.write_text(new, encoding="utf-8")
    hist = DOCS / f"history_{date}.jsonl"
    with hist.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": payload["generated"], "alpha": fc.get("alpha"), "outflow": fc.get("outflow_forecast"), "live": fc.get("live_snapshot"), "cctv": {k: v.get("level") for k, v in payload["cctv"].items()}}, ensure_ascii=False) + "\n")
    _git("add", "docs/data", check=True)
    r = _git("commit", "-q", "-m", f"data: latest {payload['generated']}")
    if r.returncode == 0 and push():
        print("published", payload["generated"])


if __name__ == "__main__":
    main()
