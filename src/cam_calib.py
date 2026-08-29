#!/usr/bin/env python3
"""CCTV ROI 캘리브레이션 보조: 카메라 1대당 프레임 1장에 픽셀 격자를 그려 저장소 **밖** 폴더에 저장한다.
사용자가 그 그림을 보고 보행 영역 폴리곤 좌표(roi)와 그 영역의 실제 면적(roi_m2, 지도에서 측정)을
data/derived/topis_yeouido_cams.json 에 적는다. 캘리브레이션 전엔 CCTV 등급이 nowcast 구역 밀도에 쓰이지 않는다.

  .venv/bin/python src/cam_calib.py --cams 192,725,310,331,39 --out ~/cam_calib

주의: 이 스크립트는 프레임을 파일로 남긴다(캘리브레이션 1회용). 저장소 안에 두지 말고 끝나면 지운다.
"""
import sys, json, pathlib, datetime
import cv2, numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from collector_cctv import grab, CAMS


def main():
    sel = set(sys.argv[sys.argv.index("--cams") + 1].split(",")) if "--cams" in sys.argv else None
    out = pathlib.Path(sys.argv[sys.argv.index("--out") + 1]).expanduser() if "--out" in sys.argv else pathlib.Path.home() / "cam_calib"
    if ROOT in out.resolve().parents or out.resolve() == ROOT: sys.exit("출력 폴더는 저장소 밖이어야 한다")
    out.mkdir(parents=True, exist_ok=True)
    for c in CAMS:
        if sel and c["camId"] not in sel: continue
        f0, _ = grab(c["hls"], n=2)
        if f0 is None: print("no frame", c["camId"], c["name"]); continue
        h, w = f0.shape[:2]; img = f0.copy()
        for x in range(0, w, 40): cv2.line(img, (x, 0), (x, h), (0, 255, 255) if x % 200 == 0 else (80, 80, 80), 1)
        for y in range(0, h, 40): cv2.line(img, (0, y), (w, y), (0, 255, 255) if y % 200 == 0 else (80, 80, 80), 1)
        for x in range(0, w, 200): cv2.putText(img, str(x), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        for y in range(0, h, 200): cv2.putText(img, str(y), (2, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cv2.putText(img, f"{c['camId']} {c['name']} {w}x{h} {datetime.datetime.now():%m-%d %H:%M}", (2, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        fn = out / f"cam_{c['camId']}_{c['name']}.png"; cv2.imwrite(str(fn), img); print("saved", fn, f"{w}x{h}")
    print("\n다음: 각 그림에서 보행 영역 꼭짓점 (x,y) 를 읽어 topis_yeouido_cams.json 항목에 추가:")
    print('  "roi": [[x1,y1],[x2,y2],...], "roi_m2": <그 영역 실제 면적 m², 지도에서 측정>')


if __name__ == "__main__":
    main()
