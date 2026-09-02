// docs/app/routing_extra.js (마포대교 보행 연결) 검증. pytest(tests/test_routing.py)가 node 로 실행하고 결과 JSON 을 읽는다.
//   node tests/routing_spec.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import url from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(url.fileURLToPath(import.meta.url)));
const R = require(path.join(ROOT, 'docs', 'app', 'routing_extra.js'));
const GRAPH = require(path.join(ROOT, 'docs', 'data', 'routing', 'walk_graph.json'));

const results = [];
const t = (name, fn) => {
  try { fn(); results.push({ name, ok: true }); }
  catch (e) { results.push({ name, ok: false, detail: String((e && e.message) || e).slice(0, 300) }); }
};
const ok = (c, msg) => { if (!c) throw new Error(msg || 'false'); };

// index.html 의 routeAllowed·routeStrict 와 같은 규칙 (사본이 어긋나면 이 스펙이 먼저 깨진다)
const tag = v => String(v == null ? '' : v).toLowerCase();
const routeAllowed = e => !/(motorway|trunk|busway)/.test(tag(e.h))
  && !/(^|,)(no|private)(,|$)/.test(tag(e.f)) && !/(^|,)(no|private)(,|$)/.test(tag(e.a));
const routeStrict = e => /(footway|path|pedestrian|steps|corridor|living_street)/.test(tag(e.h))
  || /(yes|both|left|right|separate)/.test(tag(e.s)) || !!e.x;

const distM = (a, b) => {
  const lat = (a[1] + b[1]) * Math.PI / 360;
  return Math.hypot((a[0] - b[0]) * 111320 * Math.cos(lat), (a[1] - b[1]) * 111320);
};

function shortestMeters(edges, startLL, goalLL, filter) {
  const adj = new Map(), nodes = GRAPH.nodes, usable = new Set();
  for (const e of edges) {
    if (filter && !filter(e)) continue;
    if (!adj.has(e.u)) adj.set(e.u, []);
    adj.get(e.u).push(e); usable.add(e.u); usable.add(e.v);
  }
  const nearest = p => {
    let best = null, bd = Infinity;
    for (const id of usable) { const c = nodes[id]; if (!c) continue; const d = distM(p, c); if (d < bd) { bd = d; best = id; } }
    return best;
  };
  const s = nearest(startLL), g = nearest(goalLL);
  const dist = new Map([[s, 0]]), came = new Map(), q = [[0, s]];
  while (q.length) {
    q.sort((a, b) => a[0] - b[0]);
    const [, u] = q.shift();
    if (u === g) break;
    for (const e of adj.get(u) || []) {
      const nd = dist.get(u) + (Number(e.m) || 0.1);
      if (nd < (dist.has(e.v) ? dist.get(e.v) : Infinity)) {
        dist.set(e.v, nd); came.set(e.v, [u, e]);
        q.push([nd + distM(nodes[e.v], nodes[g]), e.v]);
      }
    }
  }
  if (!dist.has(g)) return { meters: null, used: [] };
  const used = []; let u = g;
  while (u !== s) { const v = came.get(u); if (!v) break; used.push(v[1]); u = v[0]; }
  return { meters: dist.get(g), used };
}

const EVENT_PLAZA = [126.9330, 37.5290];   // nowcast.ZONES 이벤트광장
const MAPO_STN = [126.9459, 37.5391];      // nowcast.EXIT_LL 마포역 도보(마포대교)

t('마포대교 보행 간선을 양방향 2건으로 낸다', () => {
  const es = R.extraEdges();
  ok(es.length === 2, `간선 ${es.length}건 (양방향 2건이어야)`);
  const [a, b] = es;
  ok(a.u === b.v && a.v === b.u, '두 간선이 서로 반대 방향이어야');
  for (const e of es) {
    ok(/footway/.test(String(e.h)), `보행로로 태그돼야: ${e.h}`);
    ok(Number(e.m) > 0, 'm 이 양수여야');
    ok(Array.isArray(e.g) && e.g.length >= 2, '지오메트리 2점 이상');
  }
});

t('끝점이 실제 보행망 노드다', () => {
  for (const e of R.extraEdges()) {
    ok(GRAPH.nodes[e.u], `노드 없음: ${e.u}`);
    ok(GRAPH.nodes[e.v], `노드 없음: ${e.v}`);
  }
});

t('길이가 두 끝점 직선거리 이상이다 (하한 근사)', () => {
  for (const e of R.extraEdges()) {
    const straight = distM(GRAPH.nodes[e.u], GRAPH.nodes[e.v]);
    ok(e.m >= straight - 1, `m ${e.m} < 직선 ${straight.toFixed(0)}`);
    ok(e.m <= straight * 1.6, `m ${e.m} 이 직선 ${straight.toFixed(0)} 대비 과도`);
  }
});

t('간선이 마포대교 축에서 크게 벗어나지 않는다', () => {
  // 축 = 마포대교 남단 구역(nowcast.ZONES) → 마포역. 중점 이탈이 150m 안이어야 다리를 대표한다
  const S = [126.9345, 37.5310], T = [126.9459, 37.5391], k = 111320 * Math.cos(37.535 * Math.PI / 180);
  const e = R.extraEdges()[0], mid = GRAPH.nodes[e.u].map((v, i) => (v + GRAPH.nodes[e.v][i]) / 2);
  const ax = S[0] * k, ay = S[1] * 111320, bx = T[0] * k, by = T[1] * 111320;
  const px = mid[0] * k, py = mid[1] * 111320, dx = bx - ax, dy = by - ay;
  const tt = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)));
  ok(Math.hypot(px - (ax + tt * dx), py - (ay + tt * dy)) < 150, '중점이 다리 축에서 150m 넘게 벗어남');
});

t('병합은 순수하다 — 원본 배열을 건드리지 않는다', () => {
  const before = GRAPH.edges.length;
  const merged = R.withExtraEdges(GRAPH.edges);
  ok(GRAPH.edges.length === before, '원본이 변형됐다');
  ok(merged.length === before + 2, `병합 후 ${merged.length} (기대 ${before + 2})`);
  ok(merged !== GRAPH.edges, '새 배열을 돌려줘야');
});

t('병합 전에는 한강을 마포대교로 건널 수 없다 (결함 재현)', () => {
  const before = shortestMeters(GRAPH.edges, EVENT_PLAZA, MAPO_STN, routeAllowed);
  ok(before.meters > 3000, `병합 전 ${Math.round(before.meters)}m — 이미 짧다면 결함이 재현되지 않는다`);
});

t('병합하면 이벤트광장→마포역이 크게 짧아지고 새 간선을 쓴다', () => {
  const before = shortestMeters(GRAPH.edges, EVENT_PLAZA, MAPO_STN, routeAllowed);
  const after = shortestMeters(R.withExtraEdges(GRAPH.edges), EVENT_PLAZA, MAPO_STN, routeAllowed);
  ok(after.meters < before.meters * 0.65, `${Math.round(before.meters)}m → ${Math.round(after.meters)}m (35% 이상 줄어야)`);
  ok(after.used.some(e => e.mapo_walk), '새 보행 간선을 쓰지 않았다');
});

t('보행로 전용(strict) 단계에서도 쓰인다', () => {
  const after = shortestMeters(R.withExtraEdges(GRAPH.edges), EVENT_PLAZA, MAPO_STN, e => routeAllowed(e) && routeStrict(e));
  ok(after.meters != null, 'strict 단계에서 경로가 끊겼다');
  ok(after.used.some(e => e.mapo_walk), 'strict 단계가 새 간선을 못 쓴다 — 태그를 확인할 것');
});

t('근거 문자열에 출처와 한계가 적혀 있다', () => {
  const b = R.BASIS;
  ok(typeof b === 'string' && b.length > 20, '근거 문자열이 없다');
  ok(/마포대교/.test(b), '무엇인지 적혀야');
  ok(/근사|추정/.test(b), '근사·추정임을 밝혀야 (숫자 규칙)');
});

process.stdout.write(JSON.stringify(results));
