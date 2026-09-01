#!/usr/bin/env python3
"""서울 실시간 도시데이터 + 실시간 지하철 도착 수집기.

  .venv/bin/python src/collector_api.py            # 5분 간격 무한 루프
  .venv/bin/python src/collector_api.py --once     # 1회 (테스트)
  .venv/bin/python src/collector_api.py --budget   # 키별 일 호출 수만 출력 (호출 안 함)

출력: data/live/api_YYYYMMDD.jsonl (1줄 = 1핫스팟 1시각). 키는 .env 에서 읽는다.
예산(상한 1,000/키): 코어 3 × 5분 × 24h = 864회(일반키) · 지하철 4역 × 17~23시 = 336회(지하철키)
                    피더 12곳 12~19시 + 관람지 6곳 17~23시 = 키당 576+252 = 828회(피더키 2개에 순번 분산)

환경변수:
  INTERVAL=300        틱 간격(초)
  FEEDERS=강남역,...   피더 핫스팟(유입 출발지 역) 추가 수집 — 실명은 서울 121장소 목록과 정확히 일치해야 함
  WATCH=default       강 건너 관람 명당(기본 6곳). WATCH= 로 비우면 수집 안 함
  UNTIL=2026-08-30T00:10   이 시각 이후 종료(일 쿼터 보호)
  목록을 바꾸면 --budget 으로 키별 합이 1,000 을 넘지 않는지 먼저 확인할 것.
"""
import os, sys, json, time, datetime, pathlib, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = {}
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); ENV[k.strip()] = v.strip()
KG, KS = ENV["SEOUL_KEY_GENERAL"], ENV["SEOUL_KEY_SUBWAY"]
# 피더 전용 citydata 키들 (일 쿼터 분리·분산, 2026-08-31 발급). 피더는 목록 순번 % 키 수 로 고정 배정 → 키당 6곳 × 8h × 12회 = 576/일
FEEDER_KEYS = [v for v in (ENV.get("SEOUL_KEY_FEEDER", "").strip(), ENV.get("SEOUL_KEY_FEEDER2", "").strip()) if v]

CORE = ["여의도한강공원", "여의도", "여의서로"]   # 여의도 내부 구역 전부 — 121장소 전수 조회(9/1)로 이 3개가 끝임을 확인
# 피더 기본 8곳 = 귀속 상위 × 개별 상관(feeder_leadlag.json) × citydata 실명 확인(8/31). 김포공항 r=-0.19 제외.
FEEDER_DEFAULT = ["영등포 타임스퀘어", "신도림역", "사당역", "홍대입구역(2호선)", "노량진", "고속터미널역",
                  "신림역", "강남역", "성수카페거리", "잠실역", "오목교역·목동운동장", "가산디지털단지역"]   # 8/31 확장 12곳: 성수 r lag1 0.95, 잠실·오목교·가산 POI 확인
_f = os.environ.get("FEEDERS", "").strip()
FEEDERS = FEEDER_DEFAULT if _f == "default" else [x.strip() for x in _f.split(",") if x.strip()]   # 피더 핫스팟(선행지표)
FEEDER_HOURS = range(12, 20)          # 피더키 예산 보호: 12~19시만 — 도착 창. 12곳 ÷ 키 2개 = 키당 576/일
# 강 건너 관람 명당 — "여의도 붐비면 여기서 보세요" 분산 안내용 관측점. 실명은 121장소 전수 조회(9/1)로 확인.
WATCH_DEFAULT = ["노들섬", "이촌한강공원", "반포한강공원", "망원한강공원", "양화한강공원", "용산역"]
_w = os.environ.get("WATCH", "default").strip()
WATCH = WATCH_DEFAULT if _w == "default" else [x.strip() for x in _w.split(",") if x.strip()]
WATCH_HOURS = range(17, 24)           # 축제창만 — 관람지는 저녁에만 의미. 6곳 ÷ 키 2개 = 키당 3곳 × 7h × 12회 = 252/일
if not FEEDER_KEYS and WATCH:
    print("WARN: 피더 전용 키 없음 → 관람지 수집 비활성 (KG 키 864/1,000 이미 사용)", flush=True); WATCH = []
HOTSPOTS = CORE + FEEDERS + WATCH
STATIONS = ["여의나루", "여의도", "샛강", "국회의사당"]
SUBWAY_HOURS = range(17, 24)          # 지하철키 예산 보호: 17~23시만
INTERVAL = int(os.environ.get("INTERVAL", "300"))
UNTIL = datetime.datetime.fromisoformat(os.environ["UNTIL"]) if os.environ.get("UNTIL") else None
OUT = ROOT / "data" / "live"; OUT.mkdir(parents=True, exist_ok=True)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "collector/0.1"}), timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def role_of(name):
    return "core" if name in CORE else "watch" if name in WATCH else "feeder"


def feeder_key(name):
    if not FEEDER_KEYS: return KG                                     # 전용 키 없으면 KG 폴백
    pool = FEEDERS + WATCH                                            # 피더 뒤에 관람지를 이어 붙임 → 기존 피더 배정 불변
    i = pool.index(name) if name in pool else 0
    return FEEDER_KEYS[i % len(FEEDER_KEYS)]                          # 순번 고정 배정 → 키당 부하 균등·재현 가능


def budget():
    """키별 일 호출 수 — 상한 1,000. 런북 점검용(--budget)."""
    ticks = 3600 // INTERVAL
    rows = {"KG(코어)": len(CORE) * 24 * ticks, "KS(지하철)": len(STATIONS) * len(SUBWAY_HOURS) * ticks}
    for i, _ in enumerate(FEEDER_KEYS):
        n_f = len([x for j, x in enumerate(FEEDERS + WATCH) if j % len(FEEDER_KEYS) == i and x in FEEDERS])
        n_w = len([x for j, x in enumerate(FEEDERS + WATCH) if j % len(FEEDER_KEYS) == i and x in WATCH])
        rows[f"피더키{i + 1}"] = n_f * len(FEEDER_HOURS) * ticks + n_w * len(WATCH_HOURS) * ticks
    return rows


def citydata(name):
    key = KG if name in CORE else feeder_key(name)                    # 코어는 KG, 피더·관람지는 전용 키 (쿼터 분리)
    d = get(f"http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/{urllib.parse.quote(name)}")
    c = d["CITYDATA"]; p = c["LIVE_PPLTN_STTS"][0]
    road = c.get("ROAD_TRAFFIC_STTS", {}).get("AVG_ROAD_DATA", {})
    w = (c.get("WEATHER_STTS") or [{}])[0]
    return {
        "area": c["AREA_NM"], "area_cd": c["AREA_CD"], "role": role_of(name),                    # 요청명 기준 — AREA_NM 표기가 목록과 다를 수 있다
        "ppltn_time": p["PPLTN_TIME"], "congest": p["AREA_CONGEST_LVL"],
        "ppltn_min": int(p["AREA_PPLTN_MIN"]), "ppltn_max": int(p["AREA_PPLTN_MAX"]),
        "non_resnt_rate": float(p.get("NON_RESNT_PPLTN_RATE") or 0),
        "age": {k[-2:]: float(p[k]) for k in p if k.startswith("PPLTN_RATE_")},
        "female_rate": float(p.get("FEMALE_PPLTN_RATE") or 0),
        "fcst": [{"t": f["FCST_TIME"], "lvl": f["FCST_CONGEST_LVL"], "min": int(f["FCST_PPLTN_MIN"]), "max": int(f["FCST_PPLTN_MAX"])} for f in p.get("FCST_PPLTN", [])],
        "sub_live": c.get("LIVE_SUB_PPLTN") or {},
        "bus_live": c.get("LIVE_BUS_PPLTN") or {},
        "road_idx": road.get("ROAD_TRAFFIC_IDX"), "road_spd": road.get("ROAD_TRAFFIC_SPD"),
        "prk": [{"nm": x["PRK_NM"], "cur": x.get("CUR_PRK_CNT"), "cap": x.get("CPCTY")} for x in c.get("PRK_STTS", [])],
        "acdnt": c.get("ACDNT_CNTRL_STTS") or [],
        "dst_msg": c.get("LIVE_DST_MESSAGE") or [],
        "weather": {"temp": w.get("TEMP"), "pcp": w.get("PRECIPITATION"), "pcp_type": w.get("PRECPT_TYPE"), "msg": w.get("PCP_MSG")},
    }


def subway(st):
    d = get(f"http://swopenAPI.seoul.go.kr/api/subway/{KS}/json/realtimeStationArrival/0/20/{urllib.parse.quote(st)}")
    rows = d.get("realtimeArrivalList", [])
    return [{"line": r.get("trainLineNm"), "updn": r.get("updnLine"), "msg": r.get("arvlMsg2"), "sec": r.get("barvlDt")} for r in rows]


def tick():
    now = datetime.datetime.now()
    fn = OUT / f"api_{now:%Y%m%d}.jsonl"
    with fn.open("a", encoding="utf-8") as f:
        for h in HOTSPOTS:
            if h in WATCH and now.hour not in WATCH_HOURS: continue        # 관람지는 축제창(17~23시)만
            if h in FEEDERS and now.hour not in FEEDER_HOURS: continue     # 피더키 예산 보호 (12~19시만)
            try:
                rec = {"ts": now.isoformat(timespec="seconds"), "kind": "citydata", **citydata(h)}
            except Exception as e:
                rec = {"ts": now.isoformat(timespec="seconds"), "kind": "citydata", "area": h, "error": str(e)[:200]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(now.strftime("%H:%M"), h, rec.get("congest"), rec.get("ppltn_min"), "~", rec.get("ppltn_max"), rec.get("error", ""))
        if now.hour in SUBWAY_HOURS or "--force-subway" in sys.argv:
            for st in STATIONS:
                try:
                    rec = {"ts": now.isoformat(timespec="seconds"), "kind": "subway", "station": st, "arrivals": subway(st)}
                except Exception as e:
                    rec = {"ts": now.isoformat(timespec="seconds"), "kind": "subway", "station": st, "error": str(e)[:200]}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print("   ", st, len(rec.get("arrivals", [])), "trains", rec.get("error", ""))


if __name__ == "__main__":
    if "--budget" in sys.argv:
        for k, v in budget().items(): print(f"{k:12s} {v:5d}/1000 {'OVER' if v > 1000 else 'ok'}")
        sys.exit(0)
    if "--once" in sys.argv:
        tick(); sys.exit(0)
    print(f"hotspots={len(HOTSPOTS)} (core {len(CORE)} · feeder {len(FEEDERS)} · watch {len(WATCH)}) interval={INTERVAL}s until={UNTIL}", flush=True)
    while True:
        if UNTIL and datetime.datetime.now() >= UNTIL:
            print("UNTIL reached, exit", flush=True); break
        t0 = time.time()
        try: tick()
        except Exception as e: print("tick error", e)
        sys.stdout.flush()
        time.sleep(max(1, INTERVAL - (time.time() - t0)))
