#!/usr/bin/env python3
"""서울 열린데이터광장 대용량 파일 재다운로드 (data/raw/ 복원용).

열린데이터광장의 '파일내려받기'는 JS 폼 POST + 세션 쿠키가 필요하다.
브라우저 없이 받으려면 데이터셋 페이지를 먼저 GET 해 쿠키를 받고,
datafile.seoul.go.kr 에 infId / infSeq / seq 를 POST 한다.

  python src/fetch_seoul_data.py subway            # OA-12921 2024·2025 시간대별 승하차 CSV
  python src/fetch_seoul_data.py od 20250927 20241005   # OA-22300 일별 출발-도착 OD zip
  python src/fetch_seoul_data.py mode 20250927     # OA-22657 일별 수단 OD zip
  python src/fetch_seoul_data.py move 202509       # OA-22298 월별 도착지 기준 성연령 zip
  python src/fetch_seoul_data.py card 202509 202410 # OA-12914 교통카드 역별 일별 승하차 월파일(1~9호선) — 9호선 용량 비례추정용

인증키 불필요. 각 파일 60~90MB. 출처·기준일은 data/README.md 참고.
"""
import re
import sys
import pathlib
import urllib.request
import urllib.parse
import http.cookiejar

RAW = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw"
VIEW = "https://data.seoul.go.kr/dataList/{inf}/F/1/datasetView.do"
DOWN = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
UA = {"User-Agent": "Mozilla/5.0 (hanwha-ai-challenge data fetch)"}

# (데이터셋 ID, seq 규칙, 저장 파일명 규칙)
SETS = {
    "subway": ("OA-12921", {"2024": "44", "2025": "46"}, "subway_{k}.csv"),
    "od":     ("OA-22300", lambda d: d[2:],               "od_{k}.zip"),
    "mode":   ("OA-22657", lambda d: d[2:],               "mode_{k}.zip"),
    "move":   ("OA-22298", lambda d: d,                   "move_{k}.zip"),
    "card":   ("OA-12914", "scrape",                      "card_{k}.csv"),   # 교통카드 역별 일별 승하차(1~9호선). k=YYYYMM, seq 는 페이지에서 파일명으로 찾는다
}


def session_for(inf):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = list(UA.items())
    page = opener.open(VIEW.format(inf=inf), timeout=60).read().decode("utf-8", "ignore")
    # 파일 다운로드 폼(frmFile)의 infSeq 를 쓴다 — 데이터셋마다 다르다(OA-12921=1, OA-12914=3). API 폼(frmApiDown)의 값과 혼동 금지
    m = re.search(r'name="frmFile".*?name="infSeq"\s+value="(\d+)"', page, re.S)
    return opener, (m.group(1) if m else "1"), page


def download(kind, keys):
    inf, rule, name = SETS[kind]
    opener, inf_seq, page_cache = session_for(inf)
    RAW.mkdir(parents=True, exist_ok=True)
    for k in keys:
        if rule == "scrape":   # 파일명 → downloadFile('seq') 매핑을 데이터셋 페이지에서 읽는다
            m = re.search(r"CARD_SUBWAY_MONTH_%s\.csv\"\s+onclick=\"javascript:downloadFile\('(\d+)'\)" % k, page_cache)
            if not m: print("seq not found for", k); continue
            seq = m.group(1)
        else:
            seq = rule[k] if isinstance(rule, dict) else rule(k)
        out = RAW / name.format(k=k)
        if out.exists() and out.stat().st_size > 1_000_000:
            print("skip (exists)", out.name); continue
        body = urllib.parse.urlencode({"infId": inf, "seqNo": "", "infSeq": inf_seq, "seq": seq}).encode()
        req = urllib.request.Request(DOWN, data=body, headers={**UA, "Referer": VIEW.format(inf=inf)})
        data = opener.open(req, timeout=900).read()
        if len(data) < 1_000_000 or data[:20].lower().startswith(b"<html"):
            print("FAIL", out.name, data[:120]); continue
        out.write_bytes(data)
        print("saved", out.name, f"{len(data)/1e6:.1f}MB")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in SETS:
        print(__doc__); sys.exit(1)
    kind = sys.argv[1]
    keys = sys.argv[2:] or (["2024", "2025"] if kind == "subway" else [])
    if not keys:
        print("날짜를 지정해라 (예: 20250927)"); sys.exit(1)
    download(kind, keys)
