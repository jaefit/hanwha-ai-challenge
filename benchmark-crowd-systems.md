# 혼잡 예측 시스템 벤치마크 — 우리 예측을 어디를 어떻게 고칠 것인가

작성 2026-08-29 · 산출물: 타 혼잡·대기 예측 시스템 조사 + 우리 모델(`src/backtrack.py`·`src/nowcast.py`·`docs/index.html`)에 적용할 개선 목록.
방어 배점: **데이터 근거 15**(방법의 외부 근거), **현업 적용 가능성 20**(운영 중인 시스템과의 대조), AI 도구 활용(조사 자동화 기록은 §6).

---

## 1. 결론 먼저

우리 구조(과거 이벤트 곡선 × 당일 스케일 α, 종료 시각 앵커, 부하율 = 수요÷관측 최대)는 **MARTA 특별행사 논문(Santanam et al. 2021)이 134경기로 검증한 방법과 같은 꼴**이다. 바꿀 것은 모델의 뼈대가 아니라 다음 6개다 — 전부 반나절 이내, 새 데이터 불필요.

| # | 개선 | 바꾸는 항 | 근거 시스템 | 비용 |
|---|---|---|---|---|
| 1 | 이벤트 귀속 승차 = 축제일 − **평시 토요일 90퍼센타일** 초과분 (지금은 대조 2일 평균) | `backtrack.py` 역 귀속 가중치 | MARTA station signature | 2h |
| 2 | 도달 지연 40/60 → **거리 ÷ 밀도별 보행속도**(Weidmann) — 구역별·CCTV 등급 연동 | `nowcast.py` LAG_SAME/NEXT | Weidmann 1993 / Fruin | 3h |
| 3 | 부하율 문구를 **"평소 최대 대비 %"** 로, 등급 아래 "작년 이 시간" 참조선 | `index.html` 카피·차트 | TfL·Google·Yahoo | 2h |
| 4 | **시간×출구 격자**(초록 추천 / 빨강 피하기) — 전날 미리 보는 사전 계획 뷰 | `index.html` 새 섹션 | Paris 2024 Anticiper les Jeux | 3h |
| 5 | 쇼 종료 **실제 시각 입력**(offset) → 곡선 즉시 재앵커 | `nowcast.py` 파라미터 + `latest.json` 필드 | MARTA offset 보정 | 1h |
| 6 | CCTV 가시면적 **지도 폴리곤 m²** 로 count→명/m² 환산, 5~6명/m² 이상은 점유율만 | `collector_cctv.py`·`cams.json` | MapChecking·Vizio 한계치 | 3h |

보류(제출 후): 피더 역 실시간 승차 선행지표(문헌상 "타 역 유입 급증→유출 예측"으로 검증된 방식), 열차 단위 left-behind 시뮬레이션.

---

## 2. 조사한 시스템 (11건)

### 2.1 공공·도시 인파 안내

| 시스템 | 데이터·갱신 | 방법 | 시민 출력 | 정확도 공개 |
|---|---|---|---|---|
| **서울 실시간 도시데이터** (서울시·KT) | KT 기지국 신호 5분 집계 → 전수화 추정, 공공 교통·환경 데이터 융합 | 최근 12h 실측 + AI 12h 예측 | 4등급(여유~붐빔) + 인구 min~max, 핫스팟 120곳 | 미공개 |
| **Amsterdam CMSA / Public Eye** | 기존 시 CCTV + CV, 3D·Wi-Fi 센서, 프레임 미저장(밀도·히트맵만) | 규모·밀도·방향·속도 예측 모델 | 앱·웹(druktebeeld), 신호등식 표지, 키오스크 우회 안내, 일방통행 보행 | "85~90%" 주장, 측정법 미공개 |
| **Yahoo! JAPAN 混雑レーダー** | 동의한 앱 사용자 위치 통계 | 히트맵 집계(예측 아님) | 색 4단계 히트맵. **花火大会는 전년도 혼잡 레이더 타임랩스 영상을 미리 제공**해 회피 유도 | — |
| **Paris 2024 Anticiper les Jeux** (교통부) | 대회 일정 기반 사전 예측 | 시간별·일별 4단계 | **역별 "이용 권장(초록)/피하기(빨강)"** 격자, 앱은 승강장 대기 추정 | 방법 미공개 |

### 2.2 대중교통 혼잡

| 시스템 | 데이터·갱신 | 방법 | 출력 | 정확도 |
|---|---|---|---|---|
| **TfL busyness** | 역내 비식별 Wi-Fi, 5분 | 역별 "그 역 최대 대비 비율" | 앱(TfL Go·Moovit) 등급, 환승 소요시간을 55개 역에서 Wi-Fi 실측으로 보정 | 미공개 |
| **Google Maps 혼잡도** | 옵트인 위치기록, 차분 프라이버시 | 장소별 "최대 대비 %" | 3문구(as busy as it gets / a little busy / not too busy), **데이터 부족하면 표시 안 함** | 미공개 |
| **서울교통공사·SKT 실시간 혼잡** | 열차 위치 + T-WiFi + TMAP 역정보 | 칸 160명 = 100% | 2호선 실시간, 타 노선은 TMAP 빅데이터 **예측 혼잡도** | 미공개 |
| **MARTA 특별행사 논문** (Georgia Tech 2021) | AFC 교통카드 2016~2020, 134 경기일 | ① 이벤트 승차 = 실측 − 평시 90퍼센타일 초과분 ② **경기 종료 기준 5분 빈 유출 곡선이 경기마다 일관** → 평균 곡선 정규화 × 예측 총량 ③ 총량 = 관중수 선형회귀(MAPE 11.7%, LR+RF 11.3%) ④ 열차 실효 용량 707명 = 정격 576의 123%(left-behind 역산) ⑤ **예측 오차만큼(10%) 버퍼** | 운영자용 | LOOCV MAPE 0.113 |

### 2.3 계측·보행 이론

| 항목 | 내용 | 출처 |
|---|---|---|
| Weidmann 속도-밀도 | 자유속도 1.34 m/s, 정체 밀도 5.4명/m². Kladek식 v = 1.34·(1−exp(−1.913·(1/ρ − 1/5.4))) → 2명/m² 0.61 m/s, 3명/m² 0.33 m/s | Weidmann 1993, Collective Dynamics 리뷰 |
| Fruin 자유속도 | 단방향 1.43, 양방향 1.36 m/s | Fruin |
| CCTV 밀도 추정 한계 | 5~6명/m² 넘으면 개체 검출 붕괴 → 질감 기반 밀도 회귀로 전환. 저조도에서 성능 저하 | Vizio·arXiv 저조도 카운팅 |
| MapChecking (Still) | 면적×밀도, **현실 기준 2명/m²**, 균일 밀도 가정은 과대추정 | mapchecking.com |
| 국내 역사 설계기준 | 계단 최소폭 3m(서울시). 처리량 pph 수치는 **미확인** — 국토부 고시 2018-199호 원문 확인 필요 | 서울시·국토부 |

---

## 3. 우리 시스템과의 대조

**같은 것**
- 과거 이벤트 곡선 × 스케일: MARTA "평균 유출 곡선 정규화 × 예측 총량" = 우리 "2년 유출 곡선 × α".
- 종료 시각 앵커: MARTA는 경기 연장 시 offset 보정 → 우리 +40분 시프트와 동일 사고.
- 용량 = 관측 최대: MARTA도 정격 대신 실측 역산값(하한) 사용.
- 등급 4단계 + 최대 대비 비율: TfL·Google·서울시와 같은 의미 체계.
- 프레임 미저장·집계만: Amsterdam Public Eye와 같은 원칙.

**다른 것 (개선 대상)**
- 이벤트 귀속: MARTA는 90퍼센타일 초과분, 우리는 대조 2일 평균 차이 → 타 요인 혼입(2025 교차검증 2.37).
- 도달 지연: 우리는 40/60 상수. 문헌은 거리÷속도(밀도 의존).
- 불확실성: MARTA는 MAPE만큼 버퍼. 우리는 2년×방향기준 4회 min/max — 표본 2라 밴드가 좁아 과신 위험.
- 사전 계획 뷰: Paris는 시간×역 격자. 우리는 시간 탭 하나씩.
- 표시 억제 규칙: Google은 데이터 부족 시 미표시. 우리는 "수집 전" 상태만 있고 CCTV 야간 저신뢰 억제 규칙 없음.

---

## 4. 채택 개선 상세

1. **90퍼센타일 귀속** — `subway_2025.csv` 전 토요일(≈50일)로 역·시간대별 평시 분포를 만들고, 축제일 승차가 90퍼센타일을 넘는 초과분만 가중치. 2024도 동일. 교차검증 비율이 1 근처로 내려오는지 확인.
2. **속도-밀도 지연** — 관람구역 5곳→출구 7개 거리표(지도 근사) + 구역 밀도(CCTV 등급: 여유 1 / 주의 2 / 경계 3 / 심각 4명/m²) → Kladek 속도 → 도달 시각 분포 → 시간대 배분. 40/60은 "CCTV 없을 때 기본값"으로 유지.
3. **카피** — 숫자 0.90 옆에 "평소 최대의 90%". 차트에 2025 같은 시각 실측 승차 참조선(Yahoo 전년 타임랩스의 정적 버전).
4. **시간×출구 격자** — 오프라인 플랜 섹션 위에 5시간×7출구 등급 격자, 각 시간 상위 2 "추천"·하위 1 "피하기" 태그. 사전 예측표만으로 그릴 수 있어 전날부터 유효.
5. **종료 offset** — `nowcast.py --show-end 21:25` 인자 + `latest.json.show_end_actual`. 현장에서 연장 시 1분 안에 반영.
6. **CCTV m² 환산** — `cams.json`에 카메라별 가시 보행면적 폴리곤(m²) 수기 입력(지도에서 측정) → 명/m² = count ÷ 면적. 5명/m² 이상 또는 야간 저조도 플래그 시 count 숨기고 점유율·등급만.
7. **버퍼 규칙** — 9/5 후 MAPE(우리 vs 도시데이터)를 구해 라이브 밴드 = ±MAPE. 그 전엔 4회 min/max에 ±10%(MARTA 관행)를 더해 표시.

## 5. 미확인·한계
- 국토부 정거장 설계지침의 계단·에스컬레이터·게이트 pph — 원문 PDF 접근 실패(인증서). 확보되면 9호선 추정 용량 대체.
- 서울 도시데이터 12h 예측·Amsterdam 85~90%·Paris 앱 — 방법·정확도 미공개. 우리 비교 대상은 서울 12h 예측 하나뿐.
- MARTA는 AFC 개인 단위 OD가 있어 열차 단위 분석이 가능했다. 우리는 시간대 집계라 열차 단위 불가.

## 6. 조사 과정 기록 (AI 도구 활용)
- 1차: Opus 서브에이전트 5개 병렬(축별 6~10항목 × 7필드) → **49분 무응답, 중단**. 2차: 3개로 축소·항목 4·툴 호출 10회·10분 상한 → 10분 무응답, 중단. 원인 미상(에이전트 측 진행 없음).
- 3차: 메인 세션에서 WebSearch 11회 + WebFetch 6회(2회 실패: TfL 포럼 403, 국토부 PDF 인증서) + MARTA 논문 PDF 10쪽 직접 열람 → 본 문서. 소요 약 25분.
- 교훈: 리서치 위임은 항목·툴 호출·시간 상한을 명시해도 무응답일 수 있다. 상한 시각에 직접 전환.

## 출처
- 서울 실시간 도시데이터 https://data.seoul.go.kr/SeoulRtd/ · KT 5분 집계·전수화 https://www.khan.co.kr/article/202210312119015 · https://www.etnews.com/20220901000247
- Amsterdam Public Eye https://www.itu.int/hub/2021/10/why-the-city-of-amsterdam-developed-its-own-crowd-monitoring-technology/ · CMSA API https://api.data.amsterdam.nl/v1/docs/datasets/cmsa.html
- Yahoo! 混雑レーダー 花火 https://map.yahoo.co.jp/blog/archives/20160721_map_hanabimovie.html · https://news.mynavi.jp/article/20200812-1217007/
- Paris 2024 https://anticiperlesjeux.gouv.fr/en/ · https://www.info.gouv.fr/actualite/jop-2024-un-site-pour-anticiper-vos-deplacements
- TfL Wi-Fi 혼잡 https://tfl-newsroom.prgloo.com/news/tfl-press-release-first-improvements-to-customer-information-from-depersonalised-wi-fi-data-go-live · https://moovit.com/press-releases/moovit-to-use-tfl-open-data-to-display-tube-station-busyness-levels-for-transport-passengers/
- Google Maps https://blog.google/products-and-platforms/products/maps/maps101-popular-times-and-live-busyness-information/ · https://support.google.com/maps/answer/11323117
- 서울교통공사·SKT https://news.sktelecom.com/138970 · OA-12928 https://data.seoul.go.kr/dataList/OA-12928/F/1/datasetView.do
- Santanam, Trasatti, Van Hentenryck, Zhang (2021) Public Transit for Special Events https://arxiv.org/abs/2106.05359
- 특별행사 수요 문헌: Beijing 다변량 교란 DNN https://www.sciencedirect.com/science/article/abs/pii/S0957417421013981 · 역간 상호작용·이벤트 실시간 예측 https://www.sciencedirect.com/science/article/abs/pii/S0968090X18301797
- Weidmann/Fruin https://collective-dynamics.eu/index.php/cod/article/view/A17 · https://arxiv.org/pdf/physics/0506170
- 밀도 추정 한계 https://www.viziosense.com/post/smart-city-crowd-density-monitoring-real-world-use-cases-ai-accuracy-and-implementation-costs · 저조도 https://arxiv.org/pdf/2606.18566 · MapChecking https://www.mapchecking.com/
- 서울시 지하철 설계기준 https://news.seoul.go.kr/citybuild/archives/200621 · 국토부 고시 https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000118529
