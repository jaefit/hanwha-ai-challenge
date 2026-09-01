# data/

세 층이다. **`raw/` 는 원본(git 제외) · `derived/` 는 커밋하는 요약 · `live/` 는 당일 수집 로그(git 제외, 종료 후 선별 커밋).**

## `raw/` — 원본 대용량, git 제외

`python src/fetch_seoul_data.py` 로 재다운로드한다.

| 파일 | 내용 |
| :-- | :-- |
| `subway_2024.csv` · `subway_2025.csv` | 서울교통공사 역별·일별·시간대별 승하차 (OA-12921, cp949). **9호선 미포함** |
| `card_YYYYMM.csv` · `card_YYYYMMDD.json` | 교통카드 역별 일별 (OA-12914). 9호선 포함 — 출구 비중 산출의 근거 |
| `od_YYYYMMDD.zip` | KT 수도권 생활이동 출발-도착 (OA-22300, 일별, seq=yymmdd) |
| `mode_YYYYMMDD.zip` | KT 생활이동 수단 (OA-22657) |
| `move_YYYYMM.zip` | KT 생활이동 도착지 기준 성연령 (OA-22298, 월별) |
| `lifepop_dong_YYYYMM.zip` | 서울 생활인구 행정동 단위 (OA-14991). 평시·전야제·당일 3자 비교용 (2026-09-01 확보) |

## `derived/` — 커밋 대상

위에서 뽑은 작은 요약(JSON). **모든 파일에 출처·기준일을 헤더 주석이나 필드로 남긴다.**

| 파일 | 무엇 | 만든 스크립트 |
| :-- | :-- | :-- |
| `baseline.json` | L1 베이스라인 — 시간대별 유입/유출 형태 곡선·방향·수단 분포·용량 | `src/baseline.py` |
| `exit_shares.json` | 출구 7곳의 축제일 초과 승차 비중(2년 평균) — L3 배정의 근거 | `src/exit_shares.py` |
| `line9_capacity.json` | 9호선 3역 용량 비례 추정 (**추정** 표기) | `src/line9_capacity.py` |
| `backtest.json` | 백테스트 — A in-sample 0.245/0.214, B cross-year 0.420/0.438 | `src/backtest.py` |
| `exit_forecast_2026.json` | 2026 사전 예측표 (챗봇 프롬프트·오프라인 폴백 입력) | `src/backtrack.py` |
| `od_*_yeouido.json` · `od_yeouido_summary.json` | 여의동 유입·유출·방향 (2024·2025 축제일 + 평시 대조일) | 일회성 추출 (`raw/od_*.zip` 에서) |
| `lifepop_yeouido.json` | 여의동 생활인구 평시/전야제/당일 (OA-14991) | 일회성 추출 |
| `feeder_leadlag.json` | 피더 선행지표 — 상류 역이 여의도를 몇 분 앞서는가 | `src/feeder_leadlag.py` |
| `feeder_origin.json` | 출발지 구성 (출구 수요 산출의 입력) | `src/backtrack.py` |
| `eve_rehearsal.json` | 전야제 리허설 합격선 근거 (평시 금요일 대비 1.9배, OA-12921) | 일회성 추출 |
| `stations.json` · `topis_yeouido_cams.json` | 역 좌표·CCTV 23대 메타 | `src/fetch_seoul_data.py` · TOPIS 목록 |
| `eval_20260829.json` | 오차 평가 산출물 (T6) | `src/evaluate.py` |

"일회성 추출"은 재현 스크립트가 저장소에 없다는 뜻이다. **각 JSON 의 `doc`·`source` 필드에 원본과 기준일이 적혀 있으니 인용할 때 그걸 옮긴다.**

## `live/` — 당일 수집, git 제외

`run_all.sh` 가 쓴다. `api_YYYYMMDD.jsonl`(서울시 도시데이터 5분) · `cctv_YYYYMMDD.jsonl`(TOPIS 집계값 30초) · `forecast_latest.json`(최신 예측) · `forecast_history/`(예측 스냅샷 이력 — "그 시점에 뭐라고 예측했었나"의 사후 재현용, T6 입력). `publish_fail_streak` 파일이 생겼다면 **발행이 연속 실패 중**이라는 뜻이다.

**행사 종료 후 당일 로그만 골라 커밋한다.** CCTV는 프레임을 저장하지 않고 집계값(인원·점유율·흐름)만 남긴다.

## 저장소 밖

`docs/data/` 는 브라우저가 읽는 발행본이다(`latest.json`·`cams.json`·`baseline.json`·`routing/walk_graph.json`). 보행망 `walk_graph.json` 은 5.95MB — 경로 찾기를 누를 때만 받는다.
