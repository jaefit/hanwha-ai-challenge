// 덱 8b 「가장 짧은 길이 아니라 가장 빨리 닿는 길」 — 9/5 실측 장에서 최단거리 vs 최단시간 경로 (Task 13 스파이크).
//   node tools/route_real.mjs
//
// 가정 봉우리(route_demo.json)가 아니라 **그날 화면이 실제로 그린 장**으로 돌린다. 관측 → 장 → 간선 시간 → A* 는
// docs/go.html 의 fieldObs · buildField · edgeSeconds · astar 를 문자 그대로 옮겼다(같은 상수 F_KERNEL·F_PAD·F_COLS·F_ROWS,
// 같은 field.js). 재생 스냅샷 6개(docs/data/replay/20260905)마다 이벤트광장 → 역 6곳에 두 비용식을 돌려
// "경로가 실제로 바뀌었나, 몇 분 차이인가"를 낸다. 결과가 '안 바뀜'이면 덱은 그렇게 적는다 — 대장 M14.
//
// 출력: docs/deck/route_real.json (숫자만 — 좌표는 싣지 않는다)
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(url.fileURLToPath(import.meta.url)));
const Field = require(path.join(ROOT, 'docs', 'app', 'field.js'));
const RoutingExtra = require(path.join(ROOT, 'docs', 'app', 'routing_extra.js'));
const GRAPH = require(path.join(ROOT, 'docs', 'data', 'routing', 'walk_graph.json'));
const CAMS = require(path.join(ROOT, 'docs', 'data', 'cams.json'));
const REPLAY_DIR = path.join(ROOT, 'docs', 'data', 'replay', '20260905');
const OUT = path.join(ROOT, 'docs', 'deck', 'route_real.json');

// ── go.html 상수 그대로 ────────────────────────────────────────────
const EVENT = [126.9320, 37.5292];
const ZONES = [[126.9345, 37.5310], [126.9330, 37.5290], [126.9412, 37.5257], [126.9385, 37.5205], [126.9245, 37.5268]];
const F_KERNEL = { varShort: .125, lenShort: 150, varLong: .125, lenLong: 1200 };
const F_SD_MAX = Math.sqrt(F_KERNEL.varShort + F_KERNEL.varLong);
const F_PAD = .012, F_COLS = 140, F_ROWS = 110;
const STATIONS = {
  '여의도역': [126.924194, 37.521754], '여의나루역': [126.932901, 37.527098],
  '국회의사당역': [126.917874, 37.528105], '샛강역': [126.928422, 37.517274],
  '신길역': [126.916352, 37.517243], '마포역': [126.945708, 37.539141],
};
const distM = (a, b) => Field.distanceM(a, b);
const tagv = v => String(v == null ? '' : v).toLowerCase();
const allowed = e => !/(motorway|trunk|busway)/.test(tagv(e.h)) && !/(^|,)(no|private)(,|$)/.test(tagv(e.f)) && !/(^|,)(no|private)(,|$)/.test(tagv(e.a));

function buildGraph() {
  const edges = RoutingExtra.withExtraEdges(GRAPH.edges);
  const adj = new Map(), usable = new Set();
  for (const e of edges) {
    if (!allowed(e)) continue;
    if (!adj.has(e.u)) adj.set(e.u, []);
    adj.get(e.u).push(e);
    usable.add(e.u); usable.add(e.v);
  }
  return { nodes: GRAPH.nodes, adj, usable: [...usable] };
}
const nearest = (g, p) => { let b = null, bd = Infinity; for (const id of g.usable) { const c = g.nodes[id]; if (!c) continue; const d = distM(p, c); if (d < bd) { bd = d; b = id; } } return b; };

/** go.html fieldObs — 재생 파일(latest.json 모양)에서 관측을 만든다. now 는 그 발행 시각. */
function fieldObs(data, now) {
  const cctv = data.cctv || {};
  const vals = Object.entries(cctv).map(([id, v]) => Object.assign({ id: String(id) }, v));
  const byId = new Map(vals.map(v => [String(v.cam_id || v.id), v])), byName = new Map(vals.map(v => [v.name, v]));
  const obs = [];
  let uncal = 0, cal = 0;
  CAMS.forEach(cam => {
    const v = byId.get(String(cam.camId)) || byName.get(cam.name) || null;
    if (!v || v.ok === false) return;
    let y = null, kind = 'cctv_uncalibrated';
    if (v.calibrated && v.density != null) { y = Field.densityToUnit(v.density); kind = 'cctv_calibrated'; cal++; }
    else { y = Field.levelToUnit(v.level); uncal++; }
    if (y == null) { uncal--; return; }
    const t = v.ts ? Date.parse(String(v.ts).replace(' ', 'T')) : NaN;
    const ageMin = isFinite(t) ? Math.max(0, (now - t) / 60000) : null;
    obs.push({ x: [cam.lng, cam.lat], y, sigma: Field.obsNoise({ kind, confidence: v.confidence, flags: v.flags, ageMin }) });
  });
  const park = ((data.forecast || {}).live_snapshot || {})['여의도한강공원'], pu = park ? Field.gradeToUnit(park.congest) : null;
  let poi = null;
  if (pu != null) {
    const t = park.ts ? Date.parse(String(park.ts).replace(' ', 'T')) : NaN;
    const ageMin = isFinite(t) ? Math.max(0, (now - t) / 60000) : null;
    const sg = Field.obsNoise({ kind: 'poi', ageMin, dup: ZONES.length });
    ZONES.forEach(z => obs.push({ x: z, y: pu, sigma: sg }));
    poi = { grade: park.congest, unit: pu, sigma: Math.round(sg * 1000) / 1000, age_min: ageMin == null ? null : Math.round(ageMin) };
  }
  return { obs, uncal, cal, poi };
}

function buildField(obs) {
  const lngs = CAMS.map(c => c.lng), lats = CAMS.map(c => c.lat);
  const x0 = Math.min(...lngs) - F_PAD, x1 = Math.max(...lngs) + F_PAD, y0 = Math.min(...lats) - F_PAD, y1 = Math.max(...lats) + F_PAD;
  const g = { x0, y0, dx: (x1 - x0) / F_COLS, dy: (y1 - y0) / F_ROWS, cols: F_COLS, rows: F_ROWS };
  const f = Field.buildField({ observations: obs, grid: g, prior: null, fallbackPrior: .3, kernel: F_KERNEL });
  return { FIELD: f, FGRID: g };
}

function edgeCellFn(FGRID) {
  return e => {
    const c = (e.g && e.g.length) ? e.g[Math.floor(e.g.length / 2)] : null;
    const a = c || GRAPH.nodes[e.u], b = c ? null : GRAPH.nodes[e.v];
    const x = c ? c[0] : (a && b ? (a[0] + b[0]) / 2 : null), y = c ? c[1] : (a && b ? (a[1] + b[1]) / 2 : null);
    if (x == null) return -1;
    const ix = Math.floor((x - FGRID.x0) / FGRID.dx), iy = Math.floor((y - FGRID.y0) / FGRID.dy);
    if (ix < 0 || iy < 0 || ix >= FGRID.cols || iy >= FGRID.rows) return -1;
    return iy * FGRID.cols + ix;
  };
}

/** go.html astar 와 같은 탐색. cost 와 휴리스틱(시간 비용이면 거리÷자유보행)만 갈아끼운다. */
function astar(g, s, t, cost, hScale) {
  const dist = new Map([[s, 0]]), came = new Map(), q = [[0, s]], goal = g.nodes[t];
  while (q.length) {
    q.sort((a, b) => a[0] - b[0]);
    const [, u] = q.shift();
    if (u === t) break;
    for (const e of g.adj.get(u) || []) {
      const nd = dist.get(u) + cost(e);
      if (nd < (dist.has(e.v) ? dist.get(e.v) : Infinity)) {
        dist.set(e.v, nd); came.set(e.v, [u, e]);
        q.push([nd + distM(g.nodes[e.v], goal) * hScale, e.v]);
      }
    }
  }
  if (!came.has(t) && s !== t) return null;
  const es = []; let u = t;
  while (u !== s) { const v = came.get(u); if (!v) break; es.push(v[1]); u = v[0]; }
  es.reverse();
  return es;
}

function main() {
  const files = fs.readdirSync(REPLAY_DIR).filter(f => /^\d{4}\.json$/.test(f)).sort();
  if (!files.length) { console.error('재생 파일 없음 — tools/replay_build.py 먼저'); process.exit(1); }
  const g = buildGraph();
  const s = nearest(g, EVENT);
  const frames = [];
  for (const fn of files) {
    const data = JSON.parse(fs.readFileSync(path.join(REPLAY_DIR, fn), 'utf8'));
    const now = Date.parse(String(data.generated).replace(' ', 'T'));
    const { obs, uncal, cal, poi } = fieldObs(data, now);
    const { FIELD, FGRID } = buildField(obs);
    const cell = edgeCellFn(FGRID);
    const unit = e => { const k = cell(e); return k < 0 ? 0 : Math.max(0, Math.min(1, FIELD.mean[k])); };
    const sd = e => { const k = cell(e); return k < 0 ? F_SD_MAX : FIELD.sd[k]; };
    const m = e => Math.max(0.1, Number(e.m) || 0.1);
    const secOf = e => Field.blendSeconds(m(e), unit(e), sd(e), F_SD_MAX);        // 제품의 비용 = 그 간선을 걷는 초
    const sumM = es => es.reduce((a, e) => a + (Number(e.m) || 0), 0);
    const sumS = es => es.reduce((a, e) => a + secOf(e), 0);
    // 장 요약 — 얼마나 뾰족한가
    const mean = Array.from(FIELD.mean), sds = Array.from(FIELD.sd);
    const sorted = mean.slice().sort((a, b) => a - b);
    const fieldSummary = {
      n_obs: obs.length, cctv_uncalibrated: uncal, cctv_calibrated: cal, poi,
      u_median: Math.round(sorted[Math.floor(sorted.length / 2)] * 1000) / 1000,
      u_max: Math.round(Math.max(...mean) * 1000) / 1000,
      sd_median: Math.round(sds.slice().sort((a, b) => a - b)[Math.floor(sds.length / 2)] * 1000) / 1000,
    };
    const routes = Object.entries(STATIONS).map(([name, p]) => {
      const t = nearest(g, p);
      const es1 = astar(g, s, t, m, 1);                              // 최단거리
      const es2 = astar(g, s, t, secOf, 1 / Field.V_FREE);            // 최단시간 (제품)
      if (!es1 || !es2) return { name, error: 'no path' };
      const c1 = distM(EVENT, g.nodes[s]), c2 = distM(g.nodes[t], p);
      const conn = Field.blendSeconds(c1, 0, F_SD_MAX, F_SD_MAX) + Field.blendSeconds(c2, 0, F_SD_MAX, F_SD_MAX);
      const sm = sumM(es1) + c1 + c2, ss = sumS(es1) + conn, fm = sumM(es2) + c1 + c2, fs_ = sumS(es2) + conn;
      const same = es1.length === es2.length && es1.every((e, i) => e === es2[i]);
      return {
        name,
        shortest: { m: Math.round(sm), min: Math.round(ss / 60) },
        fastest: { m: Math.round(fm), min: Math.round(fs_ / 60) },
        changed: !same, extra_m: Math.round(fm - sm), saved_sec: Math.round(ss - fs_),
        fixed_speed_min: Math.round(sm / 67),                          // 옛 고정 67m/분 기준 — 대조용
      };
    });
    frames.push({ at: fn.slice(0, 4), hhmm: fn.slice(0, 2) + ':' + fn.slice(2, 4), generated: data.generated, field: fieldSummary, routes });
    const ch = routes.filter(r => r.changed);
    console.log(`${fn}: obs ${obs.length} (cctv ${uncal}+${cal}, poi ${poi ? poi.grade : '—'}) · 장 중앙 ${fieldSummary.u_median} 최대 ${fieldSummary.u_max} · 경로 바뀜 ${ch.length}/6`
      + (ch.length ? ' → ' + ch.map(r => `${r.name} +${r.extra_m}m ${Math.round(r.saved_sec / 60)}분 단축`).join(', ') : '')
      + ` · 여의도역 ${routes[0].shortest.m}m ${routes[0].shortest.min}분(고정속도 ${routes[0].fixed_speed_min}분)`);
  }
  const out = {
    date: '2026-09-05', origin: '이벤트광장', frames,
    method: 'docs/go.html 과 같은 관측→장(fieldObs·buildField, F_KERNEL 150/1200m, 140×110)·간선 시간(field.js blendSeconds)·A*. 비용식 두 개: 거리 / 그 간선을 걷는 초',
    note: '재생 스냅샷 6개의 실측 CCTV(전부 보정전 → 등급만, σ 0.3)와 서울시 공원 등급(관람구역 5곳)으로 만든 장. 가정 봉우리(route_demo.json) 없음. "changed" 가 false 면 최단시간 경로 = 최단거리 경로이고, 달라지는 건 소요 시간 추정만이다',
    source: 'docs/data/replay/20260905/*.json · docs/data/routing/walk_graph.json · docs/app/field.js · docs/app/routing_extra.js',
  };
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`${path.relative(ROOT, OUT)}  ${(fs.statSync(OUT).size / 1024).toFixed(1)}KB`);
}
main();
