// 덱 슬라이드 ④ 혼잡장 · ⑤ 보행 경로 데이터 내보내기 — 읽기 전용.
//   node tools/deck_field_route.mjs
//
// docs/app/field.js 를 그대로 require 한다. GP 커널·촐레스키를 여기서 다시 구현하면
// 화면과 덱이 조용히 어긋난다. 경로 탐색은 docs/go.html 의 allowed/distM/astar 를
// 문자 그대로 옮겼고(같은 의미를 보장), 혼잡 가중 비용은 docs/index.html:729 와 같은 식이다.
//
// 출력은 docs/deck/ — publish.py 가 `git add docs/data` 로 디렉터리를 통째로 스테이징하므로
// 그 아래 두면 5분마다 도는 발행 커밋에 반쯤 쓴 파일이 딸려 들어간다.

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
const OUT = path.join(ROOT, 'docs', 'deck');

// ── go.html 에서 그대로 옮긴 것 ────────────────────────────────────
const distM = (a, b) => { const la = (a[1] + b[1]) * Math.PI / 360; return Math.hypot((a[0] - b[0]) * 111320 * Math.cos(la), (a[1] - b[1]) * 111320); };
const tagv = v => String(v == null ? '' : v).toLowerCase();
const allowed = e => !/(motorway|trunk|busway)/.test(tagv(e.h)) && !/(^|,)(no|private)(,|$)/.test(tagv(e.f)) && !/(^|,)(no|private)(,|$)/.test(tagv(e.a));

// index.html:538 과 같은 값이어야 한다
const KERNEL = { varShort: .125, lenShort: 150, varLong: .125, lenLong: 1200 };
const CROWD_WEIGHT = 1.25;                       // index.html:550 ROUTE_CROWD_WEIGHT

const EVENT_PLAZA = [126.9330, 37.5290];         // index.html:364 ZONES "이벤트광장"
const YEOUIDO_ST = [126.924194, 37.521754];      // go.html:195 STATIONS.yeouido
const STATIONS = {                               // go.html:195-197 STATIONS
  '여의도역': [126.924194, 37.521754], '여의나루역': [126.932901, 37.527098],
  '국회의사당역': [126.917874, 37.528105], '샛강역': [126.928422, 37.517274],
  '신길역': [126.916352, 37.517243], '마포역': [126.945708, 37.539141],
};

// ── ④ 혼잡장 — 관측이 하나씩 들어오며 면이 생긴다 ──────────────────
// 카메라 23대의 좌표는 실제(docs/data/cams.json). **등급은 예시다** — 2024·2025 에는
// CCTV 관측이 없었고 오늘 23대는 전부 「보정전」이라(9/2 H6) 실측 등급을 쓸 수 없다.
// 슬라이드가 이 사실을 그대로 적는다.
const SCENARIO = {                               // 9/5 21시경을 가정한 등급 배치 (예시)
  '63빌딩': '경계', '마포대교': '심각', '여의도한강공원': '심각', '원효대교': '경계',
  '여의동로': '주의', '여의서로': '여유', '국회': '주의', '샛강': '여유',
};

function scenarioGrade(cam, i) {
  for (const [k, v] of Object.entries(SCENARIO)) if (cam.name.includes(k) || cam.road.includes(k)) return v;
  return ['주의', '여유', '경계', '주의'][i % 4];
}

function buildFieldFrames() {
  const lngs = CAMS.map(c => c.lng), lats = CAMS.map(c => c.lat);
  const pad = 0.012;
  const x0 = Math.min(...lngs) - pad, x1 = Math.max(...lngs) + pad;
  const y0 = Math.min(...lats) - pad * 0.8, y1 = Math.max(...lats) + pad * 0.8;
  const cols = 56, rows = 38;
  const grid = { x0, y0, dx: (x1 - x0) / cols, dy: (y1 - y0) / rows, cols, rows };

  // 관측을 중요도(등급 높은 것) 순이 아니라 카메라 번호 순으로 넣는다 — 순서를 고르면 그림을 만든 것이 된다
  // 미보정 카메라는 등급만 나온다(collector_cctv.level) → levelToUnit 0.3/0.7/0.9/1.0.
  // σ 는 obsNoise 가 접어준다 — 23대 전부 ROI 미검증이므로 cctv_uncalibrated(0.3).
  const sigma = Field.obsNoise({ kind: 'cctv_uncalibrated' });
  const obs = CAMS.map((c, i) => ({
    x: [c.lng, c.lat],
    y: Field.levelToUnit(scenarioGrade(c, i)),
    sigma: sigma,
    kind: 'cctv_uncalibrated',
    name: c.name,
    grade: scenarioGrade(c, i),
  }));

  const steps = [0, 1, 2, 4, 7, 11, 16, obs.length];
  const frames = steps.map(n => {
    const f = Field.buildField({ observations: obs.slice(0, n), grid, prior: null, fallbackPrior: 0.3, kernel: KERNEL });
    return {
      n,
      // 0~1 실수를 0~1000 정수로 — 파일이 4배 작아지고 화면 해상도엔 넘친다
      mean: Array.from(f.mean, v => Math.round(v * 1000)),
      sd: Array.from(f.sd, v => Math.round(v * 1000)),
    };
  });

  return {
    grid: { x0, y0, x1, y1, cols, rows },
    kernel: KERNEL,
    obs_sigma: Field.obsNoise({ kind: 'cctv_uncalibrated' }),
    observations: obs.map(o => ({ x: o.x, grade: o.grade, name: o.name, y: Math.round(o.y * 1000) })),
    frames,
    scale: 1000,
    synthetic_grades: true,
    note: '카메라 23대의 좌표·커널(150m·1200m)·σ·GP 식은 실제 값. 등급 배치는 예시다 — 2024·2025 에는 CCTV 관측이 없고, 현재 23대는 ROI 미검증이라(9/2 H6) 밀도 등급을 내지 않는다.',
    source: 'docs/app/field.js buildField() · docs/data/cams.json',
  };
}

// ── ⑤ 보행 경로 — 같은 출발·도착에 두 비용식 ──────────────────────
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

const nearest = (g, p) => {
  let b = null, bd = Infinity;
  for (const id of g.usable) { const c = g.nodes[id]; if (!c) continue; const d = distM(p, c); if (d < bd) { bd = d; b = id; } }
  return b;
};

/** go.html:231 astar 와 같은 탐색. cost 만 갈아끼운다. 방문 순서를 같이 낸다(탐색 애니메이션용). */
function search(g, s, t, cost) {
  const dist = new Map([[s, 0]]), came = new Map(), q = [[0, s]], goal = g.nodes[t], order = [];
  while (q.length) {
    q.sort((a, b) => a[0] - b[0]);
    const [, u] = q.shift();
    order.push(u);
    if (u === t) break;
    for (const e of g.adj.get(u) || []) {
      const nd = dist.get(u) + cost(e);
      if (nd < (dist.has(e.v) ? dist.get(e.v) : Infinity)) {
        dist.set(e.v, nd); came.set(e.v, [u, e]);
        q.push([nd + distM(g.nodes[e.v], goal), e.v]);
      }
    }
  }
  if (!came.has(t) && s !== t) return null;
  const es = []; let u = t;
  while (u !== s) { const v = came.get(u); if (!v) break; es.push(v[1]); u = v[0]; }
  es.reverse();
  const coords = [];
  let meters = 0;
  for (const e of es) {
    meters += Number(e.m) || 0;
    const un = g.nodes[e.u];
    let seg = (e.g || [un, g.nodes[e.v]]).slice();
    if (seg.length > 1 && distM(seg[0], un) > distM(seg[seg.length - 1], un)) seg.reverse();
    for (const c of seg) { const l = coords[coords.length - 1]; if (!l || l[0] !== c[0] || l[1] !== c[1]) coords.push(c); }
  }
  return { coords, meters, order, cost_total: dist.get(t) };
}

/** 혼잡장에서 간선 위험도 — index.html routeRisk 와 같은 뜻(간선 중점의 장 값). */
function riskLookup(field) {
  const { x0, y0, cols, rows } = field.grid;
  const dx = (field.grid.x1 - x0) / cols, dy = (field.grid.y1 - y0) / rows;
  const last = field.frames[field.frames.length - 1].mean;
  return e => {
    const g = field.grid;
    const a = GRAPH.nodes[e.u], b = GRAPH.nodes[e.v];
    if (!a || !b) return 0;
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
    const ix = Math.floor((mx - x0) / dx), iy = Math.floor((my - y0) / dy);
    if (ix < 0 || iy < 0 || ix >= cols || iy >= rows) return 0;
    void g;
    return last[iy * cols + ix] / 1000;
  };
}

function buildRoute(field) {
  const g = buildGraph();
  const s = nearest(g, EVENT_PLAZA), t = nearest(g, YEOUIDO_ST);
  const risk = riskLookup(field);

  const shortest = search(g, s, t, e => Math.max(0.1, Number(e.m) || 0.1));
  const avoiding = search(g, s, t, e => Math.max(0.1, Number(e.m) || 0.1) * (1 + CROWD_WEIGHT * risk(e)));

  // 배경 보행망 — 두 경로를 감싸는 상자 안쪽만, 간선은 끝점 두 개로 줄인다
  const all = shortest.coords.concat(avoiding.coords);
  const bx0 = Math.min(...all.map(c => c[0])) - 0.004, bx1 = Math.max(...all.map(c => c[0])) + 0.004;
  const by0 = Math.min(...all.map(c => c[1])) - 0.003, by1 = Math.max(...all.map(c => c[1])) + 0.003;
  const inBox = p => p && p[0] >= bx0 && p[0] <= bx1 && p[1] >= by0 && p[1] <= by1;
  const seen = new Set(), bg = [];
  for (const [u, list] of g.adj) {
    for (const e of list) {
      const key = u < e.v ? `${u}|${e.v}` : `${e.v}|${u}`;
      if (seen.has(key)) continue;
      const a = GRAPH.nodes[e.u], b = GRAPH.nodes[e.v];
      if (!inBox(a) || !inBox(b)) continue;
      seen.add(key);
      bg.push([r6(a[0]), r6(a[1]), r6(b[0]), r6(b[1])]);
    }
  }

  // 방문 순서는 좌표로 — 노드 id 를 덱까지 들고 갈 이유가 없다
  const orderPts = shortest.order.map(id => GRAPH.nodes[id]).filter(inBox).map(p => [r6(p[0]), r6(p[1])]);

  // 6개 목적지 전부에 두 비용식을 돌려 본다 — 혼잡 가중이 실제로 경로를 바꾸는지가 요점이다
  const comparison = Object.entries(STATIONS).map(([name, p]) => {
    const tt = nearest(g, p);
    const a = search(g, s, tt, e => Math.max(0.1, Number(e.m) || 0.1));
    const b = search(g, s, tt, e => Math.max(0.1, Number(e.m) || 0.1) * (1 + CROWD_WEIGHT * risk(e)));
    const meanRisk = r => { let m = 0, rs = 0; for (const c of [0]) void c; return { m, rs }; };
    void meanRisk;
    return { name, straight_m: Math.round(distM(EVENT_PLAZA, p)),
             shortest_m: Math.round(a.meters), avoiding_m: Math.round(b.meters),
             changed: Math.round(a.meters) !== Math.round(b.meters) };
  });

  return {
    origin: EVENT_PLAZA, dest: YEOUIDO_ST, dest_name: '여의도역',
    comparison,
    detour_ratio: Math.round(shortest.meters) / Math.round(distM(EVENT_PLAZA, YEOUIDO_ST)),
    detour_note: ('이 보행망에서 재현되는 우회비는 1.31 배다(직선 1,120m · 경로 1,471m). '
      + 'routing/README.md:60 과 report.html §3.2·§3.10 이 적은 1,820m·1.64배는 보완간선·태그필터 어느 조합으로도 재현되지 않는다. '
      + '같은 파이프라인이 마포역 1,907m(9/2 e4b9a1a 실측)는 정확히 재현한다.'),
    mapo_check_m: Math.round(search(g, s, nearest(g, STATIONS['마포역']), e => Math.max(0.1, Number(e.m) || 0.1)).meters),
    bbox: [bx0, by0, bx1, by1],
    background_edges: bg,
    visited: orderPts,
    routes: {
      shortest: { coords: shortest.coords.map(c => [r6(c[0]), r6(c[1])]), meters: Math.round(shortest.meters) },
      avoiding: { coords: avoiding.coords.map(c => [r6(c[0]), r6(c[1])]), meters: Math.round(avoiding.meters) },
    },
    straight_m: Math.round(distM(EVENT_PLAZA, YEOUIDO_ST)),
    crowd_weight: CROWD_WEIGHT,
    graph_size: { nodes: Object.keys(GRAPH.nodes).length, edges: GRAPH.edges.length },
    walk_min_basis: '67m/분 (인파 속 보행, go.html walkMin)',
    note: '최단은 go.html 이 실제로 쓰는 비용(거리), 회피는 index.html 의 비용 max(0.1,m)·(1+1.25·μ). μ 는 위 혼잡장에서 읽는다 — 그 장의 등급 배치가 예시이므로 회피 경로도 그 시나리오에서의 결과다.',
    source: 'docs/data/routing/walk_graph.json · docs/go.html astar · docs/index.html:729',
  };
}

const r6 = v => Math.round(v * 1e6) / 1e6;

// ── 실행 ───────────────────────────────────────────────────────────
fs.mkdirSync(OUT, { recursive: true });
const field = buildFieldFrames();
fs.writeFileSync(path.join(OUT, 'field_grid.json'), JSON.stringify(field));
const route = buildRoute(field);
fs.writeFileSync(path.join(OUT, 'route_demo.json'), JSON.stringify(route));

for (const f of ['field_grid.json', 'route_demo.json']) {
  console.log(`docs/deck/${f}  ${(fs.statSync(path.join(OUT, f)).size / 1024).toFixed(1)}KB`);
}
console.log(`직선 ${route.straight_m}m · 최단 ${route.routes.shortest.meters}m · 회피 ${route.routes.avoiding.meters}m · 우회비 ${(route.routes.shortest.meters / route.straight_m).toFixed(2)}`);
console.log(`탐색 방문 ${route.visited.length}점 · 배경 간선 ${route.background_edges.length}개`);
