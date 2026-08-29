#!/usr/bin/env python3
"""L1 베이스라인: 2024·2025 축제일 KT OD + 지하철 실적 → data/derived/baseline.json

- 유입/유출 시간대 곡선(2년 평균, 형태 = 시간대 비율), 방향 분포, 수단 분포, 출구 용량
- 입력: data/raw/od_20241005.zip, od_20250927.zip, mode_20250927.zip, subway_2024.csv, subway_2025.csv
- 여의동 = 11560540. 목적코드 3=귀가. 수단코드(추정) 6지하철 8차량 5일반버스 7도보 4광역버스 9기타
"""
import zipfile, io, csv, json, pathlib, collections, statistics

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "data" / "raw", ROOT / "data" / "derived"
Y = "11560540"
GU = {"11110":"종로","11140":"중구","11170":"용산","11200":"성동","11215":"광진","11230":"동대문","11260":"중랑","11290":"성북","11305":"강북","11320":"도봉","11350":"노원","11380":"은평","11410":"서대문","11440":"마포","11470":"양천","11500":"강서","11530":"구로","11545":"금천","11560":"영등포","11590":"동작","11620":"관악","11650":"서초","11680":"강남","11710":"송파","11740":"강동"}
CORRIDOR = {  # 목적지 → 귀가 회랑 (topic-fireworks.md §5 L3)
    "서": ["영등포","구로","금천","양천","강서","41190","41210","41390","41570","28"],
    "북서": ["마포","서대문","은평","41280","41480"],
    "북동": ["용산","종로","중구","성동","광진","동대문","중랑","성북","강북","도봉","노원","41310","41360","41150","41630","41650"],
    "남": ["동작","관악","41170","41410","41430","41110","41590","41370","41220","41270"],
    "남동": ["강남","서초","송파","강동","41130","41450","41460","41290"],
}
MODE = {"4":"광역버스","5":"일반버스","6":"지하철","7":"도보","8":"차량","9":"기타"}


def corridor(code):
    key = GU.get(code[:5]) or (code[:5] if code.startswith("41") else ("28" if code.startswith("28") else "기타"))
    for c, members in CORRIDOR.items():
        if key in members: return c
    return "기타"


def read_zip_csv(p):
    z = zipfile.ZipFile(p); raw = z.read(z.namelist()[0])
    try: txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError: txt = raw.decode("cp949")
    return csv.DictReader(io.StringIO(txt))


def od_curves(day):
    inflow, outflow, direction = collections.Counter(), collections.Counter(), collections.Counter()
    for r in read_zip_csv(RAW / f"od_{day}.zip"):
        v = float(r["cnt"] or 0); t = int(r["st_time_cd"][:2])
        if r["d_admdong_cd"] == Y and r["o_admdong_cd"] != Y: inflow[t] += v
        if r["o_admdong_cd"] == Y and r["d_admdong_cd"] != Y:
            outflow[t] += v
            if t >= 20: direction[corridor(r["d_admdong_cd"])] += v
    return inflow, outflow, direction


def mode_share(day):
    m = collections.Counter()
    for r in read_zip_csv(RAW / f"mode_{day}.zip"):
        if r["o_admdong_cd"] == Y and r["d_admdong_cd"] != Y and int(r["st_time_cd"][:2]) >= 20:
            m[MODE.get(r["move_trans"], r["move_trans"])] += float(r["cnt"] or 0)
    tot = sum(m.values()); return {k: round(v / tot, 4) for k, v in m.items()}


def subway_capacity():
    """관측 최대 시간당 승차 = 용량 하한. 1~8호선만(9호선 없음)."""
    cap = collections.defaultdict(int)
    for yr in ("2024", "2025"):
        raw = (RAW / f"subway_{yr}.csv").read_bytes()
        rows = list(csv.reader(io.StringIO(raw.decode("cp949", "ignore"))))
        hdr = rows[0]
        di = next(i for i, h in enumerate(hdr) if "일자" in h or "날짜" in h); si = hdr.index("역명")
        ti = next(i for i, h in enumerate(hdr) if "구분" in h)
        hcols = [(i, h) for i, h in enumerate(hdr) if "시" in h and i not in (di, si, ti) and any(c.isdigit() for c in h)]
        day = "20241005" if yr == "2024" else "20250927"
        for r in rows[1:]:
            if r[di].replace("-", "") == day and r[ti] == "승차" and r[si] in ("여의나루", "여의도", "신길", "샛강", "국회의사당"):
                mx = max(int(float(r[i] or 0)) for i, _ in hcols)
                cap[r[si]] = max(cap[r[si]], mx)
    return dict(cap)


def main():
    days = ["20241005", "20250927"]
    curves = {d: od_curves(d) for d in days}
    def shape(counters, lo, hi):
        out = {}
        for h in range(lo, hi + 1):
            vals = [c[h] for c in counters]; out[str(h)] = round(statistics.mean(vals))
        return out
    inflow_shape = shape([curves[d][0] for d in days], 10, 23)
    outflow_shape = shape([curves[d][1] for d in days], 17, 23)
    dir_share = {}
    for d in days:
        tot = sum(curves[d][2].values()); dir_share[d] = {k: round(v / tot, 4) for k, v in curves[d][2].items()}
    dir_avg = {k: round(statistics.mean(dir_share[d].get(k, 0) for d in days), 4) for k in CORRIDOR.keys() | {"기타"}}
    base = {
        "source": {"od": "서울 열린데이터광장 OA-22300 (KT 수도권 생활이동, 출발-도착 행정동)", "mode": "OA-22657", "subway": "OA-12921 서울교통공사 역별·일별·시간대별 승하차", "days": days, "generated": "src/baseline.py"},
        "yeouido_admdong": Y,
        "inflow_total": {d: round(sum(curves[d][0].values())) for d in days},
        "inflow_by_hour_mean": inflow_shape,
        "outflow_by_hour_mean": outflow_shape,
        "outflow_direction_share_by_day": dir_share,
        "outflow_direction_share_mean": dir_avg,
        "outflow_mode_share_20250927": mode_share("20250927"),
        "mode_code_note": "수단 코드표 미확정. 설명 순서 기반 추정(6=지하철, 8=차량). 확정 시 갱신",
        "subway_capacity_obs_max_per_hour": subway_capacity(),
        "closure_rules": [{"station": "여의나루", "line": "5", "hours": [19, 20], "rule": "무정차 통과(2024·2025 하차 ≈0 실적)"}],
    }
    DER.mkdir(parents=True, exist_ok=True)
    (DER / "baseline.json").write_text(json.dumps(base, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: base[k] for k in ("inflow_total", "outflow_by_hour_mean", "outflow_direction_share_mean", "outflow_mode_share_20250927", "subway_capacity_obs_max_per_hour")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
