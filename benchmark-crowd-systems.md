# 혼잡 예측 시스템 벤치마크 — 우리 예측을 어디를 어떻게 고칠 것인가

작성 2026-08-29 · 산출물: 타 혼잡·대기 예측 시스템 조사 + 우리 모델(`src/backtrack.py`·`src/nowcast.py`·`docs/index.html`)에 적용할 개선 목록.
방어 배점: **데이터 근거 15**(방법의 외부 근거), **현업 적용 가능성 20**(운영 중인 시스템과의 대조), AI 도구 활용(조사 자동화 기록은 §6).

---

## 1. 결론 먼저

우리 구조(과거 이벤트 곡선 × 당일 스케일 α, 종료 시각 앵커, 부하율 = 수요÷관측 최대)는 **MARTA 특별행사 논문(Santanam et al. 2021)이 134경기로 검증한 방법과 같은 꼴**이다. 바꿀 것은 모델의 뼈대가 아니라 다음 6개다 — 전부 반나절 이내, 새 데이터 불필요.

| # | 개선 | 바꾸는 항 | 근거 시스템 | 비용 |
|---|---|---|---|---|
| 1 | 이벤트 귀속 승차 = 축제일 − **평시 토요일 51일 분포** 초과분 (지금은 대조 2일 평균). 가중치는 중앙값 기준, p90은 검증용(§4-1 정정) | `backtrack.py` 역 귀속 가중치 | MARTA station signature | 2h |
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

1. **평시 분포 기준 귀속** — `subway_2025.csv` 전 토요일(51일)로 역·시간대별 평시 분포를 만들고 초과분을 가중치로. 2024도 동일.
   **(2026-08-29 정정)** MARTA 식 p90 으로 돌려보니 교차검증은 0.31/0.73 으로 내려왔지만 피더 상위에서 고속터미널·홍대·신림이 사라지고 어린이대공원·거여·대치(×0.99)가 올라옴 — 행사 잦은 환승역은 p90 자체가 높아 축제일이 못 넘는다. p90 은 경기장 역 스파이크 검출용. **가중치는 중앙값(p50) 기준, p90 은 교차검증 지표**로 채택.
2. **속도-밀도 지연** — 관람구역 5곳→출구 7개 직선거리×1.3(추정) + 구역 밀도(CCTV 등급 대표값: 여유 1.5 / 주의 3 / 경계 4 / 심각 5명/m², 서울시 3/4/5 기준) → 첫 300m 구역 밀도·이후 가로 1.5명/m²(추정) Kladek 속도, 정체 하한 0.15 m/s(추정) → 시간대 안 균등 출발 가정으로 같은/다음/다다음 시간대 배분. CCTV 없으면 구역 밀도 3명/m² = 이벤트광장→여의도역 38.7분 ≈ 기존 40/60. 구역↔카메라 매핑 500m(5구역 전부 1대 이상). 구역별 관람객 비중은 균등 가정(추정). 구현 `nowcast.lag_table()`.
3. **카피** — 숫자 0.90 옆에 "평소 최대의 90%". 차트에 2025 같은 시각 실측 승차 참조선(Yahoo 전년 타임랩스의 정적 버전).
4. **시간×출구 격자** — 오프라인 플랜 섹션 위에 5시간×7출구 등급 격자, 각 시간 상위 2 "추천"·하위 1 "피하기" 태그. 사전 예측표만으로 그릴 수 있어 전날부터 유효.
5. **종료 offset** — `nowcast.py --show-end 21:25` 인자 또는 `data/live/show_end.txt`(run_all 루프가 5분마다 읽음) + `latest.json.show_end_actual/source`. 현장에서 연장 시 다음 틱에 반영.
6. **CCTV m² 환산·신뢰도** — 수집기는 이미 `roi_m2`(cams.json)로 명/m² 환산·3/4/5 등급을 지원. 값이 비어 있어 점유율 등급으로 동작 중 → 면적은 사용자가 지도에서 측정해 넣는다(카메라 5대 우선). 신뢰도 플래그 구현: 저조도(<40/255)·배경차분 실패(점유율≥0.9 → 등급 "보정전")·밀도 포화(≥5명/m²)·count<20 인데 점유율 높음. nowcast는 count<20 등급을 구역 밀도에 쓰지 않는다.
7. **버퍼 규칙** — 사전표 밴드 = 4회 min×0.9 / max×1.1. 라이브 모드는 사전표 밴드 비율 × α(버퍼 포함). 9/5 후 MAPE(우리 vs 도시데이터)로 교체.

## 5. 미확인·한계
- 국토부 정거장 설계지침의 계단·에스컬레이터·게이트 pph — 원문 PDF 접근 실패(인증서). 확보되면 9호선 추정 용량 대체.
- 서울 도시데이터 12h 예측·Amsterdam 85~90%·Paris 앱 — 방법·정확도 미공개. 우리 비교 대상은 서울 12h 예측 하나뿐.
- MARTA는 AFC 개인 단위 OD가 있어 열차 단위 분석이 가능했다. 우리는 시간대 집계라 열차 단위 불가.
- CCTV 야간 테스트(2026-08-29 토 20:00~21:00, TOPIS 23대, 60초 주기 1,380건): 스트림 ok 95~100%, 프레임 중앙 밝기 56~98 — 저조도 임계(40) 걸린 카메라 0대(가로등·교량 조명). count 중앙값 1~14명, 플래그 count_vs_occ 4대(63빌딩·국회·노량진수산·마포대교북단 — 차량·구조물 오검출 의심), no frame 산발 17건(재시도로 복구). 축제일 조명(불꽃·인파 밀집)은 미검증 → 임계는 유지, ROI 캘리브레이션(5대) 전까지 모델 입력 제외 유지.
- 백테스트 cross-year(다른 해 E·곡선으로 예측) 오차 0.44 — MARTA LR MAPE 11.7% 와 직접 비교 불가(그쪽은 열차 단위·다년 학습). 우리 오차의 주원인은 연도 간 총량 이동(2년 표본)이며 밴드(min×0.9/max×1.1)로 표시.

## 6. 조사 과정 기록 (AI 도구 활용)
- 1차: Opus 서브에이전트 5개 병렬(축별 6~10항목 × 7필드) → **49분 무응답, 중단**. 2차: 3개로 축소·항목 4·툴 호출 10회·10분 상한 → 10분 무응답, 중단. 원인 미상(에이전트 측 진행 없음).
- 3차: 메인 세션에서 WebSearch 11회 + WebFetch 6회(2회 실패: TfL 포럼 403, 국토부 PDF 인증서) + MARTA 논문 PDF 10쪽 직접 열람 → 본 문서. 소요 약 25분.
- 교훈: 리서치 위임은 항목·툴 호출·시간 상한을 명시해도 무응답일 수 있다. 상한 시각에 직접 전환.

## 7. 추가 조사 (2026-08-31) — 같은 시도·새 데이터·배울점

| 발견 | 내용 | 우리에게 |
|---|---|---|
| SKT 지오비전 퍼즐 「'22 불꽃축제 지하철 이용」 | 2022 축제일 vs 전주 토요일: 여의나루 2.7배·샛강 **3.6배**·여의도 2.1배, **신길 0.71배(감소)**. 출구별: 여의나루 3번 42%+2번 34%, 여의도 4번 32%+5번 22%. 연령별: 10~20대 여의나루, 30대+ 여의도. 20시 이후 여의도·샛강 승차 급증 | 유일하게 발견된 동일 행사 분석. 샛강 큼·저녁 분산 = 우리 결론과 교차 확인. **출구 번호 비중 → 플랜 카드·챗봇 안내에 인용 가능(2022 기준 표기)**. 연령별 선호 → T5 설문 페르소나 근거. 신길 감소(2022)는 우리 2024/25 양수 초과와 다름 — 연도 차이/일 단위 vs 저녁 초과 차이로 해석, 메모 |
| 행안부 인파관리지원시스템 (2023.12~) | 이통사 기지국 접속정보로 전국 100개소 밀집도 산출, 위험경보를 지자체 공무원에 자동 전파 | 관리자 경보 시스템(공무원 대상). 우리는 **관람객 행동 안내 레이어**로 정확히 보완 관계 — 기획서 차별화 문단에 사용 |
| London NYE 불꽃 (TfL) | 역을 exit-only/entry-only로 전환, 자정 후 일방통행 보행 루트, 단계적 사전 통제, 심야 증편 | 운영 어휘 차용: 확장 제안(오렌지세이프티 관리자 뷰)에 "여의나루 해제 시 exit-only 운영·일방 보행 루트" 제안 문구. 관람객 카피 "나올 때 역·출구 지정" 근거 |
| 서울 생활인구 (OA-14991 행정동·OA-14979 집계구, KT) | 시간대별 특정 지역 존재 인구. 축제일 여의도동 곡선 확보 가능 | **새 검증 데이터셋**: KT OD 곡선·citydata 인구와 3자 대조(사전, 저비용). 9/6 오차표 보강 후보 |
| 교통카드 빅데이터 통합시스템 stcis.go.kr | 전국 교통카드 승하차 (코레일 포함 가능성) | **신길 1호선 공백을 메울 수 있는 유일한 리드** — 접근 절차 확인 필요 |
| DBpia 지하철 혼잡 예측(빅데이터, 정확도 ~81%) | 일반 혼잡 예측 연구. 행사 요인은 향후 과제로 언급 | 행사 특화 국내 학술 선행은 사실상 없음 → 우리 접근의 신규성 근거로 인용 |

추가 CCTV 소스 조사 (8/31 2차): ① **경찰청 UTIC 교통 CCTV**(data.go.kr 15148511, utic.go.kr) — 전국 관제 영상 개방, 서울 시내 TOPIS 외 보완각 가능성. 단 제공 목록·안정성 확인 필요(수시 중단 고지) ② 국토부 ITS CCTV — 고속·국도 위주라 여의도 커버 낮음 ③ 유튜브 한강 라이브캠(마포·여의도 조망 4K 다수) — 고정 조망 원경. 개인 채널이라 수집·재가공은 저작권·안정성 리스크 → 시연 화면 참고로만, 파이프라인 편입 비추천. 결론: TOPIS 23대 + 필요 시 UTIC 보완 확인, 나머지는 제외.

UTIC 확보 조사 결과 (8/31 실측): 서울시 실시간 도시데이터 사이트의 핫스팟별 CCTV API(`data.seoul.go.kr/SeoulRtd/api/cctv?hotspotNm=…`)가 UTIC 계열 원본(210.179.218.51~53, wowza HLS)을 그대로 노출한다. 여의도 핫스팟 9대 중 **8대는 우리 TOPIS 23대와 동일 카메라(좌표 0m 일치)** — 즉 "경찰 CCTV"는 신규가 아니라 같은 물리 카메라의 다른 서빙. 유일 신규 L933084(여의도, 영등포 방면 시내)는 스트림 URL 미공개. **차이는 화질: UTIC 원본 1280×720 vs TOPIS 720×480** — 63빌딩 스트림 프레임 캡처 성공(720p, OpenCV). **(8/31 반영 완료)** 인접 핫스팟까지 스캔해 총 **9대 매칭**(63빌딩·국회·국회도서관·마포대교남단·여의공원·여의교북단·국민은행·원효대교남단·노량진삼거리). 480p가 720p의 비등방 축소판임을 프레임 대조로 확인 → 수집기를 **HD 우선 + TOPIS 480p 자동 폴백**으로 전환(`hls_hd`), ROI는 `roi_frame` 기준 축 스케일로 변환(캘리브레이션 유지). 레코드에 `origin: hd/sd` 기록. IP 직결 원본 '수시 중단' 리스크는 폴백이 흡수.

배울점 요약: ① 출구 번호 단위 안내(지오비전)가 우리 안내를 한 단계 구체화 ② exit-only·일방 루트(런던)는 확장 제안의 실무 어휘 ③ 생활인구는 공짜 3자 검증 ④ 동일 행사 학술 선행 부재 = 신규성.
2022 지오비전 배수(여의나루 2.7·샛강 3.6·여의도 2.1)는 **일 단위·전주 대비**라 우리 저녁 초과 배수(샛강 6배 등, 중앙값 대비)와 직접 비교 불가 — 방향만 일치 확인.

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
- SKT 지오비전 퍼즐 '22 불꽃축제 https://puzzle.geovision.co.kr/insights/22%EB%85%84-%EC%84%9C%EC%9A%B8%EC%84%B8%EA%B3%84%EB%B6%88%EA%BD%83%EC%B6%95%EC%A0%9C-%EC%A7%80%ED%95%98%EC%B2%A0-%EC%9D%B4%EC%9A%A9-i1674791591847
- 행안부 인파관리지원시스템 https://www.korea.kr/news/policyNewsView.do?newsId=148924176 · https://www.mois.go.kr/frt/bbs/type010/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000008&nttId=104479
- London NYE 교통 https://www.nye.london/en/nye-transport.html
- 서울 생활인구 OA-14991 https://data.seoul.go.kr/dataList/OA-14991/S/1/datasetView.do · 교통카드 빅데이터 https://stcis.go.kr/
- 서울시 지하철 설계기준 https://news.seoul.go.kr/citybuild/archives/200621 · 국토부 고시 https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000118529
