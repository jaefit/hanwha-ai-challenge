# 보행 네트워크 (OSM) — 경로탐색 데이터

작성일 2026-09-01 · 산출물: 팀원 핸드오프 `hanwha-routing-handoff-20260901-175810` 를 저장소에 편입한 것
방어 배점: 현업 적용 가능성 20점(실제 걷는 길 위에서 안내한다) · 문제 해결력 15점(도달 경로를 실측 도로망으로)

## 무엇인가

CCTV 23대를 모두 감싸는 범위(+900m)의 **보행 가능 도로망**이다. OpenStreetMap 을 OSMnx 로 받아
`walk` 네트워크로 뽑았다. 대시보드(`docs/index.html`)의 **APF 혼잡장 + 혼잡 회피 보행 경로**가 이걸 쓴다.

| 파일 | 내용 |
| :-- | :-- |
| `download_walk_network.py` | 재생성 스크립트 (핸드오프 원본 그대로, 수정 없음) |
| `requirements.txt` | 재생성에만 필요한 의존성. 평소 실행에는 필요 없다 |
| `../docs/data/routing/walk_graph.json` | 산출물. 노드 9,219 · 간선 26,042 · 총 연장 1,486km(방향별) · 원본 5.95MB(gzip 전송 시 775KB) |

## 재생성

```bash
.venv/bin/pip install -r routing/requirements.txt   # osmnx·geopandas — 무겁다
.venv/bin/python routing/download_walk_network.py
```

Overpass API 를 때리므로 몇 분 걸리고 네트워크가 필요하다. `routing/cache/` 와 `data/pedestrian/` 는
중간 산출물이라 git 에서 제외한다(`.gitignore`). 스크립트는 `docs/data/cams.json` 의 카메라 좌표로
bbox 를 잡으므로, **카메라 목록이 바뀌면 다시 돌려야 한다.**

## 핸드오프에 없던 파일 3종과 처리

스크립트는 산출물 5개를 쓰지만 핸드오프에는 `walk_graph.json` 하나만 있었다.

| 없던 파일 | 처리 |
| :-- | :-- |
| `walk_network.geojson` | **파일로 싣지 않는다.** 원래 `index.html` 이 지도 로드 시 이걸 바로 받는데(eager), 같은 지오메트리가 `walk_graph.json` 에 이미 들어 있어 **모든 방문자가 5MB를 두 번 받는 꼴**이 된다. 경로 계산으로 그래프를 받은 뒤 브라우저가 표시용 GeoJSON 을 만들도록 바꿨다(`walkLayerSync()`). 추가 전송량 0 |
| `walk_graph_stats.json` | 어디서도 읽지 않는 참고용이라 생략. 필요하면 재생성으로 나온다 |
| `yeouido_walk.graphml` · `.gpkg` | GIS 도구용 중간 산출물. `data/pedestrian/` 이라 원래도 git 제외 대상 |

## 라이선스

지도 데이터는 **© OpenStreetMap contributors, ODbL**. `docs/index.html` 푸터에 표기했다.
파생물을 배포할 때 같은 표기를 유지해야 한다.

## 알아둘 것

- `walk_graph.json` 은 **경로 찾기를 누를 때만** 받는다(lazy). 첫 지도 클릭 시 미리 받기를 시작한다.
- 브라우저 비용 측정(맥 데스크톱, Node/V8): JSON 파싱 22ms · 그래프 구성 17ms · A* 5ms. 모바일은 몇 배로 보면 된다.
- 경로 탐색은 2단계다. ① 보행로·횡단보도만(`routeStrict`) 쓰는 연결 성분에서 찾고 ② 실패하면 OSM 보행 가능망 전체로 넓힌다. 화면 상태줄에 어느 쪽인지 표시된다.
- 비용은 `거리 × (1 + 1.25 × 혼잡위험)` 이다. 가중치 1.25 와 APF 반경 σ=220m 는 **핸드오프 작성자의 추정치**이고 출처가 붙어 있지 않다 — 발표에서 근거를 물으면 그렇게 답해야 한다.
- 실측 경로가 직선보다 얼마나 도는지: 이벤트광장→여의도역이 직선 1,109m 인데 실제 보행 경로는 **1,820m(1.64배)** 다. 모델의 우회계수 `DETOUR = 1.3`(`src/nowcast.py`)보다 크다. 이 그래프로 우회계수를 실측 보정할 수 있다 — 아직 안 했다.
