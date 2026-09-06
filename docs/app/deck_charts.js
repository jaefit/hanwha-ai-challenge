/* 피치 덱 차트 모듈 — 숫자는 docs/deck/*.json 에서만 읽는다. 여기서 다시 계산하지 않는다.
   2026-09-06: Claude Design 「Pitch Deck v2」 의 charts.js 를 그대로 들여왔다(1920 무대 · 토스풍 팔레트).
   이 파일은 docs/app/ 에 있으므로 데이터 경로는 ../deck/ 다. */
export function countUp(slide) {
  [].slice.call(slide.querySelectorAll(".cu")).forEach(function (el) {
    var v = parseFloat(el.getAttribute("data-v")), d = +(el.getAttribute("data-d") || 0);
    if (CHART_REDUCE) { el.textContent = v.toFixed(d); return; }
    if (el.__raf) cancelAnimationFrame(el.__raf);
    var t0 = null;
    function tick(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / 1800); p = 1 - Math.pow(1 - p, 3);
      el.textContent = (v * p).toFixed(d);
      el.__raf = p < 1 ? requestAnimationFrame(tick) : null;
    }
    el.__raf = requestAnimationFrame(tick);
  });
}
/* ── 차트 공통 ── */
var CHART_CACHE = {}, CHART_REDUCE = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
function chartData(name) {
  if (!CHART_CACHE[name]) CHART_CACHE[name] = fetch(new URL("../deck/" + name + ".json", import.meta.url)).then(function (r) { return r.json(); });
  return CHART_CACHE[name];
}
var PAL = {"--bg":"#FFFFFF","--sheet":"#FFFFFF","--card":"#F2F4F6","--ink":"#191F28","--ink-2":"#4E5968","--sub":"#8B95A1","--rule":"#E5E8EB","--line":"#E5E8EB","--accent":"#F36F21","--live":"#3182F6","--offline":"#D0342C","--g1":"#2E7D5B","--g2":"#8A6400","--g3":"#B0521C","--g4":"#B3352B","--c1":"#F36F21","--c2":"#3182F6"};
function cssVar(k) { return PAL[k] || "#000"; }
var FS = 1.9;   // 1920px 무대 기준 라벨 배율
function hex(s) { s = s.replace("#", ""); return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)]; }
function fitCanvas(cv) {
  var r = { width: cv.offsetWidth, height: cv.offsetHeight }, d = window.devicePixelRatio || 1;
  cv.width = Math.max(1, Math.round(r.width * d));
  cv.height = Math.max(1, Math.round(r.height * d));
  var x = cv.getContext("2d");
  x.setTransform(d, 0, 0, d, 0, 0);
  x.clearRect(0, 0, r.width, r.height);
  return { ctx: x, w: r.width, h: r.height };
}
function animate(cv, ms, draw) {
  if (cv.__raf) cancelAnimationFrame(cv.__raf);
  if (CHART_REDUCE) { draw(1); return; }
  var t0 = null;
  function tick(ts) {
    if (t0 === null) t0 = ts;
    var p = Math.min(1, (ts - t0) / ms);
    draw(1 - Math.pow(1 - p, 3));
    cv.__raf = p < 1 ? requestAnimationFrame(tick) : null;
  }
  cv.__raf = requestAnimationFrame(tick);
}
function axes(c, w, h, pad) {
  c.strokeStyle = cssVar("--rule"); c.lineWidth = 1;
  c.beginPath(); c.moveTo(pad.l, pad.t); c.lineTo(pad.l, h - pad.b); c.lineTo(w - pad.r, h - pad.b); c.stroke();
}
function label(c, txt, x, y, col, align, size, font) {
  c.fillStyle = col; c.textAlign = align || "left"; c.textBaseline = "middle";
  c.font = ((size || 11) * FS) + "px " + (font === "sans" ? "'Pretendard Variable', Pretendard, sans-serif" : "'IBM Plex Mono', ui-monospace, monospace");
  c.fillText(txt, x, y);
}
function roundRect(c, x, y, w, h, r) {
  r = Math.min(r, h / 2, Math.max(0, w) / 2);
  c.beginPath(); c.moveTo(x, y); c.lineTo(x + w - r, y); c.quadraticCurveTo(x + w, y, x + w, y + r);
  c.lineTo(x + w, y + h - r); c.quadraticCurveTo(x + w, y + h, x + w - r, y + h); c.lineTo(x, y + h); c.closePath();
}

var CHARTS = {};
/* ① 출구 7개 실측 비중 — 가로 막대, 비중 내림차순 (exit_bars.json) */
function drawExits(cv, d) {
  var rows = d.exits, max = rows[0].share;
  animate(cv, 1600, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var pad = { l: Math.min(260, w * 0.36), r: 100, t: 4, b: 4 }, rh = (h - pad.t - pad.b) / rows.length;
    rows.forEach(function (r, i) {
      var y = pad.t + rh * i + rh * 0.2, bh = rh * 0.6;
      var bw = (w - pad.l - pad.r) * (r.share / max) * p;
      label(c, r.name, pad.l - 10, y + bh / 2, cssVar("--ink-2"), "right", 12, "sans");
      c.fillStyle = cssVar("--c1"); roundRect(c, pad.l, y, bw, bh, 8); c.fill();
      label(c, Math.round(r.share * 100 * p) + "%", pad.l + bw + 8, y + bh / 2, cssVar("--ink"), "left", 12);
    });
  });
}
CHARTS.exits = ["exit_bars", drawExits];

/* ② 피더 12곳 방사형 — 방위 실제, 거리 = 소요시간, 원 = 귀속 인원 (feeder_map.json). 보고서 그림 1 과 같은 규칙.
   서쪽 20° 쐐기에 역 5곳이 몰리므로(273~293°) 같은 쪽 라벨은 세로로 밀어낸다 — 점은 제자리, 라벨만. */
function drawRadial(cv, d, slide, fig) {
  var host = fig.querySelector(".radial"); host.innerHTML = "";
  var NS = "http://www.w3.org/2000/svg", S = 560, C = S / 2;
  var svg = document.createElementNS(NS, "svg"); svg.setAttribute("viewBox", "-160 20 880 530"); svg.setAttribute("style", "width:100%;height:100%;display:block");
  function el(t, a, txt) {
    var e = document.createElementNS(NS, t);
    for (var k in a) e.setAttribute(k, a[k]);
    if (txt != null) e.textContent = txt;
    svg.appendChild(e); return e;
  }
  var R = function (min) { return 40 + min * 6.6; };
  var items = [], labels = [];
  d.rings_min.forEach(function (m, i) {
    items.push([el("circle", { cx: C, cy: C, r: R(m), fill: "none", stroke: "#B0B8C1", "stroke-width": 1.8, "stroke-dasharray": "6 6" }), i * 110]);
    items.push([el("text", { x: C + 8, y: C - R(m) - 8, fill: "#6B7684", "font-size": 15, "font-family": "IBM Plex Mono, monospace" }, m + "분"), i * 110 + 60]);
  });
  var maxP = d.feeders[0].persons;
  d.feeders.forEach(function (f, i) {
    var a = f.bearing_deg * Math.PI / 180, r = R(f.travel_min);
    var x = C + r * Math.sin(a), y = C - r * Math.cos(a);
    items.push([el("line", { x1: C, y1: C, x2: x, y2: y, stroke: cssVar("--c1"), "stroke-width": 1.4, "stroke-opacity": .45 }), 380 + i * 60]);
    items.push([el("circle", { cx: x, cy: y, r: 5 + Math.sqrt(f.persons / maxP) * 10, fill: cssVar("--c1"), "fill-opacity": .9, stroke: cssVar("--sheet"), "stroke-width": 2 }), 440 + i * 60]);
    // 서쪽 밀집(273~293°) 라벨은 왼쪽 여백에 정렬해 한 줄 목록처럼, 나머지는 점 옆
    var west = f.bearing_deg > 268 && f.bearing_deg < 298;
    var right = x >= C;
    var tx = west ? -8 : (right ? x + 16 : x - 16), anchor = west ? "end" : (right ? "start" : "end");
    var t1 = el("text", { x: tx, y: y, fill: cssVar("--ink"), "font-size": 19, "font-weight": 700, "font-family": "Pretendard Variable, sans-serif", "text-anchor": anchor }, f.name);
    var t2 = el("text", { x: tx, y: y, fill: cssVar("--sub"), "font-size": 14, "font-family": "IBM Plex Mono, monospace", "text-anchor": anchor }, f.travel_min + "분 · " + f.persons.toLocaleString("en-US") + "명");
    var lead = west ? el("line", { x1: x - 8, y1: y, x2: 0, y2: y, stroke: cssVar("--rule"), "stroke-width": 1, "stroke-dasharray": "2 3" }) : null;
    items.push([t1, 480 + i * 60]); items.push([t2, 480 + i * 60]); if (lead) items.push([lead, 480 + i * 60]);
    labels.push({ group: west ? "w" : (right ? "r" : "l"), y: y, t1: t1, t2: t2, lead: lead, gap: 44 });
  });
  ["w", "r", "l"].forEach(function (g) {
    var L = labels.filter(function (l) { return l.group === g; }).sort(function (a, b) { return a.y - b.y; });
    for (var k = 1; k < L.length; k++) if (L[k].y - L[k - 1].y < L[k].gap) L[k].y = L[k - 1].y + L[k].gap;
    L.forEach(function (l) {
      l.t1.setAttribute("y", l.y - 5); l.t2.setAttribute("y", l.y + 15);
      if (l.lead) l.lead.setAttribute("y2", l.y + 4);
    });
  });
  el("circle", { cx: C, cy: C, r: 9, fill: cssVar("--ink") });
  el("text", { x: C, y: C + 32, fill: cssVar("--ink"), "font-size": 18, "font-weight": 800, "text-anchor": "middle" }, d.center.name);
  host.appendChild(svg);
  items.forEach(function (it) {
    it[0].style.opacity = CHART_REDUCE ? 1 : 0;
    if (!CHART_REDUCE) it[0].style.transition = "opacity .35s ease " + (it[1] / 1000) + "s";
  });
  if (!CHART_REDUCE) requestAnimationFrame(function () { requestAnimationFrame(function () { items.forEach(function (it) { it[0].style.opacity = 1; }); }); });
}
CHARTS.radial = ["feeder_map", drawRadial];

/* ③ 피더 선행 — 보고서 그림 2 방식: 두 곡선을 그대로 두고, 같은 무리가 1시간 뒤 도착하는 짝을 화살표로 가리킨다 */
function drawFeeder(cv, d, slide) {
  var y2025 = d.years["2025"], hours = d.hours;
  var xs = hours.map(function (h) { return y2025.x[h] || 0; });
  var ys = hours.map(function (h) { return y2025.y[h] || 0; });
  var max = Math.max.apply(null, xs.concat(ys)) * 1.22;
  var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
  var pad = { l: 80, r: 250, t: 30, b: 46 };
  var px = function (i) { return pad.l + (w - pad.l - pad.r) * i / (hours.length - 1); };
  var py = function (v) { return h - pad.b - (h - pad.t - pad.b) * v / max; };
  var rEl = slide.querySelector("[data-feeder-r]");
  if (rEl) rEl.textContent = "r " + y2025.r_lag1.toFixed(2) + " (1시간 뒤)";
  var pairs = [3, 5, 7];           // 13→14 · 15→16 · 17→18 시
  function arrow(x1, y1, x2, y2, col) {
    var ang = Math.atan2(y2 - y1, x2 - x1), L = 14;
    c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 3; c.setLineDash([]);
    c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke();
    c.beginPath(); c.moveTo(x2, y2);
    c.lineTo(x2 - L * Math.cos(ang - 0.45), y2 - L * Math.sin(ang - 0.45));
    c.lineTo(x2 - L * Math.cos(ang + 0.45), y2 - L * Math.sin(ang + 0.45));
    c.closePath(); c.fill();
  }
  animate(cv, 2400, function (p) {
    var out2 = fitCanvas(cv); c = out2.ctx; w = out2.w; h = out2.h;
    axes(c, w, h, pad);
    hours.forEach(function (hh, i) { if (hh % 2 === 0) label(c, hh + "시", px(i), h - pad.b + 12, cssVar("--sub"), "center", 10.5); });
    label(c, Math.round(max / 1000) + "천", pad.l - 6, pad.t + 4, cssVar("--sub"), "right", 10.5);
    function line(vals, col, dash) {
      c.strokeStyle = col; c.lineWidth = 4; c.setLineDash(dash || []); c.beginPath();
      vals.forEach(function (v, i) { if (v <= 0) return; var X = px(i), Y = py(v); i ? c.lineTo(X, Y) : c.moveTo(X, Y); });
      c.stroke(); c.setLineDash([]);
      vals.forEach(function (v, i) { if (v <= 0) return; c.fillStyle = col; c.beginPath(); c.arc(px(i), py(v), 5.5, 0, 6.284); c.fill(); });
    }
    var pl = Math.min(1, p / 0.45);
    c.save(); c.beginPath(); c.rect(pad.l - 8, 0, (w - pad.l - pad.r + 16) * pl, h); c.clip();
    line(xs, cssVar("--c1"));
    line(ys, cssVar("--c2"), [10, 7]);
    c.restore();
    label(c, "피더역 승차 (탄다)", px(8) + 14, py(xs[8]) - 6, cssVar("--c1"), "left", 11.5);
    label(c, "여의도 도착 (내린다)", px(9) + 14, py(ys[9]) + 6, cssVar("--c2"), "left", 11.5);
    if (p > 0.45) {
      pairs.forEach(function (i, k) {
        var pa = Math.min(1, Math.max(0, (p - 0.5 - k * 0.15) / 0.2));
        if (pa <= 0) return;
        var x1 = px(i) + 8, y1 = py(xs[i]) - 8, x2 = px(i + 1) - 8, y2 = py(ys[i + 1]) - 8;
        arrow(x1, y1, x1 + (x2 - x1) * pa, y1 + (y2 - y1) * pa, cssVar("--ink"));
      });
      if (p > 0.95) {
        var i = 7, mx = (px(i) + px(i + 1)) / 2, my = Math.min(py(xs[i]), py(ys[i + 1])) - 30;
        label(c, "정점 17시 → 18시 · 약 1시간 뒤", mx, my, cssVar("--ink"), "center", 11.5, "sans");
      }
    }
  });
}
CHARTS.feeder = ["feeder_lag", drawFeeder];

var APF_SD_MAX = Math.sqrt(0.125 + 0.125);   // index.html · 커널 varShort+varLong
var FIELD_STOPS = [[0, "--g1"], [0.6, "--g2"], [0.8, "--g3"], [1, "--g4"]];
/* index.html apfPalette 의 램프. 등급 밴드 안에서는 색을 유지하고 경계에서만 넘어간다 —
   선형 보간하면 u=0.35 가 초록+골드 = 올리브가 되어 등급과 어긋난다. */
function apfRamp() {
  var V = hex(cssVar("--g1")), J = hex(cssVar("--g2")), G = hex(cssVar("--g3")), S = hex(cssVar("--g4"));
  return [[0, V], [0.50, V], [0.63, J], [0.78, G], [0.92, S], [1, S]];
}
function rampHex(ramp, u) {
  u = Math.max(0, Math.min(1, u));
  for (var i = 0; i < ramp.length - 1; i++) {
    var a = ramp[i], b = ramp[i + 1];
    if (u >= a[0] && u <= b[0]) {
      var t = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 0;
      return [a[1][0] + (b[1][0] - a[1][0]) * t, a[1][1] + (b[1][1] - a[1][1]) * t, a[1][2] + (b[1][2] - a[1][2]) * t];
    }
  }
  return ramp[ramp.length - 1][1];
}
/* 등급 경계(0.6/0.8/1.0)를 그대로 칠한다 — 연속 보간하면 중간 올리브색으로 뭉개지고,
   무엇보다 제품이 말하는 단위(등급)와 그림이 어긋난다. field.js unitToGrade 와 같은 경계. */
function fieldColor(u) {
  var k = u >= 1 ? "--g4" : u >= 0.8 ? "--g3" : u >= 0.6 ? "--g2" : "--g1";
  return hex(cssVar(k));
}
/* ④ α 격자 사후분포 — 관측이 한 건씩 들어오며 종이 좁아진다 */
function drawAlpha(cv, d, slide) {
  var grid = d.grid, frames = d.frames, prior = d.prior_weights;
  var maxW = 0;
  frames.forEach(function (f) { f.weights.forEach(function (v) { if (v > maxW) maxW = v; }); });
  var nowEl = slide.querySelector("[data-alpha-now]");
  var lg = Math.log(grid[0]), rg = Math.log(grid[grid.length - 1]);
  animate(cv, 3000, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var pad = { l: 40, r: 20, t: 30, b: 46 };
    var px = function (a) { return pad.l + (w - pad.l - pad.r) * (Math.log(a) - lg) / (rg - lg); };
    var py = function (v) { return h - pad.b - (h - pad.t - pad.b) * v / maxW; };
    axes(c, w, h, pad);
    [0.5, 0.75, 1, 1.5, 2].forEach(function (a) { label(c, String(a), px(a), h - pad.b + 12, cssVar("--sub"), "center", 10.5); });
    function curve(ws, col, fill) {
      c.beginPath();
      ws.forEach(function (v, i) { var X = px(grid[i]), Y = py(v); i ? c.lineTo(X, Y) : c.moveTo(X, Y); });
      if (fill) { c.lineTo(px(grid[grid.length - 1]), h - pad.b); c.lineTo(px(grid[0]), h - pad.b); c.closePath(); c.fillStyle = fill; c.fill(); }
      c.strokeStyle = col; c.lineWidth = 2; c.stroke();
    }
    curve(prior, cssVar("--sub"), null);
    var fi = Math.min(frames.length - 1, Math.floor(p * (frames.length - 0.001)));
    var f = frames[fi];
    curve(f.weights, cssVar("--c1"), "rgba(243,111,33,.16)");
    // p10~p90 밴드와 중앙값
    c.fillStyle = "rgba(243,111,33,.10)";
    c.fillRect(px(f.alpha[0]), pad.t, px(f.alpha[2]) - px(f.alpha[0]), h - pad.t - pad.b);
    c.strokeStyle = cssVar("--c1"); c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(px(f.alpha[1]), pad.t); c.lineTo(px(f.alpha[1]), h - pad.b); c.stroke();
    label(c, "관측 " + f.n + "건 · " + f.label, w - pad.r, pad.t + 6, cssVar("--sub"), "right", 11.5);
    if (nowEl) nowEl.textContent = "α " + f.alpha[1].toFixed(3) + " [" + f.alpha[0].toFixed(2) + "~" + f.alpha[2].toFixed(2) + "]";
  });
}
function drawFieldCanvas(cv, d, slide) {
  var g = d.grid, nEl = slide.querySelector("[data-field-n]");
  var off = document.createElement("canvas");
  off.width = g.cols; off.height = g.rows;
  var octx = off.getContext("2d");
  animate(cv, 3200, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var fi = Math.min(d.frames.length - 1, Math.floor(p * (d.frames.length - 0.001)));
    var f = d.frames[fi];
    var img = octx.createImageData(g.cols, g.rows);
    for (var iy = 0; iy < g.rows; iy++) {
      for (var ix = 0; ix < g.cols; ix++) {
        var k = iy * g.cols + ix, u = f.mean[k] / d.scale, sd = f.sd[k] / d.scale;
        var col = fieldColor(u);
        // 위→아래 뒤집기: 격자는 위도가 커질수록 인덱스가 크고, 캔버스는 아래로 간다
        var o = ((g.rows - 1 - iy) * g.cols + ix) * 4;
        img.data[o] = col[0]; img.data[o + 1] = col[1]; img.data[o + 2] = col[2];
        // 불확실할수록 투명 = "모른다". sd 는 0.24~0.50 구간이라 그 폭에 맞춰 편다
        var fade = Math.max(0, Math.min(0.55, (sd - 0.24) / 0.26 * 0.55));
        img.data[o + 3] = Math.round(255 * (1 - fade));
      }
    }
    octx.putImageData(img, 0, 0);
    c.imageSmoothingEnabled = true;
    var sc = Math.min(w / g.cols, h / g.rows), dw = g.cols * sc, dh = g.rows * sc;
    var ox = (w - dw) / 2, oy = (h - dh) / 2;
    c.drawImage(off, ox, oy, dw, dh);
    d.observations.slice(0, f.n).forEach(function (o) {
      var X = ox + dw * (o.x[0] - g.x0) / (g.x1 - g.x0), Y = oy + dh * (1 - (o.x[1] - g.y0) / (g.y1 - g.y0));
      c.fillStyle = cssVar("--ink"); c.beginPath(); c.arc(X, Y, 6, 0, 6.284); c.fill();
      c.strokeStyle = cssVar("--sheet"); c.lineWidth = 2.5; c.stroke();
    });
    ["여의도한강공원", "63빌딩", "마포대교"].forEach(function (nm) {
      var o = null;
      d.observations.some(function (q) { if (q.name.indexOf(nm) >= 0) { o = q; return true; } return false; });
      if (!o) return;
      var X = ox + dw * (o.x[0] - g.x0) / (g.x1 - g.x0), Y = oy + dh * (1 - (o.x[1] - g.y0) / (g.y1 - g.y0));
      c.fillStyle = "rgba(255,255,255,.9)";
      var tw = nm.length * 20 + 16;
      c.fillRect(X + 10, Y - 15, tw, 30);
      label(c, nm, X + 18, Y, cssVar("--ink"), "left", 11, "sans");
    });
    var sdAvg = 0; for (var i = 0; i < f.sd.length; i++) sdAvg += f.sd[i];
    sdAvg = sdAvg / f.sd.length / d.scale;
    if (nEl) nEl.textContent = "관측 " + f.n + "대 · 평균 σ " + sdAvg.toFixed(2);
  });
}
/* ⑤ A* — 혼잡장 위에서 탐색이 번지고 경로가 뽑힌다.
   바탕은 혼잡장 패널과 같은 장이다(등급 배치는 예시). 두 그림을 잇는 게 요점 —
   "혼잡장을 만든다" 다음이 "그 장 위에서 길을 고른다" 이다. */
function drawRoute(cv, d, slide) {
  chartData("field_grid").then(function (fd) { drawRouteOn(cv, d, fd); })
    .catch(function () { drawRouteOn(cv, d, null); });
}
function drawRouteOn(cv, d, fd) {
  var fig = cv.parentNode, cvs = [].slice.call(fig.querySelectorAll("canvas"));
  var b = d.bbox, fcv = null;
  if (fd) {                                  // 장을 격자 크기 캔버스에 한 번만 그려 둔다 (패널이 공유)
    var fg = fd.grid, last = fd.frames[fd.frames.length - 1], ramp = apfRamp();
    fcv = document.createElement("canvas");
    fcv.width = fg.cols; fcv.height = fg.rows;
    var fx = fcv.getContext("2d"), fim = fx.createImageData(fg.cols, fg.rows), fp = fim.data;
    for (var iy = 0; iy < fg.rows; iy++) {
      for (var ix = 0; ix < fg.cols; ix++) {
        var k = iy * fg.cols + ix;
        var u = Math.max(0, Math.min(1, last.mean[k] / fd.scale));
        var conf = Math.max(0, 1 - (last.sd[k] / fd.scale) / APF_SD_MAX), cn = Math.min(1, conf / 0.15);
        var hot = Math.max(0, Math.min(1, (u - 0.3) / 0.7));
        var col = rampHex(ramp, u), o = (0.45 + 0.50 * hot) * (0.45 + 0.55 * cn);
        var j = ((fg.rows - 1 - iy) * fg.cols + ix) * 4;
        fp[j] = col[0] | 0; fp[j + 1] = col[1] | 0; fp[j + 2] = col[2] | 0;
        fp[j + 3] = Math.round(255 * Math.max(0, Math.min(1, o)) * 0.62);
      }
    }
    fx.putImageData(fim, 0, 0);
  }
  var S = d.routes.shortest, A = d.routes.avoiding, M = d.minutes || {};
  var fmt = function (m) { return m.toLocaleString("en-US"); };
  var TITLE = { shortest: "① 최단 — 봉우리를 통과", avoiding: "② 혼잡 회피 — 돌아간다", both: "③ 겹쳐 보기" };
  var STAT = {
    shortest: fmt(S.meters) + "m · " + M.shortest + "분",
    avoiding: A ? fmt(A.meters) + "m · " + M.avoiding + "분" : "",
    both: A ? "+" + fmt(A.meters - S.meters) + "m 더 걷고 " + (M.shortest - M.avoiding) + "분 빠르다" : "",
  };
  // 패널을 왼쪽부터 차례로 그린다 — 패널 i 는 p∈[i/2,(i+1)/2] 에서 자기 경로를 늘린다
  animate(cvs[0], 3600, function (p) {
    cvs.forEach(function (canvas, idx) {
      var mode = canvas.getAttribute("data-mode") || "both";
      var out = fitCanvas(canvas), c = out.ctx, w = out.w, h = out.h;
      var kx = Math.cos((b[1] + b[3]) / 2 * Math.PI / 180);
      var sx = (b[2] - b[0]) * kx, sy = b[3] - b[1];
      var TH = 84; var sc = Math.min((w - 16) / sx, (h - TH) / sy);
      var ox = (w - sx * sc) / 2, oy = TH + (h - TH - sy * sc) / 2;
      var X = function (lng) { return ox + (lng - b[0]) * kx * sc; };
      var Y = function (lat) { return oy + (b[3] - lat) * sc; };
      if (fcv) {
        var fg2 = fd.grid;
        var fsx = (b[0] - fg2.x0) / (fg2.x1 - fg2.x0) * fg2.cols, fsx1 = (b[2] - fg2.x0) / (fg2.x1 - fg2.x0) * fg2.cols;
        var fsy = (1 - (b[3] - fg2.y0) / (fg2.y1 - fg2.y0)) * fg2.rows, fsy1 = (1 - (b[1] - fg2.y0) / (fg2.y1 - fg2.y0)) * fg2.rows;
        c.imageSmoothingEnabled = true;
        c.drawImage(fcv, fsx, fsy, Math.max(1, fsx1 - fsx), Math.max(1, fsy1 - fsy), X(b[0]), Y(b[3]), X(b[2]) - X(b[0]), Y(b[1]) - Y(b[3]));
      }
      c.strokeStyle = cssVar("--line"); c.lineWidth = 1;
      c.beginPath();
      d.background_edges.forEach(function (e) { c.moveTo(X(e[0]), Y(e[1])); c.lineTo(X(e[2]), Y(e[3])); });
      c.stroke();
      var ph = Math.max(0, Math.min(1, p * 2 - idx));      // 이 패널의 진행도 (2패널)
      if (idx === 0 && d.visited) {                          // 탐색이 번지는 건 ① 에서만
        var vs = Math.floor(Math.min(1, ph / 0.55) * d.visited.length);
        c.fillStyle = "#C9C4BA";
        d.visited.slice(0, vs).forEach(function (q) { c.beginPath(); c.arc(X(q[0]), Y(q[1]), 2.4, 0, 6.284); c.fill(); });
      }
      if (d.hotspot) {                                       // 왜 돌아가는지 — 패널 모두
        var hr = d.hotspot.radius_m / 111320 * sc, hc = d.hotspot.center;
        c.beginPath(); c.arc(X(hc[0]), Y(hc[1]), Math.max(6, hr), 0, 6.284);
        c.fillStyle = "rgba(179,53,43,.22)"; c.fill();
        c.strokeStyle = cssVar("--g4"); c.lineWidth = 1.5; c.setLineDash([3, 3]); c.stroke(); c.setLineDash([]);
      }
      c.lineJoin = "round"; c.lineCap = "round";
      var rp = idx === 0 ? Math.max(0, (ph - 0.45) / 0.55) : ph;
      // 선은 인덱스가 아니라 **걷는 시간**에 비례해 자란다. 두 사람이 동시에 출발한 것처럼 —
      // 봉우리 안에서는 기어가고, 회피 경로는 먼저 도착한다.
      var total = function (r) { return r && r.times && r.times.length ? r.times[r.times.length - 1] : 0; };
      var clock = mode === "both" ? Math.max(total(S), total(A)) : (mode === "avoiding" ? total(A) : total(S));
      var tau = rp * clock;
      var path = function (r, col, wd, dash) {
        var co = r.coords, tm = r.times || [];
        var i = 0;
        while (i + 1 < co.length && tm[i + 1] <= tau) i++;
        var done = i >= co.length - 1 || tau >= total(r);
        c.beginPath();
        for (var k = 0; k <= i; k++) k ? c.lineTo(X(co[k][0]), Y(co[k][1])) : c.moveTo(X(co[k][0]), Y(co[k][1]));
        if (!done && tm.length) {                          // 다음 점까지 부분 진행 — 선이 뚝뚝 끊기지 않게
          var f = (tau - tm[i]) / Math.max(1e-6, tm[i + 1] - tm[i]);
          c.lineTo(X(co[i][0] + (co[i + 1][0] - co[i][0]) * f), Y(co[i][1] + (co[i + 1][1] - co[i][1]) * f));
        }
        c.setLineDash(dash || []);
        c.strokeStyle = "rgba(255,255,255,.92)"; c.lineWidth = wd + 3.3; c.stroke();
        c.strokeStyle = col; c.lineWidth = wd; c.stroke();
        c.setLineDash([]);
        if (done && tau > 0) {                              // 도착 — 목적지에 그 색 고리
          var e = co[co.length - 1];
          c.beginPath(); c.arc(X(e[0]), Y(e[1]), 9, 0, 6.284);
          c.strokeStyle = col; c.lineWidth = 2; c.stroke();
        }
      };
      if (mode === "shortest") path(S, cssVar("--c1"), 3.2, null);
      else if (mode === "avoiding" && A) path(A, cssVar("--c2"), 2.6, [7, 5]);
      else { if (A) path(A, cssVar("--c2"), 2.6, [7, 5]); path(S, cssVar("--c1"), 3.2, null); }
      if (mode === "both" && tau > 0 && tau < clock) {      // 지금 몇 분째인지
        label(c, Math.round(tau / 60) + "분 경과", w - 16, 58, cssVar("--sub"), "right", 11);
      }
      [[d.origin, "출발", cssVar("--accent")], [d.dest, d.dest_name, cssVar("--c2")]].forEach(function (m) {
        var mx = X(m[0][0]), my = Y(m[0][1]);
        c.fillStyle = m[2]; c.beginPath(); c.arc(mx, my, 5, 0, 6.284); c.fill();
        c.strokeStyle = cssVar("--sheet"); c.lineWidth = 2; c.stroke();
        var right = mx > w / 2;                              // 가장자리에서 잘리지 않게 안쪽으로
        label(c, m[1], right ? mx - 9 : mx + 9, my, cssVar("--ink"), right ? "right" : "left", 11);
      });
      label(c, TITLE[mode], 16, 26, cssVar("--ink"), "left", 12.5, "sans");
      label(c, STAT[mode], 16, 58, cssVar("--sub"), "left", 11);
    });
  });
}
CHARTS.alpha = ["alpha_grid", drawAlpha];
CHARTS.field = ["field_grid", drawFieldCanvas];
CHARTS.route = ["route_demo", drawRoute];

/* ⑥ 백테스트 — 예측 대 실측 산점, 대각선에 붙을수록 맞힌 것 */
function drawBacktest(cv, d, slide) {
  var rows = d.modes.B_cross_year.years["2025"].rows.filter(function (r) { return !r.closed; });
  var hit = d.modes.B_cross_year.years["2025"];
  var max = 0;
  rows.forEach(function (r) { max = Math.max(max, r.pred, r.obs); });
  max *= 1.06;
  var hitEl = slide.querySelector("[data-bt-hit]");
  animate(cv, 2400, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var pad = { l: 84, r: 20, t: 26, b: 50 };
    var px = function (v) { return pad.l + (w - pad.l - pad.r) * v / max; };
    var py = function (v) { return h - pad.b - (h - pad.t - pad.b) * v / max; };
    axes(c, w, h, pad);
    c.strokeStyle = cssVar("--line"); c.setLineDash([4, 4]); c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(px(0), py(0)); c.lineTo(px(max), py(max)); c.stroke(); c.setLineDash([]);
    label(c, "완벽 = 대각선", px(max) - 6, py(max) + 14, cssVar("--sub"), "right", 10.5);
    label(c, "예측 승차 →", w - pad.r, pad.t + 4, cssVar("--sub"), "right", 10.5);
    label(c, "↑ 실측 승차", pad.l + 6, pad.t + 4, cssVar("--sub"), "left", 10.5);
    [0.25, 0.5, 0.75].forEach(function (t) {             // 규모를 읽을 눈금 (천 단위) — 끝값은 축 이름과 겹친다
      var v = max * t, tx = Math.round(v / 1000) + "천";
      label(c, tx, px(v), h - pad.b + 14, cssVar("--sub"), "center", 10);
      label(c, tx, pad.l - 6, py(v), cssVar("--sub"), "right", 10);
    });
    var shown = Math.floor(p * rows.length);
    rows.slice(0, shown).forEach(function (r) {
      var ok = r.pred_grade === r.obs_grade;
      c.fillStyle = ok ? cssVar("--c2") : cssVar("--c1");
      c.beginPath(); c.arc(px(r.pred), py(r.obs), 9, 0, 6.284); c.fill();
      c.strokeStyle = cssVar("--sheet"); c.lineWidth = 2; c.stroke();   // 겹칠 때 서로 떨어져 보이게
    });
    if (hitEl) hitEl.textContent = "등급 적중 " + Math.round(hit.grade_hit_rate * 100 * p) + "%";
  });
}
CHARTS.backtest = ["backtest_bars", drawBacktest];

/* ⑦ 결함 대장 — 등급별 등재 건수 타일 (redteam_counts.json, 대장 ID 를 센 값) */
function drawRedteam(cv, d, slide, fig) {
  var host = fig.querySelector(".rt"); host.innerHTML = "";
  var order = [["치명", "g4"], ["높음", "g3"], ["중간", "g2"], ["낮음", "g1"]];
  order.forEach(function (o) {
    var t = document.createElement("div");
    t.setAttribute("style", "background:#F2F4F6;border-radius:24px;padding:32px 24px;text-align:center;display:flex;flex-direction:column;gap:10px;");
    t.innerHTML = '<div style="font-size:72px;font-weight:800;letter-spacing:-.04em;line-height:1;color:#191F28"><span class="cu" data-v="' + d.by_grade[o[0]] + '">0</span></div>'
      + '<div style="font-size:26px;color:#4E5968;display:flex;align-items:center;justify-content:center;gap:10px"><i style="display:inline-block;width:14px;height:14px;border-radius:50%;background:' + cssVar("--" + o[1]) + '"></i><span>' + o[0] + '</span></div>';
    host.appendChild(t);
  });
  var s = document.createElement("p"); s.setAttribute("style", "grid-column:1 / -1;margin:0;font-size:24px;color:#8B95A1;line-height:1.45");
  s.textContent = "등재 " + d.total + "건 · 철회 " + d.retracted.length + "건(" + d.retracted.join(", ") + ") · 5회차까지, 다른 모델 교차검증 포함";
  host.appendChild(s);
  countUp(slide);
}
CHARTS.redteam = ["redteam_counts", drawRedteam];

/* ⑧ 9/5 실전 결과 — 비어 있으면 자리, 채워지면 타일 4 + 카드 3 (live_result.json — tools/deck_data.py 가 evaluate.py 결과에서 만든다) */
function esc(t) { return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
function drawLive(cv, d, slide, fig) {
  var host = fig.querySelector(".live"); host.innerHTML = "";
  if (!d.filled) {
    host.innerHTML = '<div style="background:#F2F4F6;border-radius:28px;padding:80px 60px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:20px"><span style="display:inline-block;font-size:24px;font-weight:700;padding:8px 20px;border-radius:999px;color:#fff;background:#D0342C">결과 대기</span>'
      + '<div style="font-size:52px;font-weight:800;letter-spacing:-.03em;color:#191F28">9/5 실전 결과 — 9/6 채움</div>'
      + '<p style="margin:0;font-size:28px;color:#4E5968;line-height:1.5;max-width:1100px">' + esc(d.note || "") + '</p></div>';
    return;
  }
  var tiles = d.tiles || [];
  var cards = d.cards || [];
  host.innerHTML = '<div style="display:grid;grid-template-columns:repeat(' + Math.max(1, tiles.length) + ',1fr);gap:20px">' + tiles.map(function (t) {
    return '<div style="background:#F2F4F6;border-radius:28px;padding:34px 28px;text-align:center;display:flex;flex-direction:column;gap:12px">'
      + '<div style="font-size:64px;font-weight:800;letter-spacing:-.04em;line-height:1;color:#191F28;font-variant-numeric:tabular-nums">' + esc(t.v) + '</div>'
      + '<div style="font-size:24px;font-weight:600;color:#4E5968">' + esc(t.label) + '</div>'
      + (t.sub ? '<div style="font-size:20px;color:#8B95A1;line-height:1.4">' + esc(t.sub) + '</div>' : '') + '</div>';
  }).join("") + '</div>'
  + '<div style="display:grid;grid-template-columns:repeat(' + Math.max(1, cards.length) + ',1fr);gap:20px;margin-top:20px">' + cards.map(function (k) {
    var miss = k.kind === "miss";
    return '<div style="background:' + (miss ? '#191F28' : '#F2F4F6') + ';color:' + (miss ? '#fff' : '#191F28') + ';border-radius:28px;padding:30px 34px;display:flex;flex-direction:column;gap:10px">'
      + '<div style="font-size:22px;font-weight:600;color:' + (miss ? '#FFB27A' : '#F36F21') + '">' + esc(k.kicker) + '</div>'
      + '<div style="font-size:34px;font-weight:800;letter-spacing:-.03em;line-height:1.25">' + esc(k.title) + '</div>'
      + '<p style="margin:0;font-size:22px;line-height:1.45;color:' + (miss ? '#D1D6DB' : '#4E5968') + '">' + esc(k.body) + '</p></div>';
  }).join("") + '</div>';
}
CHARTS.live = ["live_result", drawLive];

/* ⑨ 그 시각, 화면은 이랬다 — 발행 스냅샷 재생 (replay_frames.json = data/live/forecast_history/20260905 의 발행분 그대로).
   왼쪽: 쇼 종료 실시각 기입 전·후(21:31 → 21:36) 시간대별 유출 예측 — 기입 하나로 예측이 어떻게 옮겨가는가.
   오른쪽: 22:06 발행분의 역 7개 부하 — 우리 화면이 하루 중 가장 붉었던 순간. 등급색은 board.js 와 같은 경계(0.6/0.8/1.0). */
function gradeColor(load) { return cssVar(load >= 1 ? "--g4" : load >= 0.8 ? "--g3" : load >= 0.6 ? "--g2" : "--g1"); }
function drawReplay(cv, d, slide) {
  var fig = cv.parentNode, cvs = [].slice.call(fig.querySelectorAll("canvas"));
  var byAt = {}; d.frames.forEach(function (f) { byAt[f.at] = f; });
  var before = byAt[d.before_after[0]], after = byAt[d.before_after[1]], peak = byAt[d.peak];
  var hours = ["19", "20", "21", "22", "23"];
  animate(cvs[0], 2600, function (p) {
    cvs.forEach(function (canvas) {
      var mode = canvas.getAttribute("data-mode"), out = fitCanvas(canvas), c = out.ctx, w = out.w, h = out.h;
      if (mode === "shift" && before && after) {
        var pad = { l: 90, r: 24, t: 96, b: 50 };
        var max = 0; hours.forEach(function (hh) { max = Math.max(max, before.outflow[hh] || 0, after.outflow[hh] || 0); }); max *= 1.12;
        var gw = (w - pad.l - pad.r) / hours.length, bw = gw * 0.32;
        var py = function (v) { return h - pad.b - (h - pad.t - pad.b) * v / max; };
        axes(c, w, h, pad);
        [0.5, 1].forEach(function (t) { var v = max * t / 1.12; label(c, Math.round(v / 1000) + "천", pad.l - 8, py(v), cssVar("--sub"), "right", 10); });
        hours.forEach(function (hh, i) {
          var x0 = pad.l + gw * i + gw * 0.18;
          var vb = (before.outflow[hh] || 0), va = (after.outflow[hh] || 0);
          c.fillStyle = "#C5CAD1"; roundRect(c, x0, py(vb * Math.min(1, p * 2)), bw, h - pad.b - py(vb * Math.min(1, p * 2)), 6); c.fill();
          var pa = Math.max(0, Math.min(1, (p - 0.35) / 0.65));
          c.fillStyle = cssVar("--c1"); roundRect(c, x0 + bw + 6, py(va * pa), bw, h - pad.b - py(va * pa), 6); c.fill();
          label(c, hh + "시", x0 + bw + 3, h - pad.b + 14, cssVar("--sub"), "center", 10.5);
          if (pa >= 1 && Math.abs(va - vb) > max * 0.04) {
            var dv = Math.round((va - vb) / 1000);
            label(c, (dv > 0 ? "+" : "") + dv + "천", x0 + bw + 3, Math.min(py(va), py(vb)) - 14, dv > 0 ? cssVar("--c1") : cssVar("--ink-2"), "center", 10.5);
          }
        });
        label(c, before.hhmm + " 발행 · 쇼 종료 " + before.show_end + " (계획)", 16, 26, cssVar("--ink-2"), "left", 11.5, "sans");
        label(c, after.hhmm + " 발행 · 쇼 종료 " + after.show_end + " (현장 기입)", 16, 58, cssVar("--c1"), "left", 11.5, "sans");
      } else if (mode === "loads" && peak) {
        var rows = peak.loads.slice().sort(function (a, b) { return (b.load == null ? -1 : b.load) - (a.load == null ? -1 : a.load); });
        var pad2 = { l: Math.min(250, w * 0.34), r: 120, t: 96, b: 14 }, rh = (h - pad2.t - pad2.b) / rows.length;
        rows.forEach(function (r, i) {
          var y = pad2.t + rh * i + rh * 0.2, bh = rh * 0.6, full = w - pad2.l - pad2.r;
          label(c, r.name, pad2.l - 10, y + bh / 2, cssVar("--ink-2"), "right", 11.5, "sans");
          c.fillStyle = "#E5E8EB"; roundRect(c, pad2.l, y, full, bh, 8); c.fill();
          [0.6, 0.8, 1.0].forEach(function (t) { c.strokeStyle = "#fff"; c.lineWidth = 2; c.beginPath(); c.moveTo(pad2.l + full * t, y); c.lineTo(pad2.l + full * t, y + bh); c.stroke(); });
          if (r.load == null) { label(c, r.note || "통제", pad2.l + 10, y + bh / 2, cssVar("--ink-2"), "left", 11); return; }
          var bw2 = full * Math.min(1, r.load) * p;
          c.fillStyle = gradeColor(r.load); roundRect(c, pad2.l, y, bw2, bh, 8); c.fill();
          label(c, Math.round(r.load * 100 * p) + "%" + (r.note ? "  " + r.note : ""), pad2.l + bw2 + 10, y + bh / 2, cssVar("--ink"), "left", 11);
        });
        label(c, peak.hhmm + " 발행 · " + peak.hour + "시 부하(수요 ÷ 수송력)", 16, 26, cssVar("--ink-2"), "left", 11.5, "sans");
        label(c, "α " + peak.alpha.toFixed(2) + " · 관측 " + peak.n_obs + "건 · 공원 " + peak.park, 16, 58, cssVar("--sub"), "left", 11);
      }
    });
  });
}
CHARTS.replay = ["replay_frames", drawReplay];

/* ⑩ 재료 — 공개 데이터 8종 표 (sources.json). 행 수·문구 전부 JSON 에서 */
function drawSources(cv, d, slide, fig) {
  var host = fig.querySelector(".srcs"); host.innerHTML = "";
  var th = function (t, w) { return '<th style="text-align:left;padding:10px 12px;border-bottom:2px solid #191F28;font-size:20px;font-weight:700;color:#4E5968;white-space:nowrap' + (w ? ';width:' + w : '') + '">' + esc(t) + '</th>'; };
  var td = function (t, style) { return '<td style="padding:11px 12px;border-bottom:1px solid #E5E8EB;font-size:20px;line-height:1.35;color:#191F28;vertical-align:top;' + (style || '') + '">' + t + '</td>'; };
  var layerChip = function (l) {
    var dark = l.indexOf("사전") === 0, live = l.indexOf("당일") === 0;
    return '<span style="display:inline-block;padding:3px 10px;border-radius:8px;font-size:18px;font-weight:700;white-space:nowrap;color:' + (dark ? '#fff' : '#191F28') + ';background:' + (dark ? '#191F28' : live ? '#FFE1CC' : '#F2F4F6') + '">' + esc(l) + '</span>';
  };
  host.innerHTML = '<table style="border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums"><thead><tr>'
    + th("소스", "22%") + th("무엇을 주나") + th("주기", "10%") + th("층", "9%") + th("어디에 쓰나", "20%") + th("한계", "20%") + '</tr></thead><tbody>'
    + d.rows.map(function (r) {
      return '<tr>' + td('<b>' + esc(r.name) + '</b><div style="font-size:16px;color:#8B95A1;margin-top:2px;font-family:var(--mono)">' + esc(r.id) + '</div>')
        + td(esc(r.gives)) + td(esc(r.cadence), 'white-space:nowrap') + td(layerChip(r.layer)) + td(esc(r.use)) + td('<span style="color:#4E5968">' + esc(r.limit) + '</span>') + '</tr>';
    }).join("") + '</tbody></table>';
}
CHARTS.sources = ["sources", drawSources];

/* ⑪ 과정 — 일별 커밋 막대 + 이정표 (process.json). 숫자 타일은 같은 JSON 에서 */
function drawProcess(cv, d, slide, fig) {
  var tiles = slide.querySelector(".ptiles");
  if (tiles) {
    var T = [[String(d.commits_total), "커밋 (제출용)", "+ 자동 발행 " + d.publish_commits],
             [d.tests.first + "→" + d.tests.now, "회귀 테스트", "변경마다 전부 통과"],
             [d.redteam.rounds + "회차 · " + d.redteam.total + "건", "우리 것을 먼저 깼다", "치명 " + d.redteam.by_grade["치명"] + " · 높음 " + d.redteam.by_grade["높음"] + " 전부 조치"],
             [String(d.hotfix_day), "당일 hotfix", "테스트 통과 후에만 push"]];
    tiles.innerHTML = T.map(function (t) {
      return '<div style="background:#F2F4F6;border-radius:24px;padding:26px 24px;display:flex;flex-direction:column;gap:8px"><div style="font-size:52px;font-weight:800;letter-spacing:-.04em;line-height:1;color:#191F28;font-variant-numeric:tabular-nums">' + esc(t[0]) + '</div><div style="font-size:22px;font-weight:700;color:#191F28">' + esc(t[1]) + '</div><div style="font-size:18px;color:#8B95A1;line-height:1.35">' + esc(t[2]) + '</div></div>';
    }).join("");
  }
  var days = d.days, max = Math.max.apply(null, days.map(function (x) { return x.commits; }));
  animate(cv, 2000, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var pad = { l: 24, r: 24, t: 110, b: 44 }, gw = (w - pad.l - pad.r) / days.length, bw = gw * 0.56;
    var py = function (v) { return h - pad.b - (h - pad.t - pad.b) * v / max; };
    c.strokeStyle = cssVar("--rule"); c.lineWidth = 1; c.beginPath(); c.moveTo(pad.l, h - pad.b); c.lineTo(w - pad.r, h - pad.b); c.stroke();
    days.forEach(function (x, i) {
      var cx = pad.l + gw * i + gw / 2, v = x.commits * p, y = py(v);
      c.fillStyle = x.milestone ? cssVar("--c1") : "#C5CAD1"; roundRect(c, cx - bw / 2, y, bw, h - pad.b - y, 8); c.fill();
      label(c, Math.round(v) + "", cx, y - 14, cssVar("--ink"), "center", 11);
      label(c, x.date.slice(5).replace("-", "/"), cx, h - pad.b + 16, cssVar("--sub"), "center", 10.5);
      if (x.milestone && p > 0.85) {
        var parts = x.milestone.split(" · ");
        parts.forEach(function (t, k) { label(c, t, cx, pad.t - 84 + k * 26, cssVar("--ink-2"), "center", 9.5, "sans"); });
        c.strokeStyle = cssVar("--rule"); c.setLineDash([2, 4]); c.beginPath(); c.moveTo(cx, pad.t - 84 + parts.length * 26 - 8); c.lineTo(cx, y - 26); c.stroke(); c.setLineDash([]);
      }
    });
  });
}
CHARTS.process = ["process", drawProcess];

/* ⑫ 실측 장 — 최단시간 경로가 최단거리와 달랐던 순간 (route_real.json). 행 = 발행 시각, 열 = 목적지. 계산 없음, 표시만 */
function drawRouteReal(cv, d, slide, fig) {
  var frames = d.frames, names = frames[0].routes.map(function (r) { return r.name.replace("역", ""); });
  var changed = 0, total = 0, best = null, yeoMin = [];
  frames.forEach(function (f) { f.routes.forEach(function (r) { total++; if (r.changed) { changed++; if (!best || r.saved_sec > best.saved_sec) best = Object.assign({ at: f.hhmm }, r); } if (r.name === "여의도역") yeoMin.push(r.shortest.min); }); });
  var sum = slide.querySelector("[data-real-summary]");
  if (sum) sum.innerHTML = "9/5 실측 장 " + frames.length + "시각 × 목적지 " + names.length + "곳 = " + total + "건 중 <b style=\"color:#191F28\">" + changed + "건</b>에서 가장 빨리 닿는 길 ≠ 가장 짧은 길"
    + (best ? " · 최대 <b style=\"color:#191F28\">" + esc(best.name) + " " + best.at + "</b> — " + best.extra_m + "m 더 걷고 <b style=\"color:#F36F21\">" + Math.round(best.saved_sec / 60) + "분</b> 빠름" : "")
    + " · 이벤트광장→여의도역 걷는 시간 " + Math.min.apply(null, yeoMin) + "~" + Math.max.apply(null, yeoMin) + "분 (고정속도라면 " + frames[0].routes[0].fixed_speed_min + "분)";
  var maxSave = Math.max(1, best ? best.saved_sec / 60 : 1);
  animate(cv, 1800, function (p) {
    var out = fitCanvas(cv), c = out.ctx, w = out.w, h = out.h;
    var pad = { l: 96, r: 12, t: 64, b: 8 }, cw = (w - pad.l - pad.r) / names.length, rh = (h - pad.t - pad.b) / frames.length;
    label(c, "가장 빨리 닿는 길이 가장 짧은 길과 달랐나 — 9/5 실측 장", 12, 22, cssVar("--ink"), "left", 12, "sans");
    names.forEach(function (n, j) { label(c, n, pad.l + cw * j + cw / 2, pad.t - 14, cssVar("--ink-2"), "center", 10.5, "sans"); });
    frames.forEach(function (f, i) {
      var y = pad.t + rh * i;
      label(c, f.hhmm, pad.l - 10, y + rh / 2, cssVar("--ink-2"), "right", 11);
      f.routes.forEach(function (r, j) {
        var x = pad.l + cw * j + 3, bw = cw - 6, bh = rh - 6;
        var k = Math.min(1, ((i * names.length + j) + 1) / total / Math.max(0.001, p));
        if (k > 1) return;
        if (r.changed) {
          var t = Math.min(1, (r.saved_sec / 60) / maxSave), col = hex(cssVar("--c1"));
          c.fillStyle = "rgba(" + col[0] + "," + col[1] + "," + col[2] + "," + (0.25 + 0.7 * t).toFixed(2) + ")";
          roundRect(c, x, y + 3, bw, bh, 8); c.fill();
          label(c, "−" + Math.round(r.saved_sec / 60) + "분", x + bw / 2, y + rh / 2 - 9, t > 0.45 ? "#fff" : cssVar("--ink"), "center", 11.5);
          label(c, "+" + r.extra_m + "m", x + bw / 2, y + rh / 2 + 11, t > 0.45 ? "rgba(255,255,255,.85)" : cssVar("--ink-2"), "center", 9.5);
        } else {
          c.fillStyle = "#F2F4F6"; roundRect(c, x, y + 3, bw, bh, 8); c.fill();
          label(c, "같은 길", x + bw / 2, y + rh / 2, cssVar("--sub"), "center", 10, "sans");
        }
      });
    });
  });
}
CHARTS.routereal = ["route_real", drawRouteReal];

export function playChart(slide) {
  [].slice.call(slide.querySelectorAll("[data-chart]")).forEach(function (fig) {
    var spec = CHARTS[fig.getAttribute("data-chart")];
    if (!spec) return;
    var cv = fig.querySelector("canvas");
    chartData(spec[0]).then(function (d) { spec[1](cv, d, slide, fig); })
      .catch(function (err) { console.warn("chart", err); fig.innerHTML = '<p style="font-size:24px;color:#8B95A1">그래프 데이터를 받지 못했다.</p>'; });
  });
}
export async function loadStrips(root) {
  var pres = [].slice.call(root.querySelectorAll("pre[data-strip]"));
  if (!pres.length) return;
  var list = await fetch(new URL("../deck/code_strips.json", import.meta.url)).then(function (r) { return r.json(); });
  var by = {}; list.forEach(function (s) { by[s.id] = s; });
  pres.forEach(function (pre) {
    if (pre.getAttribute("data-strip-done")) return;
    var s = by[pre.getAttribute("data-strip")]; if (!s) return;
    pre.setAttribute("data-strip-done", "1");
    var hl = function (line) {
      var t = esc(line);
      var m = t.match(/^(\s*)(#.*|\/\/.*)$/);
      if (m) return m[1] + '<span style="color:#8B95A1">' + m[2] + '</span>';
      var ds = t.match(/^(\s*)("""|\/\*)/);
      if (ds || /"""\s*$/.test(t) || /^\s*\/\*/.test(t)) return '<span style="color:#8B95A1">' + t + '</span>';
      t = t.replace(/(&quot;[^&]*&quot;|"[^"]*"|'[^']*')/g, '<span style="color:#2E7D5B">$1</span>');
      t = t.replace(/\b(def|return|for|in|if|else|function|const|var|let|import|from|not|and|or|lambda|None|True|False)\b/g, '<span style="color:#F36F21;font-weight:600">$1</span>');
      t = t.replace(/\b([A-Za-z_][A-Za-z0-9_]*)(?=\()/g, '<span style="color:#3182F6">$1</span>');
      return t;
    };
    pre.innerHTML = '<span style="display:flex;justify-content:space-between;gap:16px;color:#4E5968;font:600 20px/1.4 var(--mono);padding-bottom:14px;margin-bottom:16px;border-bottom:1px solid #E5E8EB"><span>' + esc(s.file + ":" + s.start) + '</span><span style="font-family:Pretendard Variable,sans-serif;font-weight:600;color:#191F28">' + esc(s.caption) + '</span></span>' + s.lines.map(hl).join("\n");
  });
}
