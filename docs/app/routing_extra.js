/* 보행망 보완 간선 — OSM 에서 빠진 마포대교 보행 연결을 채운다.
 *
 * 작성 2026-09-02. 검증: tests/routing_spec.mjs (pytest tests/test_routing.py 가 node 로 실행)
 *
 * 왜 필요한가
 *   `docs/data/routing/walk_graph.json` 에는 **마포대교의 한강 횡단 구간이 없다.** 다리 축(마포대교 남단 구역 →
 *   마포역) ±150m 안에서 위도 37.531~37.536, 즉 강을 실제로 건너는 약 550m 에 노드가 0개다. 남아 있는 데크 후보
 *   간선은 전부 `trunk`·`trunk_link` 이고 `index.html` 의 `routeAllowed()` 가 `trunk` 를 거른다.
 *
 *   그 결과 이벤트광장 → 마포역 경로가 **원효대교를 돌아 4,024m** 로 나왔다. 직선은 1,351m 다
 *   (서울시 한강교량 제원 마포대교 1,390m 과 부합). 화면은 출구 보드에서 "마포대교 보행로로 건너 마포역"을
 *   안내하는데 길찾기는 그 길을 재현하지 못하는, 서로 다른 말을 하는 상태였다.
 *
 * 무엇을 넣는가
 *   마포대교에는 **상시 인도**가 있다. 축제 임시 조치와 무관하게 걸어서 건널 수 있으므로, 빠진 연결을 채우는 것은
 *   축제일 규칙이 아니라 데이터 결손 보정이다. 양방향 보행 간선 1쌍만 넣는다.
 *
 *   길이는 두 접속 노드의 직선거리에서 온 **하한 근사**다. 실제 보행은 둔치에서 데크로 오르는 접근로가 더해져
 *   이보다 길다. 과소평가는 도보 시간을 짧게 보이게 하므로 화면 문구에 근사임을 밝힌다.
 *
 * 넣지 않은 것 (2026-09-02 판단)
 *   ① **축제일 하위 1개 차로 추가 보행로** — 2025 실적이다(경찰·서울시: "행사 종료 후 마포대교의 경우 하위 1개
 *      차로를 통제하는 방식으로 추가 보행로를 확보"). 2026 공지에는 아직 없어 넣지 않는다. 폭이 늘면 혼잡이
 *      낮아지는 방향이라, 넣지 않는 쪽이 안전측이다.
 *   ② **원효대교 차단** — 2026 공지의 "전면 통제"는 차량 통제 발표다. 2025·2024 에는 인도 통제를 "원효대교
 *      마포대교 방면 인도 17:00~20:30 보행 제한"처럼 따로 명시했는데 2026 공지에는 그런 문구가 없다.
 *      보행 통행을 막을 근거가 없으므로 차단하지 않는다.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RoutingExtra = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // 접속 노드 — walk_graph.json 에 실재하는 id 다 (tests/routing_spec.mjs 가 확인한다).
  //   남단 13357347387 (37.52911, 126.93331) 여의도 북안. 다리 축에서 236m. 허용 3 · 보행로 전용 3 간선.
  //   북단 10057773580 (37.53684, 126.94379) 마포 남안. 다리 축에서 63m. 허용 4 · 보행로 전용 2 간선. 마포역까지 직선 307m.
  //   두 점의 중점은 축에서 75m. 북단은 **마포역에서 도달 가능한 노드 중 다리 축을 따라 가장 남쪽**이다 —
  //   더 남쪽 노드(예: 5168879174)는 붙어 있는 간선이 전부 trunk 라 routeAllowed 를 통과하지 못해 고립돼 있다.
  var SOUTH = { id: "13357347387", ll: [126.9333062, 37.5291063] };
  var NORTH = { id: "10057773580", ll: [126.9437900, 37.5368400] };

  var BASIS = "마포대교 상시 인도 — OSM 보행망에 횡단 구간이 없어 보완한 간선. 길이는 접속 노드 직선거리 기준 하한 근사(실제는 둔치→데크 접근로만큼 더 길다). 축제일 하위 1개 차로 추가 보행로(2025 실적, 2026 미공지)는 반영하지 않았다.";

  function distanceM(a, b) {
    var lat = (a[1] + b[1]) * Math.PI / 360;
    return Math.hypot((a[0] - b[0]) * 111320 * Math.cos(lat), (a[1] - b[1]) * 111320);
  }

  function edge(from, to) {
    return {
      u: from.id, v: to.id, k: 0,
      m: Math.round(distanceM(from.ll, to.ll) * 10) / 10,
      h: "footway",          // routeAllowed·routeStrict 를 모두 통과해야 1단계(보행로 전용)에서도 쓰인다
      f: "yes",              // foot=yes
      s: null, x: null, a: null, sv: null,
      b: "yes",              // 교량
      t: null,
      g: [from.ll.slice(), to.ll.slice()],
      mapo_walk: true,       // 화면·테스트가 이 간선을 식별하는 표시
      basis: BASIS,
    };
  }

  /** 보완 간선 목록(양방향). 호출할 때마다 새 객체를 돌려준다. */
  function extraEdges() {
    return [edge(SOUTH, NORTH), edge(NORTH, SOUTH)];
  }

  /** 원본 배열을 건드리지 않고 보완 간선을 더한 새 배열. */
  function withExtraEdges(edges) {
    return (edges || []).concat(extraEdges());
  }

  return {
    SOUTH: SOUTH,
    NORTH: NORTH,
    BASIS: BASIS,
    distanceM: distanceM,
    extraEdges: extraEdges,
    withExtraEdges: withExtraEdges,
  };
});
