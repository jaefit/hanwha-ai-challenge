#!/usr/bin/env python3
"""서울 실시간 도시데이터 + 실시간 지하철 도착 수집기.

  .venv/bin/python src/collector_api.py            # 5분 간격 무한 루프
  .venv/bin/python src/collector_api.py --once     # 1회 (테스트)

출력: data/live/api_YYYYMMDD.jsonl (1줄 = 1핫스팟 1시각). 키는 .env 에서 읽는다.
예산: 핫스팟 3 × 5분 × 24h = 864회/일 (일반키), 지하철 4역 × 5분 × 18~24시 = 288회/일 (지하철키, 상한 1,000).
"""
import os, sys, json, time, datetime, pathlib, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = {}
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); ENV[k.strip()] = v.strip()
KG, KS = ENV["SEOUL_KEY_GENERAL"], ENV["SEOUL_KEY_SUBWAY"]

HOTSPOTS = ["여의도한강공원", "여의도", "여의서로"]
STATIONS = ["여의나루", "여의도", "샛강", "국회의사당"]
SUBWAY_HOURS = range(17, 24)          # 지하철키 예산 보호: 17~23시만
INTERVAL = int(os.environ.get("INTERVAL", "300"))
OUT = ROOT / "data" / "live"; OUT.mkdir(parents=True, exist_ok=True)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "collector/0.1"}), timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def citydata(name):
    d = get(f"http://openapi.seoul.go.kr:8088/{KG}/json/citydata/1/5/{urllib.parse.quote(name)}")
    c = d["CITYDATA"]; p = c["LIVE_PPLTN_STTS"][0]
    road = c.get("ROAD_TRAFFIC_STTS", {}).get("AVG_ROAD_DATA", {})
    w = (c.get("WEATHER_STTS") or [{}])[0]
    return {
        "area": c["AREA_NM"], "area_cd": c["AREA_CD"],
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
    if "--once" in sys.argv:
        tick(); sys.exit(0)
    while True:
        t0 = time.time()
        try: tick()
        except Exception as e: print("tick error", e)
        time.sleep(max(1, INTERVAL - (time.time() - t0)))
