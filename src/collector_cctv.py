#!/usr/bin/env python3
"""TOPIS 공개 CCTV(HLS) → 군중 밀도·점유율·흐름 집계 수집기. 프레임은 저장하지 않는다.

  .venv/bin/python src/collector_cctv.py --once [--cams 192,725,310]   # 1회 (테스트)
  INTERVAL=60 .venv/bin/python src/collector_cctv.py                    # 60초 루프

출력: data/live/cctv_YYYYMMDD.jsonl — 1행 = 1카메라 1시각
  ts, cam_id, name, count(밀도맵 합), occupancy(전경 비율 0~1), flow(프레임간 평균 이동량), level, ok
등급: count 를 ROI 면적(m², cams.json 의 roi_m2, 없으면 null)으로 나눈 밀도 → 서울시 기준 3/4/5명/m² = 주의/경계/심각.
신뢰도(confidence ok/low, flags): 저조도(brightness<40) · 배경차분 실패(occupancy≥0.9) · 밀도 포화(≥5명/m², 개체 검출 붕괴 구간) ·
count<20 인데 점유율 높음(불일치). bg_fail 이면 등급을 "보정전"으로 내린다. 하류(nowcast)는 count<20 등급을 구역 밀도에 쓰지 않는다. (benchmark §4-6)
     roi_m2 가 없으면 등급은 점유율 기준 임시값(0.15/0.30/0.45)으로 매긴다. 캘리브레이션 전까지는 '추세' 용도다.
ROI 마스크: cams.json 의 roi = [[x,y],...] (픽셀 폴리곤, 보행 영역만). 있으면 폴리곤 밖을 검게 지운 뒤 count·점유율·흐름을 계산한다.
  도로 카메라는 차량·노면 질감이 count 에 섞이므로(낮에 여의교남단 87.7 등) ROI 없는 카메라의 등급은 화면 참고용이고 nowcast 구역 밀도엔 쓰지 않는다.
  ROI 좌표 잡기: src/cam_calib.py (격자 프레임 1장을 저장소 밖에 저장).
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


def apply_roi(frame, roi):
    """ROI 폴리곤(픽셀) 밖을 0 으로. roi 없으면 원본."""
    if not roi: return frame
    m = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.fillPoly(m, [np.array(roi, dtype=np.int32)], 255)
    return cv2.bitwise_and(frame, frame, mask=m)


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


LOW_LIGHT, MIN_COUNT, SATURATION = 40.0, 20, 5.0


def confidence(cnt, occ, dens, frame):
    """계측 신뢰도 플래그. 프레임 평균 밝기(0~255)도 기록."""
    flags = []
    b = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
    if b < LOW_LIGHT: flags.append("low_light")
    if occ is not None and occ >= 0.9: flags.append("bg_fail")
    if dens is not None and dens >= SATURATION: flags.append("saturated")
    if cnt < MIN_COUNT and (occ or 0) >= 0.30: flags.append("count_vs_occ")
    return ("low" if flags else "ok"), flags, round(b, 1)


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
                # HD 원본(UTIC 1280x720, 2026-08-31 확인) 우선, 실패 시 TOPIS 480p 폴백. IP 직결 원본이라 수시 중단 가능 → 폴백 필수
                origin = "hd" if c.get("hls_hd") else "sd"
                f0, f1 = grab(c.get("hls_hd") or c["hls"])
                if f0 is None and c.get("hls_hd"):
                    origin = "sd"; f0, f1 = grab(c["hls"])
                if f0 is None: raise RuntimeError("no frame")
                roi = c.get("roi")
                if roi and f0 is not None:                        # ROI 좌표는 roi_frame 기준 → 실제 프레임 크기로 스케일 (HD 720p 대응)
                    bw, bh = c.get("roi_frame", [720, 480])
                    if (f0.shape[1], f0.shape[0]) != (bw, bh):
                        sx, sy = f0.shape[1] / bw, f0.shape[0] / bh
                        roi = [[round(x * sx), round(y * sy)] for x, y in roi]
                f0m, f1m = apply_roi(f0, roi), apply_roi(f1, roi) if f1 is not None else None
                cnt = count_people(f0m); occ = occupancy(c["camId"], f0m); fl = flow(f0m, f1m)
                if roi and occ is not None:                       # 점유율은 ROI 면적 기준으로 재정규화
                    m = np.zeros(f0.shape[:2], dtype=np.uint8); cv2.fillPoly(m, [np.array(roi, dtype=np.int32)], 1); occ = min(1.0, occ / max(1e-6, float(m.mean())))
                lv, dens = level(cnt, occ, c.get("roi_m2"))
                conf, flags, bright = confidence(cnt, occ, dens, f0)
                if "bg_fail" in flags or "count_vs_occ" in flags: lv = "보정전"   # 계측 자체가 깨진 경우만 등급을 내린다(저조도는 플래그만)
                rec.update(ok=True, count=round(cnt, 1), occupancy=None if occ is None else round(occ, 4), flow=None if fl is None else round(fl, 3), density=dens, level=lv,
                           confidence=conf, flags=flags, brightness=bright, calibrated=bool(roi and c.get("roi_m2")), origin=origin)
            except Exception as e:
                rec["error"] = str(e)[:120]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(now.strftime("%H:%M:%S"), f"{c['name']:<10}", rec.get("level", "ERR"), "count", rec.get("count"), "occ", rec.get("occupancy"), "flow", rec.get("flow"), rec.get("confidence", ""), ",".join(rec.get("flags", [])), rec.get("error", ""))


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
