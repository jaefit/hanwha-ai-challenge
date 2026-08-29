#!/usr/bin/env python3
"""TOPIS 공개 CCTV(HLS) → 군중 밀도·점유율·흐름 집계 수집기. 프레임은 저장하지 않는다.

  .venv/bin/python src/collector_cctv.py --once [--cams 192,725,310]   # 1회 (테스트)
  INTERVAL=60 .venv/bin/python src/collector_cctv.py                    # 60초 루프

출력: data/live/cctv_YYYYMMDD.jsonl — 1행 = 1카메라 1시각
  ts, cam_id, name, count(밀도맵 합), occupancy(전경 비율 0~1), flow(프레임간 평균 이동량), level, ok
등급: count 를 ROI 면적(m², cams.json 의 roi_m2, 없으면 null)으로 나눈 밀도 → 서울시 기준 3/4/5명/m² = 주의/경계/심각.
     roi_m2 가 없으면 등급은 점유율 기준 임시값(0.15/0.30/0.45)으로 매긴다. 캘리브레이션 전까지는 '추세' 용도다.
모델: lwcc DM-Count(SHA). 720x480 원거리 고각이라 절대값 오차 ±30% 가정. 출처·한계는 topic-fireworks.md §6.
"""
import os, sys, json, time, datetime, pathlib
import cv2, numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAMS = json.loads((ROOT / "data" / "derived" / "topis_yeouido_cams.json").read_text(encoding="utf-8"))
OUT = ROOT / "data" / "live"; OUT.mkdir(parents=True, exist_ok=True)
INTERVAL = int(os.environ.get("INTERVAL", "60"))
os.environ.setdefault("HOME", str(pathlib.Path.home()))

_model = None
def model():
    global _model
    if _model is None:
        from lwcc import LWCC
        _model = LWCC.load_model(model_name="DM-Count", model_weights="SHA")
    return _model


def grab(url, n=8):
    """HLS 에서 프레임 2장(≈0.5초 간격) — 흐름 계산용. 실패 시 (None, None)."""
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened(): return None, None
    frames = []
    for _ in range(n):
        ok, f = cap.read()
        if ok: frames.append(f)
    cap.release()
    if len(frames) < 2: return (frames[0], None) if frames else (None, None)
    return frames[0], frames[-1]


def count_people(frame):
    from lwcc import LWCC
    import tempfile
    # lwcc 는 파일 경로만 받는다 → 임시파일로 넘기고 즉시 삭제 (프레임 미저장 원칙)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
        cv2.imwrite(tmp.name, frame)
        c = LWCC.get_count(tmp.name, model=model())
    return float(c)


_bg, _seen = {}, {}
WARMUP = 3   # 배경 모델이 자리 잡기 전(첫 3틱)엔 점유율을 내지 않는다 — 첫 프레임은 전부 전경으로 잡힌다
def occupancy(cam_id, frame):
    """MOG2 배경차분 전경 비율. 카메라별 배경 모델 유지. 워밍업 전엔 None."""
    sub = _bg.setdefault(cam_id, cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=32, detectShadows=False))
    m = sub.apply(frame)
    _seen[cam_id] = _seen.get(cam_id, 0) + 1
    if _seen[cam_id] <= WARMUP: return None
    return float((m > 0).mean())


def flow(f0, f1):
    if f0 is None or f1 is None: return None
    g0, g1 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY), cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
    fl = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    return float(np.linalg.norm(fl, axis=2).mean())


def level(count, occ, roi_m2):
    if roi_m2:
        d = count / roi_m2
        return ("심각" if d >= 5 else "경계" if d >= 4 else "주의" if d >= 3 else "여유"), round(d, 2)
    if occ is None: return "보정전", None
    return ("심각" if occ >= 0.45 else "경계" if occ >= 0.30 else "주의" if occ >= 0.15 else "여유"), None


def tick(cams):
    now = datetime.datetime.now()
    fn = OUT / f"cctv_{now:%Y%m%d}.jsonl"
    with fn.open("a", encoding="utf-8") as f:
        for c in cams:
            rec = {"ts": now.isoformat(timespec="seconds"), "cam_id": c["camId"], "name": c["name"], "ok": False}
            try:
                f0, f1 = grab(c["hls"])
                if f0 is None: raise RuntimeError("no frame")
                cnt = count_people(f0); occ = occupancy(c["camId"], f0); fl = flow(f0, f1)
                lv, dens = level(cnt, occ, c.get("roi_m2"))
                rec.update(ok=True, count=round(cnt, 1), occupancy=None if occ is None else round(occ, 4), flow=None if fl is None else round(fl, 3), density=dens, level=lv)
            except Exception as e:
                rec["error"] = str(e)[:120]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(now.strftime("%H:%M:%S"), f"{c['name']:<10}", rec.get("level", "ERR"), "count", rec.get("count"), "occ", rec.get("occupancy"), "flow", rec.get("flow"), rec.get("error", ""))


if __name__ == "__main__":
    sel = None
    if "--cams" in sys.argv: sel = set(sys.argv[sys.argv.index("--cams") + 1].split(","))
    cams = [c for c in CAMS if c.get("hls") and (sel is None or c["camId"] in sel)]
    if "--once" in sys.argv:
        tick(cams); sys.exit(0)
    while True:
        t0 = time.time()
        try: tick(cams)
        except Exception as e: print("tick error", e)
        time.sleep(max(1, INTERVAL - (time.time() - t0)))
