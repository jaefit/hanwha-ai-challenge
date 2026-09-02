/* 출구 판정 규칙 — 관람객 화면(go.html)과 운영 화면(index.html)이 같은 기준으로 말하게 하는 공용 모듈.
 *
 * 작성 2026-09-02. 검증: tests/board_spec.mjs (pytest tests/test_board.py 가 node 로 실행)
 *
 * 왜 나눴나
 *   화면 하나가 관람객과 운영을 같이 상대하고 있었다. 관람객에게 α·유출 인원 수·가우시안 과정 회귀는 쓸모가 없고,
 *   운영에는 그것들이 더 필요하다. 화면을 나누면 각자 자기 일을 하는데, **판정 규칙이 두 벌이 되면 같은 데이터가
 *   두 화면에서 다른 등급으로 보인다.** 그래서 규칙만 여기로 뺐다. DOM 을 만지지 않는 순수 함수다.
 *
 * 결함 대장에서 여기서 닫는 것
 *   M2 결손 ≠ 통제 — `load == null` 을 통제로 렌더하면 "무정차 통과 · 여의도역으로"가 결손에도 뜬다. 나눠서 준다.
 *   M6 사전값을 측정값처럼 — 관측 없는 α=1.00 은 값이 아니라 기본값이다. 라벨에서 구분한다.
 *   H2 통제 문구 단정 금지 — 20시에 "무정차"라고 단정하면 실제로 탈 수 있는 사람을 1.5km 보낸다. 반대로
 *      "정차한다"는 더 위험하다(2024·2025 실적은 19시부터 하차 0). 공지 시각과 예년 이력을 같이 준다.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Board = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // dk = data/latest.json 의 exits 키. index.html 의 EXITS 와 같은 목록이다.
  var EXITS = [
    { k: "gukhoe", dk: "국회의사당(9)", name: "국회의사당(9)", desc: "9호선 · 당산·김포 방면", est: true, ll: [37.5281, 126.9174], sh: "국회", lc: "#BDB092" },
    { k: "mapo", dk: "마포역 도보(마포대교)", name: "마포역 도보", desc: "마포대교 보행로 → 5호선 마포역", est: true, ll: [37.5391, 126.9459], sh: "마포역", lc: "#4B5563" },
    { k: "yd9", dk: "여의도(9)", name: "여의도(9)", desc: "9호선 · 남·남동(동작·강남 방면)", est: true, ll: [37.5206, 126.9262], sh: "여의도(9)", lc: "#BDB092" },
    { k: "saet", dk: "샛강(9)", name: "샛강(9)", desc: "9호선 · 신림선 환승", est: true, ll: [37.5172, 126.9287], sh: "샛강", lc: "#BDB092" },
    { k: "naru", dk: "여의나루(5)", name: "여의나루(5)", desc: "5호선 · 북행·동행", est: false, ll: [37.5271, 126.9327], sh: "여의나루", lc: "#996CAC" },
    { k: "singil", dk: "신길(1·5)", name: "신길(1·5)", desc: "1·5호선 · 도보 약 58분(추정) · 분산 출구", est: true, ll: [37.5170, 126.9137], sh: "신길", lc: "#0052A4" },
    { k: "yd5", dk: "여의도(5)", name: "여의도(5)", desc: "5호선 · 서행(신길·영등포 방면)", est: false, ll: [37.5222, 126.9238], sh: "여의도(5)", lc: "#996CAC" },
  ];

  // 수집 시작 전 폴백 — 2024·2025 실적 × α=1 (index.html 과 같은 값)
  var FALLBACK = {
    "20": { gukhoe: .10, mapo: .11, yd9: .30, saet: .35, singil: .53, yd5: .79, naru: null },
    "21": { gukhoe: .16, mapo: .17, yd9: .48, saet: .56, naru: .74, singil: .84, yd5: .85 },
    "22": { gukhoe: .08, mapo: .09, yd9: .24, saet: .28, naru: .37, yd5: .43, singil: .43 },
  };

  var CLOSED_NOTE = {
    "20": "공지 기준 20:40부터 통제 · 예년엔 조기 무정차 — 현장 확인",
    "21": "21:40 해제 예정 · 그전까지는 여의도역으로",
    "default": "무정차 통과 · 여의도역으로",
  };

  var PLANS = [
    { dir: "W", title: "서쪽", where: "영등포·강서·양천·구로·부천·인천·김포", share: "귀가 38%",
      items: ["신길역까지 걸어 1·5호선 — 여의도역보다 부하 낮음", "여의도역 5호선 서행 — 21시 전후 가장 붐빔", "여의도환승센터 버스 (20~22시 집중투입)"] },
    { dir: "NW", title: "북서쪽", where: "마포·서대문·은평·고양", share: "13%",
      items: ["마포대교 보행로로 건너 마포역 5호선 — 줄 없음", "여의나루 5호선 북행 — 20:40~21:40 통제, 그 뒤"] },
    { dir: "NE", title: "북동쪽", where: "용산·종로·중구·성동·강북권", share: "17%",
      items: ["여의나루 5호선 동행 — 20:40~21:40 통제, 그 뒤", "여의도역 5호선 동행 — 통제 시간대 대체"] },
    { dir: "S", title: "남·남동쪽", where: "동작·관악·강남·서초·송파", share: "19%",
      items: ["국회의사당역 9호선 — 부하 가장 낮음", "샛강역 9호선 — 신림선 환승", "여의도역 9호선 — 급행 정차, 가장 붐빔"] },
  ];

  var STALE_MIN = 12 * 60;   // index.html 과 같은 기준: 12시간 넘으면 사전 예측표로 물러난다

  /** 부하율 → 서울시 4단계. index.html 의 LV 와 경계가 같아야 한다(tests/test_board.py 가 대조). */
  function grade(load) {
    return load >= 1 ? "심각" : load >= 0.8 ? "경계" : load >= 0.5 ? "주의" : "여유";
  }

  function closedNote(hour) {
    return CLOSED_NOTE[String(hour)] || CLOSED_NOTE.default;
  }

  function ageMin(ts, now) {
    if (!ts) return null;
    var t = Date.parse(String(ts).replace(" ", "T"));
    if (!isFinite(t)) return null;
    return Math.max(0, Math.round(((now == null ? Date.now() : now) - t) / 60000));
  }

  function isStale(ts, now) {
    var a = ageMin(ts, now);
    return a != null && a > STALE_MIN;
  }

  /** 관측이 있을 때만 α 를 값으로 말한다. 사전 모드의 1.00 은 측정이 아니라 기본값이다 (M6). */
  function alphaLabel(forecast) {
    var f = forecast || {};
    if (f.prior) return "사전값 " + Number(f.alpha == null ? 1 : f.alpha).toFixed(2) + " (관측 전)";
    if (f.alpha == null) return "—";
    return Number(f.alpha).toFixed(2);
  }

  function waitNote(load, waitMin) {
    if (waitMin > 0) return "대기 ~" + waitMin + "분(추정)";
    if (load >= 0.8) return "줄 길어짐 — 그 시간 안엔 탐";
    if (load >= 0.5) return "줄 서되 그 시간 안에 탐";
    return "줄 거의 없음";
  }

  function fallbackExits() {
    var out = {};
    EXITS.forEach(function (e) {
      out[e.dk] = {};
      Object.keys(FALLBACK).forEach(function (h) {
        var l = FALLBACK[h][e.k];
        out[e.dk][h] = { load: l, closed: l == null, estimated_capacity: e.est };
      });
    });
    return out;
  }

  /**
   * 한 시간대의 출구를 열림·통제·결손으로 나눠 준다.
   *   open    : 부하율 오름차순. grade·note·load 포함
   *   closed  : 운행 통제 (closed === true). 시간대별 문구
   *   missing : 값이 없어 판단 못 하는 곳. **통제로 말하지 않는다** (M2)
   *   mode    : live | prior | fallback
   */
  function rank(forecast, hour) {
    var fc = forecast || {}, ex = fc.exits || {}, mode = "live", hours = null;
    if (!Object.keys(ex).length) { ex = fallbackExits(); mode = "fallback"; hours = Object.keys(FALLBACK); }
    else if (fc.prior) mode = "prior";
    var h = String(hour);
    var open = [], closed = [], missing = [];
    EXITS.forEach(function (e) {
      var row = ex[e.dk];
      if (!row) return;
      var c = row[h] || row[Number(h)] || {};
      var est = c.estimated_capacity == null ? e.est : c.estimated_capacity;
      var base = { dk: e.dk, key: e.k, name: e.name, desc: e.desc, sh: e.sh, ll: e.ll, lc: e.lc, estimated: est };
      if (c.closed === true) {
        closed.push(Object.assign({}, base, { note: closedNote(h) }));
      } else if (c.load == null) {
        missing.push(Object.assign({}, base, { note: "값을 받지 못했다 — 다른 출구를 보라" }));
      } else {
        open.push(Object.assign({}, base, {
          load: c.load, grade: grade(c.load), waitMin: c.wait_min || 0,
          note: waitNote(c.load, c.wait_min || 0),
          loadLo: c.load_lo == null ? null : c.load_lo, loadHi: c.load_hi == null ? null : c.load_hi,
        }));
      }
    });
    open.sort(function (a, b) { return a.load - b.load; });
    var modeNote = mode === "fallback"
      ? "실시간 수집 전 — 2024·2025 실적 기준"
      : mode === "prior" ? "사전 예측 · 2024·2025 출발지 구성 기반" : "실시간 반영";
    return { open: open, closed: closed, missing: missing, mode: mode, modeNote: modeNote, hours: hours || Object.keys(FALLBACK) };
  }

  /** 지금 시각에 맞는 기본 탭. 축제 창(19~23시) 밖이면 21시. */
  function defaultHour(now) {
    var h = (now == null ? new Date() : new Date(now)).getHours();
    return (h >= 19 && h <= 23) ? String(h) : "21";
  }

  return {
    EXITS: EXITS, FALLBACK: FALLBACK, PLANS: PLANS, CLOSED_NOTE: CLOSED_NOTE, STALE_MIN: STALE_MIN,
    grade: grade, closedNote: closedNote, ageMin: ageMin, isStale: isStale,
    alphaLabel: alphaLabel, waitNote: waitNote, rank: rank, defaultHour: defaultHour,
  };
});
