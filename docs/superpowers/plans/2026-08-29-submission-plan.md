# 제출까지 실행 계획 (8/29 → 9/8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 §4 완료 정의를 9/8 20:00 전에 전부 체크한다.

**Architecture:** 사전 예측(backtrack) 위에 당일 레이어(nowcast)를 얹는 현 구조를 바꾸지 않는다. 남은 일은 (a) 검증 뼈대, (b) 미착수 산출물 3개, (c) 당일 운영 런북, (d) 제출 패키징.

**Tech Stack:** Python 3.14 venv(`.venv`), pytest, 정적 HTML(MapLibre), GitHub Pages, zsh 스크립트.

**Spec:** `docs/superpowers/specs/2026-08-29-submission-design.md`

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

### Task 2: 야간 CCTV 테스트 판정 + 캘리브레이션 (8/30, 사용자 절반)

**Files:**
- Read: `logs/night_test_20260829.log`, `data/live/cctv_20260829.jsonl`
- Modify: `data/derived/topis_yeouido_cams.json` (5대 `roi`·`roi_m2`), `src/collector_cctv.py` `LOW_LIGHT` 임계

- [ ] **Step 1: 요약 실행** — `.venv/bin/python src/cctv_summary.py --from 20:00 --minutes 60` → 저조도 카메라 수, count 중앙값, 플래그 분포 기록(`benchmark-crowd-systems.md` §5 에 3줄)
- [ ] **Step 2: 임계 조정** — 밝기 중앙값 분포 보고 `LOW_LIGHT` 를 하위 1/4 분위로. 이유를 코드 주석에
- [ ] **Step 3 (사용자): ROI 측정** — `.venv/bin/python src/cam_calib.py --cams 192,725,310,331,39 --out ~/cam_calib` → 그림 보고 폴리곤 좌표, 지도에서 면적(m²) → cams.json 기입 → 끝나면 `rm -r ~/cam_calib`
- [ ] **Step 4: 검증** — `.venv/bin/python src/collector_cctv.py --once --cams 192` 레코드에 `calibrated: true`, `density` 숫자. `pytest` 통과. 커밋

### Task 3: 대시보드 UI 개선 ③④ (8/30, 사용자 디자인 판단 후)

**Files:**
- Modify: `docs/index.html` (카피·참조선·격자 섹션)

**Interfaces:**
- Consumes: `exit_forecast_2026.json.exits[st][h].load/load_lo/load_hi`, `outflow_by_year`
- Produces: `#grid` 섹션(시간×출구 등급), 숫자 옆 "평소 최대의 N%", 차트 2025 참조선

- [ ] **Step 1: 설계 제시(bounded) → 승인** — 격자 위치(오프라인 플랜 위), 추천 상위 2·피하기 하위 1 태그, 카피 문구
- [ ] **Step 2: 구현** — `render()`에서 `hours × EXITS` 격자 생성, `data-g` 등급색 재사용. 카피는 `.num` 아래 small
- [ ] **Step 3: 검증** — 헤드리스 캡처 1440 다크/라이트 + 520 (swiftshader 플래그), `node --check`. 가로 스크롤 없음 확인
- [ ] **Step 4: 커밋·push → Pages 확인**

### Task 4: 귀가 내비 챗봇 프롬프트 (8/30~31)

**Files:**
- Create: `prompt/exit_navi.md` (시스템 프롬프트), `prompt/test_queries.md` (질의 10 + 기대 답)
- Create: `src/build_prompt.py` (사전표·통제 규칙을 프롬프트 변수로 주입)

**Interfaces:**
- Consumes: `exit_forecast_2026.json` (ranking_by_hour, closures, direction_share), `nowcast` PLANS 텍스트(`docs/index.html` PLANS 상수와 동일 문장)
- Produces: `prompt/exit_navi.generated.md` — 편집기 항목 5·6 증빙, 영상 시연

- [ ] **Step 1: 설계 제시 → 승인** — 입력(위치 5구역·목적지 회랑·시각), 출력 형식(출구 1·2·3 + 도보 분 + 통제 주석 + 근거 한 줄), 금지(모르는 시간대·역 추측 금지)
- [ ] **Step 2: `build_prompt.py`** — JSON 읽어 표를 마크다운으로 렌더 → 프롬프트 템플릿에 삽입. 검증: 생성 파일에 7출구×5시간 표 존재
- [ ] **Step 3: 질의 10건 수동 테스트** — Claude에 프롬프트 넣고 답 기록. 기대와 다른 건 프롬프트 수정. 결과를 `prompt/test_queries.md`에 표로
- [ ] **Step 4: 커밋**

### Task 5: 가상 설문 1,000건 + 분석 (8/31~9/1)

**Files:**
- Create: `survey/generate_survey.py` (규칙 기반 생성, 시드 고정), `survey/survey_2026.csv`, `survey/analyze.py`, `survey/charts/*.png` 3장, `survey/README.md`

**Interfaces:**
- Consumes: `baseline.json` 방향 분포, `feeder_origin.json` 출발지 비중, `move_202509` 성연령(20·30대 여성 최다)
- Produces: 편집기 항목 3 증빙. 문항: 귀가 소요·불편 순위(통신·화장실·안내·대기)·정보 채널·희망 기능

- [ ] **Step 1: 설계 제시 → 승인** — 문항 12개, 페르소나 분포(성연령·출발지·수단)를 실데이터 비율로 캘리브레이션, 응답 상관 규칙 3개(서쪽 귀가 ↔ 대기 불만 ↑ 등), 생성은 규칙+난수(LLM 생성 아님 — 재현성)
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
- [ ] **Step 3: 쇼 종료 시각 기입** — `echo 21:1x > data/live/show_end.txt`
- [ ] **Step 4: 24:00 종료·백업** — `data/live/*_20260905.jsonl` 커밋·push

### Task 10: 오차표·영상·편집기 초안 (9/6~7)

**Files:**
- Create: `submission/editor_draft.md`(9항목), `submission/video_script.md`, `docs/eval.md`

- [ ] **Step 1: `evaluate.py --date 20260905`** → 표. 우천 시 `--fallback rehearsal`
- [ ] **Step 2: 편집기 9항목 초안** — 스펙 §2 표 순서대로. 항목 5·6은 `benchmark-crowd-systems.md` §6·커밋 로그에서 발췌
- [ ] **Step 3: 영상 3분 스크립트** — 0:00 문제(실적 표) · 0:40 데이터·모델 · 1:30 페이지 시연(20→21→22시, 무정차 행) · 2:20 9/5 실측 vs 예측 · 2:50 한화 적용. 녹화·MP4 ≤20MB
- [ ] **Step 4: 추가자료 5개 목록·용량 확인. Release 자산 업로드(OD zip)**

### Task 11: 제출 (9/8)

- [ ] **Step 1: 오전 최종 점검** — Pages 링크 열림, 상태 4종 중 현재 상태 문구 정상, `pytest` 통과, 스펙 §4 체크리스트 전부 ✓
- [ ] **Step 2: 편집기 입력·영상 업로드·추가자료 첨부** — 18:00까지
- [ ] **Step 3: 20:00 제출 · 스크린샷 · `/dev-end`**

---

## Self-Review

- 스펙 §2 항목 1~9·추가자료 → Task 4·5·6·10·11에 대응. 항목 1(팀)은 사용자 입력.
- 스펙 §4 페이지 DoD → Task 3·7; 모델·데이터 DoD → Task 1·2·6; 당일 DoD → Task 8·9; 제출물 DoD → Task 10·11.
- 플레이스홀더: Task 4·5의 세부 문항·프롬프트 본문은 "설계 제시 → 승인" 단계에서 확정한다(approval-gate). 그 외 없음.
- 이름 일관성: `exit_forecast_2026.json` 필드명은 스펙 §3과 동일. `show_end.txt` 경로 `data/live/`.
