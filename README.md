# 불꽃배웅 — 눈부신 밤의 끝, 집으로 가는 길까지.

서울세계불꽃축제(2026-09-05) 관람객 **귀가 내비**. 불꽃이 끝나는 순간 백만 명이 움직이는데, 공원에서 가장 가까운 여의나루역은 그 시간에 닫혀 있고 지도앱은 그 역으로 안내한다. 이 제품은 한 가지에 답한다 — **지금, 어디로 나갈까.**

한화 신입사원 AI 솔루션 챌린지 **과제 03 「고객 페인포인트 해결」** 제출물이다. 2026-08-29부터 공개 저장소이며, 배포받은 원본 과제 자료(사내)는 저장소 밖에 둔다.

## 바로 보기

| 링크 | 내용 |
| :-- | :-- |
| **[▶ 관람객 화면](https://jaefit.github.io/hanwha-ai-challenge/go.html)** | 열면 답이 먼저 — 가장 빨리 닿는 출구 · 걸어서 N분 · 등급 · 시간대 스크럽. 묻는 것 0 |
| **[운영 대시보드](https://jaefit.github.io/hanwha-ai-challenge/)** | 출구 상태판 · 유출 예측 · CCTV 23대 · 혼잡장(GP 회귀) · 오프라인 카드 |
| **[9/5 22:06 재생](https://jaefit.github.io/hanwha-ai-challenge/index.html?at=20260905T2206)** · [관람객](https://jaefit.github.io/hanwha-ai-challenge/go.html?at=20260905T2206) | 실전 당일 발행분을 그 시각 그대로. 배너 칩으로 20:05 → 23:02 여섯 시점 이동 |
| **[피치 덱](https://jaefit.github.io/hanwha-ai-challenge/deck.html)** | 12장 · 5분 · 문제 → 화면 실물 → 3층 해부 → 검증 → 실전 결과. `n` 노트, `t` 시계, `f` 전체화면 |
| [팀 보고서](https://jaefit.github.io/hanwha-ai-challenge/report.html) · [쉬운 버전](https://jaefit.github.io/hanwha-ai-challenge/report_easy.html) | 모델 수식·실측표·외부 검증·적대적 검증 / 같은 내용을 수식 없이 |

행사가 끝난 뒤 라이브 화면은 사전 예측표만 보여준다. 실물은 위 **재생** 링크로 본다.

## 상태 (2026-09-08 제출)

**9/5 실전 운전 완료 → 채점 → 제출 단계.** 마감 9/8(화) 22:00.

| 실전 결과 (2026-09-05, `src/evaluate.py` 산출) | 값 |
| :-- | :-- |
| 발행 스냅샷 | 287개 (5분 간격, 12:00~24:00 자동) |
| 수집 | 서울시 API 9,147건 · CCTV 판독 33,120건 · 재기동 1회(계획된 간격 전환) · 크래시 0 |
| 오늘 배율 α | 최종 0.91 [0.86~0.97] (사전 1.00, 최고 1.36) |
| 유출 피크 시각 | **22시 일치** · 형태 상관 r 0.66 |
| 쇼 종료 실시각 | 21:27 현장 기입 (계획 21:10) — 한 줄 입력으로 유출 곡선 전체가 밀렸다 |
| 서울시 12시간 예측 대비 | 같은 도시데이터의 선행 예측은 저녁 피크를 9배 낮게 봤다 (MAPE 0.56) |
| **놓친 것** | 23시 꼬리 — 실측은 피크의 92%, 예측은 41%. 여의나루 조기 무정차(18:10~22:05)와 겹침. 결함 대장 M15 |

적대적 검증 7회차, 결함 **39건**(치명 6 · 높음 10 · 중간 16 · 낮음 7) — 치명·높음 전부 조치. 회귀 테스트 **122건** 통과. 커밋 169개(8/28~).

## 만든 것

| 산출물 | 위치 | 무엇 |
| :-- | :-- | :-- |
| **관람객 화면** | `docs/go.html` | 풀블리드 지도 + 바텀시트. 출발지는 위치 권한(거절·여의도 밖이면 이벤트광장 + 핀 드래그), 1위 = 도보+대기 시간, 경로 = 보행망 A*(거리가 아니라 **시간**으로 고른다). 판정 `docs/app/board.js`, 혼잡장·속도식 `docs/app/field.js` 공용 |
| **운영 대시보드** | `docs/index.html` | 출구 7곳 × 시간대 부하율, 유출 예측(막대 = 우리, 회색 = 2년 평균, 점 = 서울시 12h), CCTV 등급, 혼잡장, 오프라인 카드 |
| **발행 스냅샷 재생** | `docs/app/replay.js` · `docs/data/replay/20260905/` | `?at=YYYYMMDDTHHMM` — 그 시각 발행분을 그대로. 시계 고정, 자동 갱신·폴백 끔. 6개 시점 |
| 예측 엔진 | `src/nowcast.py` 외 | 사전층(작년 실측 출구 비중 × 도착 형태) → 당일층(α 격자 61점 데이터동화, 5분) → 출구 배정 → 큐. 백테스트 `src/backtest.py` |
| 수집·발행 | `run_all.sh` | `collector_api.py`(도시데이터·실시간 지하철·피더) · `collector_cctv.py`(TOPIS 23대, 영상 저장 없이 집계만) · nowcast→publish 5분 루프 · 워치독 |
| 혼잡장 | `docs/app/field.js` | CCTV 23대 + 서울시 구역등급을 가우시안 과정 회귀로 한 면에. 못 본 곳은 흐리게 |
| 보행 경로탐색 | `routing/` | OSM 보행망 A*, 비용 = 거리 × (1 + 1.25 × 혼잡위험). 9/5 실측 장에서 36건 중 11건 경로가 바뀜(`tools/route_real.mjs`) |
| 채점 | `src/evaluate.py` → `data/derived/eval_20260905.json` | 서울시 12h 기준선 · α 추이 · 지하철 형태 상관 · 꼬리 비율 |
| 피치 덱 | `docs/deck.html` + `docs/deck/*.json` | 12장(Claude Design 「Pitch Deck v2」 원안). 숫자는 전부 `tools/deck_data.py` 가 git·tests·대장·평가 파일에서 셈 — 손 숫자 없음, `tests/test_deck.py` 가 대조 |
| 소개 영상 | `video/` | 대본 12블록 · 녹화본(3:30, 프레임 그대로) 위에 TTS·자막을 얹는 파이프라인. 영상 파일은 레포 밖 |
| 결함 대장 | [redteam-20260901.md](redteam-20260901.md) | 7회차 39건. 다른 모델(Codex) 교차검증 포함. **05의 결함은 여기에만 적는다** |
| 회귀 테스트 | `tests/` | 122건 — `.venv/bin/python -m pytest tests -q`. `field_spec.mjs` 는 배포 중인 `field.js` 를 node 로 직접 검증 |

## 읽는 순서

| 순서 | 문서 | 내용 |
| :-- | :-- | :-- |
| 0 | [topic-fireworks.md](topic-fireworks.md) | **주제 문서.** 페인포인트 실적, 데이터 검증, 모델, CCTV 방법, 일정 |
| 1 | [BRIEF.md](BRIEF.md) | 과제 정의, 평가표 100점 배분, 제출 형식 |
| 2 | [docs/superpowers/specs/2026-08-29-submission-design.md](docs/superpowers/specs/2026-08-29-submission-design.md) | 제출 스펙 — 편집기 9항목 매핑 · 완료 정의 · 리스크 |
| 3 | [docs/superpowers/plans/2026-08-29-submission-plan.md](docs/superpowers/plans/2026-08-29-submission-plan.md) | 실행 계획 8/29 → 9/8, 태스크 14개(체크박스가 진실) |
| 4 | [redteam-20260901.md](redteam-20260901.md) | 적대적 검증 7회차 · 조치 현황 · 열린 질문 |
| 5 | [runbook_20260904.md](runbook_20260904.md) | 9/4 17:08 → 9/6 01:01 무중단 운전 런북 |
| 6 | [benchmark-crowd-systems.md](benchmark-crowd-systems.md) | 타 혼잡 예측 시스템 11건 대조 · 채택 개선 |
| 7 | [routing/README.md](routing/README.md) | 보행망·경로탐색·핸드오프 편입 기록 |
| 8 | [handoff/README.md](handoff/README.md) | 디자인 핸드오프 — 사실·브랜드·화면 구조·데이터 계약 |
| 9 | [video/README.md](video/README.md) | 소개 영상 대본·빌드 |
| — | [archive/](archive/) | 주제 확정 전 탐색 기록(방산·금융 후보 20개, F3 ETF 시제품). 보류·보존 |

## 저장소 구조

```
docs/        GitHub Pages — go.html · index.html · deck.html · report*.html · app/ · data/ · deck/
src/         수집기 2 · 나우캐스트 · 발행 · 백테스트 · 채점
tools/       덱 데이터 exporter · 재생 스냅샷 빌더 · 경로 스파이크 · 데모
tests/       pytest 122 + node spec
data/        derived/(요약본, 커밋) · live/(당일 런타임, 레포 밖) · raw/(재다운로드)
routing/     보행망 다운로드·그래프
prompt/      귀가 내비 챗봇 프롬프트 팩
handoff/     디자인 핸드오프(팀원)
video/       소개 영상 대본·빌드 스크립트
archive/     주제 확정 전 문서
```

## 돌려보기

```bash
.venv/bin/python -m pytest tests -q          # 회귀 122건
.venv/bin/python src/nowcast.py --out /tmp/fc.json   # 예측 1회 (라이브 파일 안 건드림)
./run_all.sh                                 # 수집기 + 5분 발행 루프 (당일 운영, .env 키 필요)
./tools/demo.sh                              # 가상 관측으로 대시보드 미리보기 → 127.0.0.1:8080
.venv/bin/python tools/deck_data.py          # 덱 숫자 재생성 (커밋·테스트 수가 바뀌면)
video/build/run.sh 녹화.mp4                  # 소개 영상: 전사 → TTS → 자막 → mp4
```

`tools/demo.sh` 의 주입값은 실측이 아니다 — 보고서·제출물에 인용하지 않는다. 당일 수집 원본(`data/live/*.jsonl`, 78MB)은 맥 한 대에만 있고 백업하지 않기로 했다(9/6). 재생 스냅샷 6개는 레포에 있다.

## 기록

- **8/27~28** 방산·금융 페인포인트 후보 20개 탐색, F3(ETF 구성 불투명)만 시제품까지. `PLUS K방산` ETF 의 한화 3사 51.04% 발견. → `archive/`
- **8/29** 주제 확정(불꽃축제 귀가 내비), 공개 전환, 공공 데이터 수집. **8/31** 예측 엔진·백테스트·대시보드 v1. **9/1** 적대적 검증 1회차·혼잡장·피치덱. **9/2~3** 드라이런·워치독 고장 주입·Codex 교차검증·테스트런.
- **9/4 17:08 → 9/6 01:01** 32시간 무중단 운전(전야제 리허설 + 본번). 당일 hotfix 4건. **9/5** 제품명 「불꽃배웅」.
- **9/6** 실전 채점·덱 v2 14장·발행 스냅샷 재생. **9/7** 소개 영상 녹화·TTS·자막. **9/8** 제출.
