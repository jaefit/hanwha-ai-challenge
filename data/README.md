# data/

- `raw/` — git 제외. 원본 대용량. `python src/fetch_seoul_data.py`로 재다운로드.
  - `subway_2024.csv`, `subway_2025.csv` — 서울교통공사 역별·일별·시간대별 승하차 (OA-12921, cp949)
  - `od_YYYYMMDD.zip` — KT 생활이동 출발-도착 (OA-22300, 일별, seq=yymmdd)
  - `mode_YYYYMMDD.zip` — KT 생활이동 수단 (OA-22657)
  - `move_YYYYMM.zip` — KT 생활이동 도착지 기준 성연령 (OA-22298, 월별)
- `derived/` — 커밋 대상. 위에서 뽑은 작은 요약(JSON/CSV). 모든 파일에 출처·기준일 컬럼 또는 헤더 주석.
