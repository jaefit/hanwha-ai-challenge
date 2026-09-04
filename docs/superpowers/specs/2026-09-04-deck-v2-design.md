# 피치 덱 v2 설계 스펙 — 5분 발표용 12장 (라이트 테마 · 3층 해부)

작성 2026-09-04 · 산출물: `docs/deck.html` 제자리 교체. 현 덱(18장 · 검정 테마 · 2026-09-01~03)은 git 이력에 남고 링크(`/deck.html`)는 그대로다.

**왜 다시 짜나.** ① 검정 바탕·세리프는 밤 불꽃 무드지 밝은 방 발표엔 대비가 죽는다. 관람객 화면(`go.html`)과 같은 얼굴이면 "이게 그 화면"이 공짜로 이어진다. ② 현 18장은 기(1~3장) 뒤에 제품 화면 없이 수식으로 직행하고, 지도·피더·아키텍처가 척추 없이 나열되며, 검증이 검증 대상보다 먼저 나온다. ③ 5분에 18장은 많다. ④ 보고서 §3.6 피더 4단계·12역 도식, §4.1 3층 구조가 덱엔 한 줄뿐이라 "어떻게 만들었나"가 안 보인다.

---

## 1. 목표 (한 문장)

심사위원 앞 **5분 발표**에서, 관람객이 얻는 것(행동)과 그것을 만든 3층 구조(사전·당일·화면)와 검증까지를 12장으로 보여주되, 화면·도식·코드는 캡처가 아니라 **저장소 안의 실물**을 덱이 직접 끌어다 쓴다.

## 2. 범위 · 비범위

**한다**
- `docs/deck.html` 전면 교체 — 12장, 라이트 테마, 탐색(←/→ · 스크롤 스냅 · 진행 표시)은 현 덱 방식 유지
- 실물 임베드 — 3장 `go.html` · 4장 `index.html` 을 iframe 으로, 통신 없으면 폴백 이미지
- 보고서 그림 1(피더 12곳 방사형)·현 덱 canvas 애니 4종(α 격자 · 백테스트 산점 · 혼잡장 · 경로 레이스) 이식 + 라이트 재도색
- 코드 스트립 — 소스에서 빌드 시 잘라 넣는 실제 코드 4~6줄 × 3
- 발표자 노트 — 장마다 25초 대본을 `aside.notes` 로 숨겨 두고 `n` 키로 토글
- 9/5 실전 결과 자리 — JSON 만 채우면 되는 10장
- `tools/deck_data.py` 확장 · `tests/test_deck.py` 갱신 · README 갱신

**안 한다**
- `src/` · `docs/index.html` · `docs/go.html` 변경 (동결 이후. 임베드는 파라미터 없이 있는 그대로 띄운다)
- 영상 3분 편집(덱은 영상 촬영에 재사용하되 영상 작업은 T10)
- fireworks-js 불꽃 — 흰 바탕에 맞지 않고 외부 라이브러리 하나 줄인다. 훅은 카운트업만
- QR 코드 — URL 문자열로 충분
- 폴백 캡처 2장 생성 — 사용자가 직접 찍는다(헤드리스 캡처 금지 규칙)

## 3. 슬라이드 12장

시간 배분 5분 ÷ 12 = 25초/장. 각 장은 **한 문장(h2) + 한 화면**. 본문 글자는 뒷줄에서 읽히게 최소 22px.

| # | 막 | h2 (가안) | 화면 | 데이터 · 자산 | 자동 검사 |
|:-:|:-:|:--|:--|:--|:--|
| 1 | 기 | 불꽃이 끝나면 100만 명이 움직인다 — 그리고 역이 닫힌다 | 좌 카운트업 **100**만 · 우 카드 「≈ 0명 — 축제일 저녁 여의나루 하차」 + 3줄(지도앱은 오늘도 여의나루로 · 무정차 통제 · 실측 2년 공통) | 현 s1·s2 합침. 시간대별 하차 곡선은 `data/derived` 에 없어(용량 최댓값만) 큰 숫자로 간다 | 카운트업 목표값 100 |
| 2 | 기 | 지도앱도 서울시도 "상태"만 준다 — 빠진 건 행동 | 3열 카드: 지도앱(막힌 길 안내) / 서울시 4단계(붐빔·상태) / **빠진 것 = 어디로 나갈지** | 현 s3·s4 카피, 보고서 §1.1~1.2 | — |
| 3 | 승 | 상태가 아니라 행동 — 묻지 않는 귀가 내비 | 좌 폰 프레임(390×844 → 화면 맞춤 scale) **iframe `go.html`**, 위치 권한 없이 → 이벤트광장 기준 가상 위치 · 우 3줄: 위치 자동 · 1위 자동 · 시각 = 지금 | 실물 화면, 가상 위치. 폴백 `docs/deck/fallback_go.png` | iframe src `go.html` · `allow="geolocation"` **없음** · 폴백 참조 |
| 4 | 승 | 운영 화면 — 그리고 그 아래 3층 | 좌 **iframe `index.html`**(1280폭 → scale 0.5) · 우 3층 스택 [화면층 / 당일층 / 사전층] 각 한 줄. 다음 5장의 목차 | 현 s9 스택 재활용. 폴백 `fallback_ops.png` | iframe src `index.html` · 폴백 참조 |
| 5 | 전 | 사전층 ① 수요 = α × E_st × 도착형태 | 상 KaTeX 식 1개 + 3항 한 줄씩 · 하좌 출구 7개 실측 비중 가로막대(E_st) · 하우 **코드 스트립** `backtrack.py exit_forecast()` | `exit_bars.json` 신규(← `derived/exit_shares.json` `share_mean`) · `code_strips.json` | 막대 합 = 1.00 ± 0.01 · 스트립 = 소스 일치 |
| 6 | 전 | 사전층 ② 피더역 12곳 — 여의도보다 1시간 먼저 움직인다 | 좌 방사형 도식(방위 · 소요시간 링 10/20/30분 · 원 = 2년 귀속 인원) · 우상 lag 미니(r 0.72 → 0.98) · 우하 "4단계로 찾았다"(초과 승차 → 2년 필터 → KT 상한 → 교차 검증) | 보고서 `radialInit()` 이식, 데이터 `feeder_map.json` 신규(← `derived/feeder_origin.json` · `feeder_leadlag.json`) · 현 `feeder_lag.json` | r 두 값 = 소스 일치(현 테스트 유지) · 역 12곳 |
| 7 | 전 | 당일층 — 5분마다 오늘 규모를 다시 잰다 | 3열: ① α 베이즈 격자 애니(밴드가 좁아진다, **α=1.15 가정** 라벨) ② CCTV 23대 → 보행속도(Kladek 식 1줄 + 등급 사다리 1.5/3/4/5) ③ 워치독·발행(30초 생존 확인 · 재기동 17초 · `api_last_ok`) · 하단 **코드 스트립** `nowcast.py` α 격자 사후 | 현 5c 애니 재도색 · `alpha_grid.json` · `code_strips.json` | 가정 라벨 존재(현 테스트 유지) · 스트립 = 소스 일치 |
| 8 | 전 | 화면층 — 못 본 곳은 모른다고, 길은 걸을 수 있는 길로 | 좌 혼잡장 GP 프레임(**등급 배치는 예시** 라벨) · 우 최단 vs 회피 레이스(현 12번 3패널 → 2패널: 최단 통과 / 회피) · 하단 **코드 스트립** `field.js blendSeconds()` | 현 7b·7c canvas · `field_grid.json` · `route_demo.json` | 예시 라벨 · 경로 숫자 = 내보내기 일치(현 테스트 유지) · 마포역 1,907m 재현 |
| 9 | 전 | 검증 — 백테스트로 맞히고, 우리 것을 먼저 깼다 | 좌 백테스트 산점 + 등급 적중률 숫자 · 우 결함 대장 등급별 건수(치명/높음/중간/낮음) + 조치·보류·철회 한 줄 | 현 6b · `backtest_bars.json` · `redteam_counts.json` 신규(← `redteam-20260901.md` ID 정규식 집계) | 적중률 = 소스 일치(현 테스트 유지) · 건수 합 = 대장 ID 수 |
| 10 | 결 | 9/5 실전 결과 | 채워지면: 등급 적중 · α 궤적(p10/p50/p90) · 발행 틱 수 · 재기동 횟수 · 한 줄 소감. 비면: "9/5 실전 — 9/6 채움" 상태 화면 | `live_result.json` 신규(초기 `{"filled": false}`), 9/6 `evaluate.py` → `deck_data.py` 로 채움 | 파일 존재 · `filled` 불리언 |
| 11 | 결 | 판단은 사람이, 구현은 AI가 — 같은 뼈대로 다른 현장 | 좌 현 s10 6줄 압축(파이프라인 · 엔진 · 수집기 · 검증 3층 · 산출물 · 과정 기록) · 우 확장 1줄: 실측 뼈대 + 당일 보정 + 검증은 행사와 무관 → 한화 현장 적용안(오렌지세이프티 관리자 뷰의 관람객 레이어, 제출 스펙 §2 9번과 같은 문구) | 현 s10 | — |
| 12 | 결 | 예측은 검증까지가 제품 | 한 줄 + URL `jaefit.github.io/hanwha-ai-challenge` | 현 s12 | — |

버리는 현 슬라이드: 5b(수식 4개) · 6(적중률 표) · 8b(피더 lag 단독) · 11(일정). 전부 보고서에 있다.

## 4. 테마

`go.html` 토큰을 그대로 가져온다. 슬라이드 = 바탕 위 흰 카드(관람객 화면의 시트 느낌).

| 역할 | 값 | 비고 |
|:--|:--|:--|
| 바탕 · 카드 · 괘선 | `#F5F4F1` · `#FFFFFF` · `#E2DFD8` | go.html `--bg --sheet --rule` |
| 글자 3단 | `#14110C` · `#5B554B` · `#8F897D` | go.html `--ink --ink-2 --sub` |
| 액센트 | `#F36F21` | 한화 오렌지. **도형·바·진행선에만.** 흰 바탕 위 텍스트 강조는 굵기로 한다 — 오렌지 글자는 등급 「주의」색과 헷갈린다 |
| 등급 g1~g4 | `#2E7D5B` · `#8A6400` · `#B0521C` · `#B3352B` | go.html 것. status 전용, 시리즈로 안 쓴다 |
| 차트 시리즈 2색 | 플랜에서 확정 | 현 `#e2661c`·`#4f95e8` 은 검정 위 검증값. 라이트 바탕에서 dataviz 검증기(CVD ΔE · 대비) 통과한 값으로 교체 |
| 라이브 · 오프라인 | `#2A78D6` · `#D0342C` | 신선도 필 색, 10장 상태 표시에 재사용 |

서체: Pretendard(본문·숫자, go.html 과 같은 jsDelivr 동적 서브셋) · Black Han Sans 는 **1장 훅만** · IBM Plex Mono 코드 스트립·표 숫자. Hahmlet 세리프는 뺀다. KaTeX 0.16.11 유지(5장 · 7장 식).

장마다 하단 진행 바(액센트) + `3 / 12` + 막 라벨(기·승·전·결). 라이트 단일 — 다크 모드 없음(발표 환경 고정).

## 5. 실물 임베드 · 폴백

- 3장 `<iframe src="go.html">` — **위치 권한을 주지 않는다**(`allow="geolocation"` 생략). 브라우저가 팝업 없이 즉시 거절하고 go.html 은 `setGeo("denied")` → 이벤트광장 기준 가상 위치로 뜬다(2026-09-04 사용자 결정: 프로젝트 발표회라 실위치 시연 불필요). 팝업이 발표 중에 안 뜨는 게 핵심. go.html 은 손대지 않는다.
- 4장 `<iframe src="index.html">` 1280폭, CSS `transform: scale(.5)`.
- 같은 origin(Pages)이라 iframe 안 문서 상태를 읽을 수 있다. **폴백 규칙:** `navigator.onLine` 이 거짓이거나, 4초 안에 iframe 문서 본문이 비어 있으면 iframe 을 숨기고 `docs/deck/fallback_go.png` / `fallback_ops.png` 를 같은 자리에 띄운다. 이미지도 없으면 "라이브 화면 — 통신 필요" 문구.
- 캡처 2장은 **사용자가 직접** 찍어 넣는다(파일명 위 그대로). 덱은 파일 유무와 무관하게 동작한다.
- 발표장 통신 리스크는 README 「발표」 절에 한 줄: 노트북 지참 · 휴대폰 테더링 · 폴백 캡처 갱신일.

## 6. 코드 스트립

- 5 · 7 · 8장 하단, 4~6줄, `파일:시작줄` 라벨, 모노 18px. 25초엔 못 읽는다 — "진짜 도는 코드" 신호가 목적이라 작게.
- **손으로 베끼지 않는다.** `tools/deck_data.py` 가 소스에서 **앵커 문자열**(함수 시그니처)을 찾아 그 줄부터 N줄을 잘라 `docs/deck/code_strips.json` 으로 낸다. 줄 번호는 내보낼 때 계산한다(소스가 움직여도 앵커로 따라간다).
- 스트립 3개: `src/backtrack.py` `def exit_forecast(` · `src/nowcast.py` 격자 사후분포 함수(독스트링 "격자 사후분포" 가 있는 def) · `docs/app/field.js` `function blendSeconds(`.
- 테스트: 각 스트립의 `lines` 가 현재 소스의 해당 구간과 문자 단위로 같다. 어긋나면 `deck_data.py` 재실행이 답이다.

## 7. 데이터 파이프라인

`docs/deck/` 에 둔다 — `publish.py:109` 가 `git add docs/data` 로 디렉터리를 통째로 스테이징하므로 `docs/data/` 밖이어야 한다(현 덱과 같은 이유).

| 파일 | 상태 | 출처 | 만드는 것 |
|:--|:--|:--|:--|
| `alpha_grid.json` · `backtest_bars.json` · `feeder_lag.json` | 기존 | `data/derived/*` | `deck_data.py` |
| `field_grid.json` · `route_demo.json` | 기존 | `docs/app/field.js` · 보행망 | `deck_field_route.mjs` |
| `exit_bars.json` | 신규 | `derived/exit_shares.json` `share_mean` | `deck_data.py` |
| `feeder_map.json` | 신규 | `derived/feeder_origin.json`(귀속 인원) · `feeder_leadlag.json`(소요·r) · `stations.json`(좌표 → 방위) | `deck_data.py` |
| `redteam_counts.json` | 신규 | `redteam-20260901.md` — 표 첫 칸 `C\d+ H\d+ M\d+ L\d+` 고유 ID 집계 | `deck_data.py` |
| `code_strips.json` | 신규 | §6 | `deck_data.py` |
| `live_result.json` | 신규 | 초기 `{"filled": false}` · 9/6 `evaluate.py` 결과로 채움 | `deck_data.py --live` (9/6 추가) |
| `fallback_go.png` · `fallback_ops.png` | 사용자 제공 | 실기기 캡처 | 사람 |

`test_every_chart_has_its_data_file` 의 키 집합을 위 목록으로 갱신한다.

## 8. 테스트 (`tests/test_deck.py`)

유지: 데이터 위치(`docs/data` 밖) · 경로 숫자 일치 · 마포역 1,907m 재현 · 피더 r 일치 · 백테스트 적중률 일치 · 가정/예시 라벨 · α 밴드 수렴 · KaTeX · 죽은 타일 URL 없음.

신규:
- 섹션 12개, id `s1`~`s12`, 각각 h2 하나 · `aside.notes` 하나
- 라이트 토큰 존재(`--bg:#F5F4F1`) · 검정 토큰 부재(`#0b0d12`) · Hahmlet 부재 · fireworks-js 부재
- iframe 2개(`go.html` — `allow="geolocation"` 이 **없어야** 통과 · `index.html`) · 폴백 이미지 2개 참조
- 코드 스트립 3개 = 소스 일치(§6)
- `exit_bars` 합 1.00 ± 0.01 · `feeder_map` 12역 · `redteam_counts` 합 = 대장 ID 수
- `live_result.json` 존재 · `filled` 불리언

헤드리스 검증(메모리 레시피): KaTeX 렌더 노드 수·넘침 0, canvas 는 숫자로(가상시간 · 최소 창폭 500). **iframe 안 지도는 WebGL 이 없어 못 본다 — 실기기.**

## 9. git 운용 (작업 중 수집기가 돌고 있다)

- `run_all.sh` 가 5분마다 `docs/data` 를 커밋·push 한다. 내 커밋은 **파일 명시** `git add docs/deck.html docs/deck tests/test_deck.py tools/deck_data.py README.md docs/superpowers`. `git add -A` 금지(`data/live/*.jsonl` 미추적 파일이 딸려 온다).
- push 전에 `git pull --rebase`. 거절되면 `publish.py` 가 `--autostash` rebase 를 시도하므로 작업 트리에 미커밋 변경을 오래 두지 않는다 — 장 단위로 커밋.
- 동결 무관: `src/` · `index.html` · `go.html` 안 건드린다.

## 10. 완료 정의 (DoD)

1. `pytest tests -q` 전부 통과(기존 96 + 신규)
2. 헤드리스: 12 섹션 · KaTeX 오류 0 · canvas 4종 숫자 검증 · 콘솔 에러 0
3. 실기기(발표 PC 또는 폰): 3장 go.html 지도·시트, 4장 index.html 이 iframe 안에서 뜬다 · 오프라인으로 바꾸면 폴백이 뜬다
4. 발표자 노트 12장 = 소리 내어 읽어 5분 ± 30초
5. README 「피치 덱」 행 12장으로 · 「발표」 절 추가
6. Pages 에서 `/deck.html` 갱신 확인(`curl` 로 h2 첫 줄)

## 11. 미확정 (사용자 몫)

- 폴백 캡처 2장(go · ops) 촬영 시점 — 전야제 실기기 확인 때 같이 찍으면 한 번에 끝난다
- 11장 확장 문구의 한화 적용안 표현 — 제출 스펙 §2 9번 문구를 그대로 쓴다. 다르게 가려면 그 스펙과 함께 고친다
- 발표 시간 5분이 확정인지, Q&A 별도인지 — 대본 길이의 기준

## 12. 순서 (플랜이 쪼갠다)

테마·뼈대(12 빈 섹션 + 탐색 + 진행 바 + 노트) → 데이터 내보내기(신규 5 JSON + 테스트) → 정적 장(1·2·5·11·12) → 임베드 장(3·4 + 폴백) → 이식 장(6 피더 · 7 α · 8 혼잡장/경로 · 9 검증) → 10장 자리 → 헤드리스·실기기 → README·push.
