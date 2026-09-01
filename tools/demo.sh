#!/bin/zsh
# 가상 관측으로 대시보드를 띄운다 — 발표 시연·혼잡장 눈으로 확인용.
#
# 작성 2026-09-01. 왜 필요한가: 혼잡장(docs/app/field.js)은 관측이 신선할 때만 색이 나온다.
# 평상시 공개 데이터는 오래돼서 "배경만 표시"로 뜨므로, 실제로 어떻게 보이는지 확인하려면
# 축제 저녁 수준의 값을 넣어 봐야 한다. 수집기를 돌리지 않고 그걸 한다.
#
#   ./tools/demo.sh              # http://127.0.0.1:8080
#   PORT=9000 ./tools/demo.sh
#
# 저장소를 건드리지 않는다 — docs/ 사본을 $TMPDIR 에 만들어 거기에만 주입한다.
# 주입값은 전부 가상이다. 실측이 아니므로 보고서·제출물에 인용하지 말 것.
set -e
ROOT="${0:A:h:h}"
PORT="${PORT:-8080}"
D="${TMPDIR:-/tmp}/apf_demo"
rm -rf "$D"; mkdir -p "$D"; cp -R "$ROOT/docs/" "$D/"

"$ROOT/.venv/bin/python" - "$D" "$ROOT" <<'PY'
import sys, json, math, pathlib, datetime
d_dir, root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
now = datetime.datetime.now()
cams = json.loads((root / "docs" / "data" / "cams.json").read_text(encoding="utf-8"))

EVENT = (126.9330, 37.5290)   # 이벤트광장 (nowcast.ZONES)
def dist_m(c):
    dy = (c["lat"] - EVENT[1]) * 111320
    dx = (c["lng"] - EVENT[0]) * 111320 * math.cos(math.radians(EVENT[1]))
    return math.hypot(dx, dy)

# 축제 저녁 21시를 가정한 가상값. ROI 보정 4대는 명/m², 나머지는 행사장 거리에 따른 등급.
CALIBRATED = {"331": 4.2, "192": 4.9, "310": 3.6, "725": 4.5}   # 63빌딩·마포남단·여의공원·원효남단
LOW_CONF_CAM = "39"          # 배경차분 실패 오탐 한 대 — σ 확대로 눌리는지 눈으로 보려고

cctv = {}
for c in cams:
    cid, m = c["camId"], dist_m(c)
    base = dict(ts=now.isoformat(timespec="seconds"), name=c["name"], ok=True, flow=0.2)
    if cid in CALIBRATED:
        rho = CALIBRATED[cid]
        lvl = "심각" if rho >= 5 else "경계" if rho >= 4 else "주의" if rho >= 3 else "여유"
        cctv[cid] = {**base, "calibrated": True, "density": rho, "level": lvl,
                     "count": round(rho * 10000, 1), "occupancy": 0.30, "confidence": "ok", "flags": []}
    else:
        low = cid == LOW_CONF_CAM
        lvl = "경계" if m < 700 else "주의" if m < 1400 else "여유"
        cctv[cid] = {**base, "calibrated": False, "density": None,
                     "level": "심각" if low else lvl, "count": None,
                     "occupancy": 1.0 if low else 0.20,
                     "confidence": "low" if low else "ok", "flags": ["bg_fail"] if low else []}

p = d_dir / "data" / "latest.json"
payload = json.loads(p.read_text(encoding="utf-8"))
payload["generated"] = now.isoformat(timespec="seconds")
payload["cctv"] = cctv
snap = payload.setdefault("forecast", {}).setdefault("live_snapshot", {})
for name, lvl, pp in (("여의도한강공원", "붐빔", [120000, 150000]),
                      ("여의도", "약간 붐빔", [95000, 130000]),
                      ("여의서로", "붐빔", [1500, 2200])):
    snap.setdefault(name, {}).update(congest=lvl, ts=now.strftime("%Y-%m-%d %H:%M"),
                                     ppltn=pp, role="core", fcst=[])
p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
n_cal = sum(1 for v in cctv.values() if v["calibrated"])
n_low = sum(1 for v in cctv.values() if v["confidence"] == "low")
print(f"가상 관측 주입 — CCTV {len(cctv)}대 (ROI 보정 {n_cal} · 저신뢰 {n_low}) + 서울시 구역등급 3곳")
PY

echo "→ http://127.0.0.1:$PORT   (Ctrl+C 로 종료 · 저장소는 그대로다)"
cd "$D" && exec python3 -m http.server "$PORT"
