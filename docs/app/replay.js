/* 발행 스냅샷 재생 — 관람객(go.html)·운영(index.html) 화면이 `?at=YYYYMMDDTHHMM` 이면 그 시각 발행분을 그대로 그린다.
 *
 * 작성 2026-09-06 (Task 12). 검증: tests/replay_spec.mjs (pytest tests/test_replay.py 가 node 로 실행)
 *
 * 규칙
 *   - 재계산하지 않는다. 화면은 `data/replay/<date>/<hhmm>.json`(= 그 시각 latest.json 재조립본)을 latest.json 대신 읽는다.
 *   - 시계는 재생 시각으로 묶는다. 두 화면의 `Date.now()` 는 전부 `NOW()` 를 지나야 한다 — 하나라도 실제 시계를 보면
 *     "12시간 넘게 오래됨 → 사전 예측표" 폴백이 튀어 재생이 사전표로 바뀐다 (tests/test_replay.py 가 잔류를 센다).
 *   - now 는 로컬 naive 시각이다. 발행 스냅샷의 ts("2026-09-05T22:06:53")도 zone 없이 저장돼 board.js ageMin 이 로컬로 읽는다.
 *     +09:00 을 붙이면 KST 밖 기기에서 나이가 시차만큼 튄다.
 *   - 재생 중엔 localStorage 저장·cctv_latest 덮어쓰기·자동 갱신·위치 권한을 끈다 (각 화면의 load() 가 REPLAY 를 본다).
 * DOM 을 만지는 건 mount() 하나 — 나머지는 순수 함수라 node 로 검증한다. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Replay = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function parse(search) {
    var m = /(?:^|[?&])at=(\d{8})T(\d{4})(?:&|$)/.exec(search || "");
    if (!m) return null;
    var date = m[1], hhmm = m[2];
    var y = +date.slice(0, 4), mo = +date.slice(4, 6), d = +date.slice(6, 8), h = +hhmm.slice(0, 2), mi = +hhmm.slice(2, 4);
    if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59) return null;
    var now = new Date(y, mo - 1, d, h, mi, 0, 0).getTime();
    if (!isFinite(now)) return null;
    return { at: date + "T" + hhmm, date: date, hhmm: hhmm, now: now,
             label: date.slice(0, 4) + "-" + date.slice(4, 6) + "-" + date.slice(6, 8) + " " + hhmm.slice(0, 2) + ":" + hhmm.slice(2, 4) };
  }
  function file(r) { return "data/replay/" + r.date + "/" + r.hhmm + ".json"; }
  function index(r) { return "data/replay/" + r.date + "/index.json"; }
  function href(page, at) { return page + "?at=" + at; }
  function neighbors(chips, hhmm) {
    var i = -1, k;
    for (k = 0; k < chips.length; k++) if (chips[k].at === hhmm) { i = k; break; }
    return { prev: i > 0 ? chips[i - 1].at : null, next: i >= 0 && i < chips.length - 1 ? chips[i + 1].at : null };
  }

  /** 재생 배너 — 화면 위에 얹는다. 스타일은 여기서 인라인으로 (두 화면이 같은 모습, CSS 손대지 않음). */
  function mount(page, r) {
    if (!r || typeof document === "undefined") return null;
    var bar = document.createElement("div");
    bar.id = "replay-bar";
    bar.setAttribute("style", "position:fixed;left:0;right:0;top:0;z-index:9000;display:flex;align-items:center;gap:10px;flex-wrap:wrap;"
      + "padding:8px 12px;background:rgba(25,31,40,.96);color:#fff;font:600 13px/1.3 'Pretendard Variable',Pretendard,-apple-system,system-ui,sans-serif;"
      + "box-shadow:0 2px 10px rgba(0,0,0,.25)");
    bar.innerHTML = '<span style="display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border-radius:999px;background:#F36F21;color:#fff">'
      + '<span aria-hidden="true">&#9654;</span>재생</span>'
      + '<span id="replay-label" style="font-variant-numeric:tabular-nums">' + r.label + ' 발행분 그대로</span>'
      + '<span id="replay-chips" style="display:inline-flex;gap:6px;flex-wrap:wrap;margin-left:auto"></span>'
      + '<a href="' + page + '" style="color:#B0B8C1;text-decoration:underline;margin-left:6px">실시간으로</a>';
    document.body.appendChild(bar);
    document.body.style.paddingTop = (bar.offsetHeight || 40) + "px";
    var chipsEl = bar.querySelector("#replay-chips"), labelEl = bar.querySelector("#replay-label");
    fetch(index(r), { cache: "no-store" }).then(function (x) { return x.ok ? x.json() : null; }).then(function (idx) {
      if (!idx || !idx.chips) return;
      var cur = null;
      idx.chips.forEach(function (c) { if (c.at === r.hhmm) cur = c; });
      if (cur && cur.label) labelEl.textContent = r.label + " · " + cur.label;
      var nb = neighbors(idx.chips, r.hhmm);
      var mk = function (txt, at, on) {
        var a = document.createElement(at ? "a" : "span");
        if (at) a.href = href(page, r.date + "T" + at);
        a.textContent = txt;
        a.setAttribute("style", "display:inline-block;padding:4px 9px;border-radius:8px;font:600 12px/1.2 inherit;color:" + (on ? "#191F28" : "#fff")
          + ";background:" + (on ? "#fff" : "rgba(255,255,255,.12)") + ";text-decoration:none" + (at ? "" : ";opacity:.35"));
        return a;
      };
      chipsEl.appendChild(mk("◀", nb.prev, false));
      idx.chips.forEach(function (c) { chipsEl.appendChild(mk(c.at.slice(0, 2) + ":" + c.at.slice(2), c.at, c.at === r.hhmm)); });
      chipsEl.appendChild(mk("▶", nb.next, false));
    }).catch(function () {});
    return bar;
  }

  return { parse: parse, file: file, index: index, href: href, neighbors: neighbors, mount: mount };
});
