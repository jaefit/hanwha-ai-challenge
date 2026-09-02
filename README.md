# AI 솔루션 챌린지 — 과제 03

한화 신입사원 AI 실습 과제. 5개 과제 중 **03 「고객 페인포인트 해결」** 을 선택해 수행한 작업 기록이다.

> 2026-08-29부터 **공개 저장소**다. 배포받은 원본 과제 자료(PDF·PNG)는 사내 자료라 저장소에 넣지 않는다(히스토리에서도 제거). 판독 결과만 `BRIEF.md`에 요약했다.

## 현재 상태 (2026-09-02)

**주제: 서울세계불꽃축제(9/5) 관람객 혼잡·귀가 내비.** 9/8(화) 20:00 제출(마감 22:00). 기준 문서는 [topic-fireworks.md](topic-fireworks.md), 실행 계획은 [플랜](docs/superpowers/plans/2026-08-29-submission-plan.md)이다.

행사 사흘 전이다. **예측 모델·수집 파이프라인·공개 대시보드는 돌아가는 상태**이고, 남은 일은 당일 운영(9/4 리허설 · 9/5 실전)과 그 결과 정리다. **코드 동결 9/4 12:00** — 이후 `src/`·`docs/index.html` 변경은 hotfix만.

### 만들어 둔 것

| 산출물 | 위치 | 무엇 |
|---|---|---|
| **대시보드** | [Pages](https://jaefit.github.io/hanwha-ai-challenge/) · `docs/index.html` | 출구 랭킹 · 지도(혼잡장 + 혼잡 회피 보행 경로) · CCTV 등급 · 오프라인 플랜. 5분 갱신 |
| 팀 보고서 | [report.html](https://jaefit.github.io/hanwha-ai-challenge/report.html) | 모델 수식(KaTeX)·실측표·외부 검증. 쉬운 버전 [report_easy.html](https://jaefit.github.io/hanwha-ai-challenge/report_easy.html) |
| 피치 덱 | [deck.html](https://jaefit.github.io/hanwha-ai-challenge/deck.html) | 발표용 12장 |
| 예측 모델 | `src/nowcast.py` 외 | 4층(L1 베이스라인 → L2 α 나우캐스트 → L3 출구 배정 → L4 큐). 백테스트 `src/backtest.py` |
| 수집·발행 | `run_all.sh` | 프로세스 3개 — `collector_api.py`(서울시 도시데이터 5분 + 실시간 지하철 도착 17~23시 + 피더 12~19시) · `collector_cctv.py`(TOPIS 23대, 기본 60초) · `nowcast`→`publish` 5분 루프. 워치독·`.env` 키 점검 포함 |
| 혼잡장 | `docs/app/field.js` | CCTV 23대 + 서울시 구역등급을 **가우시안 과정 회귀**로 하나의 면에. 신뢰도는 배제가 아니라 관측 노이즈 σ 로 |
| 보행 경로탐색 | `routing/` | OSM 보행망(노드 9,219) 위 A*, 비용 = 거리 × (1 + 1.25 × 혼잡위험) |
| 자체 적대적 검증 | [redteam-20260901.md](redteam-20260901.md) | 결함 18건 + 조치 현황. **05의 결함 대장은 이 문서다** |
| 회귀 테스트 | `tests/` | **45건**(2026-09-02 기준) — `.venv/bin/python -m pytest tests -q` |

### 이전 상태 (2026-08-29, 기록)

**주제 확정 — 서울세계불꽃축제(9/5) 관람객 혼잡·귀가 내비.** 마감 9/8(화) 22:00. 기준 문서는 `topic-fireworks.md`.
이 시점 산출물은 사전 예측표(`backtrack.py`)와 대시보드 프로토타입까지였다. 아래 "탐색 단계"는 그보다 하루 전 기록이다.

### 이전 상태 (2026-08-28, 기록)

**주제는 아직 확정되지 않았다.** 후보를 넓게 벌려놓고 하나씩 근거를 대보는 탐색 단계다.
지금까지 세 차례에 걸쳐 페인포인트 후보 20개를 돌렸다.

| 차수 | 한 일 | 결과 |
|---|---|---|
| 1차 | 방산 5 · 금융 5 · 교차 1 = 후보 11개 발굴 | D5(취준생·대중)는 과제 01 영역이라 탈락 |
| 2차 | 니즈 증거를 공표 자료로 재검증해 A~C 등급 부여 | 순위가 뒤집혔다. F2 가 "03 원문에 가장 충실"에서 C등급 7위로 내려가고 F3 가 1위로 올라옴 |
| 3차 | 고객·접점을 더 잘게 쪼개 후보 9개 추가 (D6~D9 · F6~F10) | F6 · D6 · F7 이 F3 위로 올라와 **F3 는 4위가 됨** |

**F3(ETF 구성 불투명)만 산출물 시제품까지 가봤다.** 실제로 만들어봐야 실데이터로 근거를
채울 수 있는지 확인되기 때문에 먼저 뚫어본 것이고, 최종 선택이라는 뜻이 아니다.
현재 최신 순위 1~3위인 **F6**(해외주식 양도소득세) · **D6**(부품단종) · **F7**(설명서 난해)은
아직 시제품을 만들어보지 않았다.

F3 을 뚫어보다 나온 발견: `PLUS K방산` ETF 는 이름과 달리 **한화 3사가 51.04%** 를 차지한다.
페인포인트의 실증 사례이면서 동시에 자사 상품이라 발표 소재로는 강하다.

## 읽는 순서

| 순서 | 문서 | 내용 |
|---|---|---|
| 0 | [topic-fireworks.md](topic-fireworks.md) | **확정 주제.** 페인포인트 실적, 데이터 검증, 4층 모델, CCTV 방법, 일정. **여기부터 읽는다.** |
| 1 | [BRIEF.md](BRIEF.md) | 과제 정의. 5개 과제 요약, 평가표 100점 배분, 제출 형식 |
| 2 | [business-research.md](business-research.md) | 방산·금융 사업영역 조사와 페인포인트 후보 도출 |
| 3 | [painpoint-analysis.md](painpoint-analysis.md) | 페인포인트 전수 분석. 방산 5건 · 금융 5건 · 교차 1건을 증거 기반으로 순위화 |
| 4 | [spec-f3-etf.md](spec-f3-etf.md) | (보류) F3 산출물 스펙. 요구사항 P0 5건과 배점 매핑 |
| 5 | [deliverable-etf-cards.md](deliverable-etf-cards.md) | (보류) ETF 해부 카드 3장, 전부 공시 실데이터 |
| 6 | [status-update.md](status-update.md) | (보류) 8/27 시점 중간보고. 주제 확정 전 기록 |
| 7 | [benchmark-crowd-systems.md](benchmark-crowd-systems.md) | 타 혼잡 예측 시스템 11건 대조 · 채택 개선 |
| 8 | [docs/superpowers/specs/2026-08-29-submission-design.md](docs/superpowers/specs/2026-08-29-submission-design.md) | **제출 스펙** — 편집기 9항목 매핑 · 완료 정의 · 범위 밖 · 리스크 |
| 9 | [docs/superpowers/plans/2026-08-29-submission-plan.md](docs/superpowers/plans/2026-08-29-submission-plan.md) | **실행 계획** 8/29→9/8 태스크 11개 · 런북 |
| 10 | [redteam-20260901.md](redteam-20260901.md) | **자체 적대적 검증** 결함 18건 · 조치 현황 · 미조치 판단 근거 |
| 11 | [routing/README.md](routing/README.md) | 보행 네트워크(OSM) · 경로탐색 · 핸드오프 편입 기록 |
| 12 | [handoff/README.md](handoff/README.md) | 디자인 핸드오프 — 사실·브랜드·화면 구조·데이터 계약 (8/29 기준 + 이후 변경) |
| 13 | `tests/` | 모델 불변식 pytest **45건**(2026-09-02) — `.venv/bin/python -m pytest tests -q`. `tests/field_spec.mjs` 는 배포 중인 `docs/app/field.js` 를 node 로 직접 검증한다 |
| 14 | `src/backtest.py` → `data/derived/backtest.json` | 모델 백테스트 — 2024·2025 실측 시간대 승차. **A in-sample 승차오차 0.245/0.214**(2024/2025)·등급적중 82%/100%, **B cross-year(2026 조건) 0.420/0.438**·76%/88%. 생성 2026-08-30 (`52ff59a` 재생성분) |

## 원본 자료

배포받은 과제 안내 PDF 6쪽과 쪽별 PNG는 **저장소 밖**(로컬 `../05_ai_challenge_assignment_local/`)에 둔다. 사내 배포자료라 공개 저장소에 올리지 않는다.
PDF 텍스트가 글리프로 박혀 있어 복사·검색이 되지 않는다. 판독은 PNG를 보고 했고, 그 결과를 정리한 것이 `BRIEF.md`다.

## 돌려보기

```bash
.venv/bin/python -m pytest tests -q     # 회귀 45건
.venv/bin/python src/nowcast.py         # 예측 1회 → data/live/forecast_latest.json
./run_all.sh                            # 수집기 3종 + 5분 발행 루프 (당일 운영)
./tools/demo.sh                         # 가상 관측으로 대시보드 미리보기 → 127.0.0.1:8080
```

`tools/demo.sh` 는 축제 저녁 수준의 **가상값**을 `$TMPDIR` 사본에 주입해 혼잡장이 어떻게 보이는지만 확인한다. 저장소는 건드리지 않는다. **주입값은 실측이 아니므로 보고서·제출물에 인용하지 않는다.**

## 다음 할 일 (2026-09-02 갱신)

| 날짜 | 할 일 |
|---|---|
| 9/2(수) 저녁 | **T7 드라이런** — `run_all.sh` 30분. 새 워치독이 실제 수집기와 도는 첫 실행이다 |
| 9/3(목) | 중간 정리 5장 `submission/midterm_5pages.md` |
| 9/4(금) | 오전 오프라인 피드백 · **12:00 코드 동결** · 런북 작성 · 저녁 전야제 리허설 수집 |
| 9/5(토) | 실전 12~24시. 쇼 종료 실시각 기입 담당 1명 |
| 9/6~7 | `evaluate.py` 오차표 · 영상 3분 · 편집기 9항목 초안 |
| 9/8(화) | 최종 점검 → 18:00 업로드 → **20:00 제출** |

동결 전 결정 2건이 남아 있다 — **C1 α 밴드 클램프**(관측 20건에 밴드가 ±5%로 좁아지는데 백테스트 오차는 ±42%)와 **전야제 합격선**(1.9배 미달 시 행동 미정의). 근거는 `redteam-20260901.md` §C1 과 `topic-fireworks.md` §9.

### 이전 (2026-08-28 기록)

- **주제 확정** — 최신 순위 1~3위(F6 · D6 · F7)와 시제품이 나와 있는 F3 를 놓고 결정한다.
  판단 기준은 "실데이터로 산출물이 나오는가" 하나다. 배점 50점이 거기 걸려 있다
- 고른 주제로 산출물 제작 — F3 외에는 아직 시제품이 없다
- 프롬프트 설계 문서 작성 — 평가 배점 25점에 직결된다
- 가상 설문 1,000건 생성 여부 확정 후 분석
- 마감일·제출 형식·개인/팀 여부 확인 (전부 미확정)
