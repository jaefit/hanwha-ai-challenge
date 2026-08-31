# 제출까지 실행 계획 (8/29 → 9/8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 §4 완료 정의를 9/8 20:00 전에 전부 체크한다.

**Architecture:** 사전 예측(backtrack) 위에 당일 레이어(nowcast)를 얹는 현 구조를 바꾸지 않는다. 남은 일은 (a) 검증 뼈대, (b) 미착수 산출물 3개, (c) 당일 운영 런북, (d) 제출 패키징.

**Tech Stack:** Python 3.14 venv(`.venv`), pytest, 정적 HTML(MapLibre), GitHub Pages, zsh 스크립트.

**Spec:** `docs/superpowers/specs/2026-08-29-submission-design.md`

## Priority (2026-08-29 오차 예산 기준)

성능(9/5 순위·부하율 정확도)에 실제로 기여하는 순서: **⓪ 출구 배정 관측화(T1d, 8/29 완료) → ① 9호선 용량(T1b, 완료) → ② 순차 데이터동화(T1c) → ③ CCTV ROI(T2, 야간 테스트 조건부) → ⑤ 쇼 종료 시각 기입(T9)**. 나머지 태스크는 산출물·점수용. 학술 접목 중 conformal 구간·아날로그·JuPedSim·CLIP은 보류(`benchmark-crowd-systems.md` 참조).

## Global Constraints

- 숫자엔 출처·기준일. 모르는 값은 비운다. 추정은 "추정" 표기. (CLAUDE.md)
- 키·PIN·제출코드는 어떤 파일에도 쓰지 않는다. `.env`만.
- CCTV 프레임 저장 금지(캘리브레이션 1회용 `cam_calib.py`는 저장소 밖).
- 작업 후 commit + push (맥↔회사 PC).
- **코드 동결: 9/4 12:00 이후 `src/`·`docs/index.html` 변경은 hotfix만**, 변경 시 `pytest` 통과 후 push.
- 구현 전 분류·설계 제시 → 사용자 승인 (approval-gate).

---

### Task 1: 모델 불변식 테스트 (8/29)

**Files:**
- Create: `tests/test_model.py`
- Modify: `requirements.txt` (pytest 추가), `README.md` 읽는 순서에 스펙·플랜·테스트 한 줄

**Interfaces:**
- Consumes: `src/nowcast.py` `lag_table, kladek, arrival_split, compute_exits, shift_for, ASSIGN, CAP, CLOSED`; `src/backtrack.py` `origin_key`; `src/baseline.py` `corridor`; `data/derived/exit_forecast_2026.json`
- Produces: 이후 모든 태스크의 회귀 검증 명령 `.venv/bin/python -m pytest tests -q`

- [ ] **Step 1: 테스트 작성** — 지연표 합=1 · 기본 밀도에서 여의도(5) 같은 시간대 비율 0.25~0.45 · kladek 단조감소·하한 · arrival_split T=0/90 · ASSIGN 행 합=1 · 수요 보존(lag {0:1}) · 통제 이관 · origin_key/corridor · shift_for · 사전표 스키마
- [ ] **Step 2: 실행해 실패/통과 확인** — `.venv/bin/python -m pytest tests -q` (신규 테스트라 첫 실행에서 통과가 정상. 의도적 회귀 1건: `V_MIN`을 0으로 바꾸고 kladek 테스트가 실패하는지 확인 후 되돌림)
- [ ] **Step 3: 커밋** — `git add tests requirements.txt README.md && git commit -m "test: 모델 불변식 pytest 10건"`

### Task 1b: 9호선 용량 데이터화 (8/29~30) — 오차 예산 1순위

**Files:**
- Modify: `src/nowcast.py` `CAP` (9호선 3역), `data/derived/baseline.json`(`subway_capacity_obs_max_per_hour`에 9호선 추정 근거), `src/fetch_seoul_data.py`(교통카드 역별 데이터 다운로드)
- Create: `data/derived/line9_capacity.json`

**Interfaces:**
- Consumes: 서울 열린데이터광장 교통카드 역별 승하차(전 노선, 9호선 포함) — 일별(`CardSubwayStatsNew`) 및 시간대별 월집계(`CardSubwayTime`) — 서비스명은 검색으로 확정
- Produces: `CAP["여의도(9)"|"샛강(9)"|"국회의사당(9)"]` = 5호선 여의도 축제일 시간당 최대 승차 × (축제일 9호선 역 일 승차 ÷ 5호선 여의도 일 승차). `estimated_capacity` 는 유지하되 근거를 "비례 추정(교통카드 일별)"으로

- [ ] **Step 1: 데이터 존재 확인(spike)** — 서비스명·9호선 포함 여부·2025-09-27 일자 조회 가능 여부. 없으면 국토부 지침 pph × 게이트 수로 대체하고 "추정"
- [ ] **Step 2: 다운로드 스크립트** — `fetch_seoul_data.py card 20250927 20241005` → `data/raw/card_YYYYMMDD.json`
- [ ] **Step 3: 비례 추정 계산** — `src/line9_capacity.py` → `line9_capacity.json`(역별 비율·추정 용량·출처·기준일). `nowcast.CAP` 가 파일 있으면 읽도록
- [ ] **Step 4: 검증** — `pytest` 통과, `backtrack.py` 재실행 후 21시 순위 변화 기록, 커밋

### Task 1d: 출구 배정을 관측 초과 승차로 교체 (8/29 완료) — T1b 중 발견, 오차 예산 신규 1순위

**Files:** `src/exit_shares.py`(신규) → `data/derived/exit_shares.json`, `src/nowcast.py` `compute_exits` 관측 모드, `src/backtrack.py`, `tests/test_model.py` 2건, `topic-fireworks.md` §5 정정

- [x] 관측: 교통카드 일별(9호선)+교통공사 시간대별(5호선·마포) 축제일 초과 승차 → 출구 7개 E_st·비중. 2년 합계 108.7k/109.3k(0.6% 차)
- [x] 모델: 수요(st,h) = α × E_st × 도착 형태(KT 곡선+지연, 19~23시 개방 시간대 정규화). 회랑 배정표는 참고 필드
- [x] 백테스트(2024·2025 실측 시간대 승차 4역): 절대오차/실측 0.34→**0.25**, 0.41→**0.29**. 여의나루 재배정 이중계산·평가창 정규화 2회 정정
- [x] 백테스트 스크립트화 `src/backtest.py` → `data/derived/backtest.json` (8/30). A in-sample **0.24/0.29**, 등급 적중 88%/94%. **B cross-year(다른 해 E·곡선으로 예측 = 2026 조건) 0.44/0.44**, 등급 76%/88% — 연도 간 규모 이동(여의도(5) 21시 17.8k↔12.5k)이 주 오차. pytest 회귀 가드 추가
- [x] 여의나루 해제 직후 승차(2024 21시 2.3k / 2025 5.8k): **통제 시간대 도착분을 해제 후 첫 개방 시간대로 이월**(8/30 결정, 2026 은 22시 합산). 백테스트도 같은 규칙으로 합산 비교 → A 2025 0.29→**0.21**(등급 17/17), 2024 0.24 유지, B 0.42/0.44
- [ ] 한계 기록: 마포역 20시 과소(보행자 조기 도착 5.1k/5.8k vs 예측 2.5k), 신길 1호선 미포함, 9호선 시간대 실측 없음, 여의나루 23시 과소(이월로 22시 집중, 실측 2.6k/2.9k vs 예측 0.7k)

### Task 1c: 순차 데이터동화 (particle filter) — 오차 예산 2순위 (8/30~9/1)

**Files:**
- Modify: `src/nowcast.py` (`alpha()` → `assimilate()`), `tests/test_model.py` (입자 가중 정규화·관측 없을 때 사전 유지 테스트)
- Output 필드: `forecast_latest.json.assimilation` = {n_particles, eff_sample_size, posterior: {alpha: [p10,p50,p90], zone_density_scale, lag_shift_min}}, 출구별 `load_lo/hi` = 입자 예측의 p10/p90

**Interfaces:**
- Consumes: 오늘 `api_*.jsonl`(핫스팟 인구 min~max·여의나루 누적 하차), 사전표 밴드(사전 분포 폭), `compute_exits`
- Produces: 라이브 `load/lo/hi` 가 관측 누적에 따라 좁아짐. 관측 없으면 사전표와 동일(회귀 테스트)

- [x] **Step 1: 설계 제시 → 승인** (8/30) — 입자 대신 **격자 61점(1/3~3, 결정론적)**, 상태는 α 하나. 관측 O1 여의나루 30분 하차 증분(12~19시) · O2 여의도 핫스팟 9역 30분 승차(19시~, 커버리지 c 당일 14~17시 추정). τ·방향은 식별 불가로 제외
- [x] **Step 2: 테스트 먼저** — 6건: 사전 재현(1.00/0.73/1.38) · 2배 관측 수렴·축소 · 아핀(평시 항) · 극단 edge_hit · 커버리지 폴백/추정 · 1건 과신 방지. red→green 에서 결함 3개 잡음(분위 반 셀 편향, σ 예측기준 편향 0.91, σ 관측기준 과신)
- [x] **Step 3: 구현·실행** — `assimilate()`·`_observations()`, `alpha()` 삭제. 8/29 평시 로그: α 0.58 [0.46–0.71] (평시라 낮음 = 정상)
- [x] **Step 4: 커밋. 대시보드는 필드 그대로 밴드 표시(변경 없음)** — 밴드 = α 사후 p10/p90 비율(관측 없으면 0.73~1.38)
- [ ] 9/4 전야제 로그로 커버리지 c 실측값 확인(폴백 1.3 vs 추정). O2 창 시각 오프셋(≤5분) 영향 점검

### Task 1e: 피더 선행지표 (8/31 사전 근거 완료 · 9/4~5 수집 · 9/6 검증)

**Files:**
- Done: `src/feeder_leadlag.py` → `data/derived/feeder_leadlag.json` (사전 근거 ④)
- Modify: `src/collector_api.py` (피더 전용 키 라우팅, 기본 8곳, 12~20시 게이트)
- Create (9/6): `src/feeder_verify.py` — 9/5 로그 5분 창 교차상관(랙 0~60분), "몇 분 먼저 알 수 있었나"

- [x] **④ 사전 교차상관 (8/31)** — X=피더 귀속 승차 합(시간대), Y=여의도(5)+여의나루 하차 초과. **lag1h r=0.993(2024)/0.981(2025), 합동 0.988**; lag0 0.72 → 도착이 승차보다 ~1시간대 늦게 정점(노선 25~40분+시간대 경계). 개별: 영등포시장 0.86·홍대입구 0.82·영등포구청 0.80 / 김포공항 -0.19(제외). 주의: 매끄러운 단봉 곡선 간 상관이라 과대 — 인과 증명이 아니라 "사슬 존재+위상차" 근거로만 기술
- [x] **피더 키·수집기 (8/31)** — 전용 citydata 키 발급(.env `SEOUL_KEY_FEEDER`, 레포 밖). 기본 8곳: 영등포 타임스퀘어·신도림역·사당역·홍대입구역(2호선)·노량진·고속터미널역·신림역·강남역 (POI 실명 API 확인). 12~20시 게이트 → 8×9h×12=864 < 1,000
- [ ] **9/4·9/5: `FEEDERS=default` 로 수집** (런북 T8에 반영) — **12곳**(성수·잠실역·오목교역·가산디지털단지역 추가, 8/31 POI 확인), 창 12~19시, **전용 키 2개 순번 분산(키당 576/일)**. 9/5 모델 입력엔 **안 씀**
- [ ] **9/6: 검증** — 피더 30분 초과 승차(OA-12921 토 중앙값 대비) vs 여의나루+여의도 핫스팟 30분 하차, **역별** 랙 5~60분 교차상관(노선 추정치와 대조) → 최적 랙·r 을 오차표 옆 "선행지표 검증" 절로
- [ ] **9/6~7: 도착 30분 예측 데모** — 검증된 역별 랙으로 9/5 오후를 재구성: "피더 신호로 도착을 실제보다 N분 먼저 맞혔다" 표 1장 (제출물: 검증 결과 + 관리자 뷰 확장안, 2027판 α 관측 후보)

### Task 2: 야간 CCTV 테스트 판정 + 캘리브레이션 (8/30, 사용자 절반) — 오차 예산 3순위(조건부)

**Files:**
- Read: `logs/night_test_20260829.log`, `data/live/cctv_20260829.jsonl`
- Modify: `data/derived/topis_yeouido_cams.json` (5대 `roi`·`roi_m2`), `src/collector_cctv.py` `LOW_LIGHT` 임계

- [x] **Step 1: 요약 실행** (8/29 21:00 자동, `logs/night_test_20260829.log`) — 23대 60분 1,380건, ok 95~100%, 밝기 중앙값 56~98(저조도<40 **0대**), count 중앙 1~14, 등급 대부분 여유, 플래그 count_vs_occ 4대(63빌딩·국회·노량진수산·마포대교북단), no frame 산발 17건. `benchmark-crowd-systems.md` §5 기록
- [x] **Step 2: 임계 판단 (8/30)** — 야간 실측 밝기 중앙 56~98로 저조도(<40) 0대 → `LOW_LIGHT=40` 유지. 계획의 '하위 1/4분위(≈70)' 규칙은 카메라 1/4을 근거 없이 저조도 처리하게 되어 미적용
- [x] **Step 3: ROI 기입 (8/31)** — 프레임 5장 캡처 → AI가 ROI 다각형 제안(통제 시 보행로가 될 차도), 사용자 검수·조정(39캠 좌하 -40px). 면적은 지도 실측 대신 **추정**: 교량 공식 제원(마포 25m·원효 20m)/OSM lanes × 가시 구간(원근 추정), ±35%·`roi_measured: estimated` 표기. 밀도 등급 반 계단 오차 수준
- [x] **Step 4: 검증 (8/31)** — 5캠 `--once`: 전부 `calibrated: true`·density 산출(주간 차량은 DM-Count가 안 세어 count≈0 정상). pytest 통과. 남은 것: 9/4 리허설 야간 실화면으로 ROI 타당성 재확인
- [x] **HD 업그레이드 (8/31)** — UTIC 원본 720p 9대 발견(경찰 CCTV 조사 부산물, TOPIS와 동일 카메라). 수집기 HD 우선·SD 폴백, ROI `roi_frame` 스케일 변환. 스모크: 331·192 hd / 39 sd 폴백, calibrated 유지

### Task 3: 대시보드 UI 개선 ③④ (8/30, 사용자 디자인 판단 후)

**Files:**
- Modify: `docs/index.html` (카피·참조선·격자 섹션)

**Interfaces:**
- Consumes: `exit_forecast_2026.json.exits[st][h].load/load_lo/load_hi`, `outflow_by_year`
- Produces: `#grid` 섹션(시간×출구 등급), 숫자 옆 "평소 최대의 N%", 차트 2025 참조선

- [x] **Step 1: 설계 제시 → 승인** (8/31) — 격자 = CCTV와 오프라인 플랜 사이, 열별 최저 1곳 '추천' 테두리·최고 1곳 '피하기'(상위2 대신 1로 단순화), 카피 "평소 최대의 N%"
- [x] **Step 2: 구현** — `grid(ex,hours)` 신설(등급 색 `color-mix` 토큰 재사용, 통제 셀 점선), 보드 설명줄에 % 카피, 차트에 2025 실측 점선(`outflow_by_year`, 라이브에 필드 없으면 자동 생략)
- [x] **Step 3: 검증** — `node --check` OK, 헤드리스 1440 다크·520 캡처: 격자만 내부 가로 스크롤, 본문 스크롤 없음, 현재 시간 열 강조
- [x] **Step 4: 커밋·push** — Pages 반영 확인은 배포 수 분 후

### Task 4: 귀가 내비 챗봇 프롬프트 (8/30~31)

**Files:**
- Create: `prompt/exit_navi.md` (시스템 프롬프트), `prompt/test_queries.md` (질의 10 + 기대 답)
- Create: `src/build_prompt.py` (사전표·통제 규칙을 프롬프트 변수로 주입)

**Interfaces:**
- Consumes: `exit_forecast_2026.json` (ranking_by_hour, closures, direction_share), `nowcast` PLANS 텍스트(`docs/index.html` PLANS 상수와 동일 문장)
- Produces: `prompt/exit_navi.generated.md` — 편집기 항목 5·6 증빙, 영상 시연

- [x] **Step 1: 설계 제시 → 승인** (8/31) — 사전표·통제·방향 매핑·출구번호('22 표기)·도보 주입, 출력 형식·금지 규칙 강제
- [x] (8/31 반영) 출구 번호 안내 — 프롬프트 '역 출구 번호' 절에 2022 기준 경고와 함께 포함
- [x] **Step 2: `build_prompt.py`** — 사전표→마크다운 표·순위·도보(모델 travel_min) 주입, 생성 파일 assert(7출구×5시간·통제). 데이터 갱신 시 재실행만 하면 프롬프트 동기화
- [x] **Step 3: 질의 10건 테스트** — 방향 5·시각 함정 2·범위 밖 2·날씨 1. 초기 결함 1건(급행 정차역 미구분) 발견→템플릿 수정. 10/10, `prompt/test_queries.md`
- [x] **Step 4: 커밋** (8/31)

### Task 5: 가상 설문 1,000건 + 분석 (8/31~9/1)

**Files:**
- Create: `survey/generate_survey.py` (규칙 기반 생성, 시드 고정), `survey/survey_2026.csv`, `survey/analyze.py`, `survey/charts/*.png` 3장, `survey/README.md`

**Interfaces:**
- Consumes: `baseline.json` 방향 분포, `feeder_origin.json` 출발지 비중, `move_202509` 성연령(20·30대 여성 최다)
- Produces: 편집기 항목 3 증빙. 문항: 귀가 소요·불편 순위(통신·화장실·안내·대기)·정보 채널·희망 기능

- [ ] **Step 1: 설계 제시 → 승인** — 문항 12개, 페르소나 분포(성연령·출발지·수단)를 실데이터 비율로 캘리브레이션, 응답 상관 규칙 3개(서쪽 귀가 ↔ 대기 불만 ↑ 등), 생성은 규칙+난수(LLM 생성 아님 — 재현성)
- [ ] (8/31 추가) 연령별 역 선호 상관: 1020↔여의나루, 30대+↔여의도 (지오비전 '22 근거)
- [ ] **Step 2: 생성 스크립트** — `python survey/generate_survey.py --n 1000 --seed 26` → CSV 1,000행. 검증: 성별·출발지 분포가 목표 ±2%p (스크립트가 출력)
- [ ] **Step 3: 분석 3장** — 불편 순위 막대 · 귀가 방향×대기 불만 히트맵 · 희망 기능 순위. `python survey/analyze.py`
- [ ] **Step 4: README에 생성 규칙·한계("가상 데이터, 실태 아님") 명시. 커밋**

### Task 6: evaluate.py + 오차표 틀 (9/1~2)

**Files:**
- Create: `src/evaluate.py`, `data/derived/eval_YYYYMMDD.json`, `docs/eval.md`(표)

**Interfaces:**
- Consumes: `data/live/api_YYYYMMDD.jsonl`(도시데이터 실측 인구·12h 예측 스냅샷), `forecast_latest.json` 시각별 사본(publish 시 `data/live/forecast_history/HHMM.json`으로 저장 — publish.py 1줄 추가), `exit_forecast_2026.json`
- Produces: 시간대별 표: 우리 p50·밴드 / 서울시 12h / 실측 인구, MAPE, 등급 적중률, 밴드 포함률

- [ ] **Step 1: publish.py에 이력 저장 1줄** — `forecast_history/` 디렉터리. 검증: 로컬 1회 실행 후 파일 생성
- [ ] **Step 2: evaluate.py** — 같은 시각 매칭(5분 내), 지표 계산, 마크다운 표 출력. 검증: 8/29 로그(7건)로 돌려 표가 나오는지
- [ ] **Step 3: 우천 연기 분기** — `--fallback rehearsal` 로 9/4 로그를 쓰는 옵션
- [ ] **Step 4: 커밋**

### Task 7: 드라이런 + 중간 정리 5장 (9/2~3)

**Files:**
- Create: `submission/midterm_5pages.md` (9/4 오전 피드백용)
- Read: `logs/*.log`

- [ ] **Step 1: 9/2 저녁 `./run_all.sh` 30분 드라이런** — api·cctv·nowcast·publish 로그 4개 에러 0, Pages `latest.json` 갱신 시각 확인. 문제는 hotfix 후 재실행
- [ ] **Step 2: 중간 정리 5장** — 문제·데이터·모델·결과(사전표 화면)·검증 계획. 스펙 §2 표에서 항목 2·4·6·8·9 발췌
- [ ] **Step 3: 커밋·push. 9/4 오전 피드백 메모는 `submission/feedback_0904.md`**

### Task 8: 9/4 전야제 리허설 런북 (9/4 18:00~22:00)

**Files:**
- Create: `submission/runbook.md` (9/4·9/5 공용)

- [ ] **Step 1: 런북 작성** — 시간표(17:30 전원·뚜껑·`./run_all.sh`, 18:00 첫 publish 확인, 20:00 show_end 기입 담당, 22:00 종료), 실패 대안(맥 재시작 → `run_all.sh` 재실행, API 오류 → 페이지 localStorage 유지, Pages 지연 → 로컬 서버 시연), 확인 명령 목록
- [ ] **Step 2: 실행** — 로그 4개, `cctv_summary.py` 야간 요약, α 로그 스크린샷
- [ ] **Step 3: 판정** — 스펙 §4 "9/4 전야제" 항목 체크. hotfix는 `pytest` 통과 후만

### Task 9: 9/5 본번 (12:00~24:00)

- [ ] **Step 1: 11:30 준비** — 전원·뚜껑·네트워크·`git pull`·`pytest`·`./run_all.sh`
- [ ] **Step 2: 매시 확인** — Pages 기준 시각 ≤15분, 오류 로그, 도시데이터 α 값. 20:00~21:40 통제 실물 확인해 `closures` 규칙과 다르면 메모
- [ ] **Step 3 (오차 예산 5순위, 비용 0 — 가장 큰 타이밍 레버): 쇼 종료 실제 시각 기입** — 마지막 불꽃 직후 `echo HH:MM > data/live/show_end.txt`. 담당 1명 지정, 20:55부터 알람. 다음 nowcast 틱(≤5분)에 `show_end_source: file` 확인
- [ ] **Step 4: 24:00 종료·백업** — `data/live/*_20260905.jsonl` 커밋·push

### Task 10: 오차표·영상·편집기 초안 (9/6~7)

**Files:**
- Create: `submission/editor_draft.md`(9항목), `submission/video_script.md`, `docs/eval.md`

- [ ] **Step 1: `evaluate.py --date 20260905`** → 표. 우천 시 `--fallback rehearsal`
- [ ] (8/31 추가) 생활인구(OA-14991 여의도동 시간대) 3자 대조 절 — KT 기반이라 반독립임을 표기. 기획서에 London exit-only 어휘·행안부 인파시스템 보완관계 문단 (§benchmark §7)
- [ ] **Step 2: 편집기 9항목 초안** — 스펙 §2 표 순서대로. 항목 5·6은 `benchmark-crowd-systems.md` §6·커밋 로그에서 발췌
- [ ] **Step 3: 영상 3분 스크립트** — 0:00 문제(실적 표) · 0:40 데이터·모델 · 1:30 페이지 시연(20→21→22시, 무정차 행) · 2:20 9/5 실측 vs 예측 · 2:50 한화 적용. 녹화·MP4 ≤20MB
- [ ] **Step 4: 추가자료 5개 목록·용량 확인. Release 자산 업로드(OD zip)**

### Task 11: 제출 (9/8)

- [ ] **Step 1: 오전 최종 점검** — Pages 링크 열림, 상태 4종 중 현재 상태 문구 정상, `pytest` 통과, 스펙 §4 체크리스트 전부 ✓
- [ ] **Step 2: 편집기 입력·영상 업로드·추가자료 첨부** — 18:00까지
- [ ] **Step 3: 20:00 제출 · 스크린샷 · `/dev-end`**

---

## 백로그 (프리즈 후·제출 후)

- stcis.go.kr 교통카드 빅데이터 — 신길 1호선(코레일) 승차 확보 리드. 접근 신청 절차 확인 필요. 확보 시 exit_shares 입력 데이터만 교체(코드 불변)

## Self-Review

- 스펙 §2 항목 1~9·추가자료 → Task 4·5·6·10·11에 대응. 항목 1(팀)은 사용자 입력.
- 스펙 §4 페이지 DoD → Task 3·7; 모델·데이터 DoD → Task 1·2·6; 당일 DoD → Task 8·9; 제출물 DoD → Task 10·11.
- 플레이스홀더: Task 4·5의 세부 문항·프롬프트 본문은 "설계 제시 → 승인" 단계에서 확정한다(approval-gate). 그 외 없음.
- 이름 일관성: `exit_forecast_2026.json` 필드명은 스펙 §3과 동일. `show_end.txt` 경로 `data/live/`.
