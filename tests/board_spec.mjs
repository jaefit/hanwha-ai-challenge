// docs/app/board.js (출구 판정 규칙) 검증. pytest(tests/test_board.py)가 node 로 실행하고 결과 JSON 을 읽는다.
//   node tests/board_spec.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import url from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(url.fileURLToPath(import.meta.url)));
const B = require(path.join(ROOT, 'docs', 'app', 'board.js'));

const results = [];
const t = (name, fn) => {
  try { fn(); results.push({ name, ok: true }); }
  catch (e) { results.push({ name, ok: false, detail: String((e && e.message) || e).slice(0, 300) }); }
};
const ok = (c, msg) => { if (!c) throw new Error(msg || 'false'); };
const eq = (a, b, msg) => { if (a !== b) throw new Error(`${msg || ''} ${JSON.stringify(a)} !== ${JSON.stringify(b)}`); };

const fc = (exits, extra) => Object.assign({ exits }, extra || {});
const at = (load, more) => Object.assign({ load, closed: false }, more || {});

t('등급 경계가 서울시 4단계와 같다', () => {
  eq(B.grade(0.49), '여유'); eq(B.grade(0.5), '주의');
  eq(B.grade(0.79), '주의'); eq(B.grade(0.8), '경계');
  eq(B.grade(0.99), '경계'); eq(B.grade(1.0), '심각'); eq(B.grade(2.4), '심각');
});

t('열린 출구를 부하율 오름차순으로 준다', () => {
  const r = B.rank(fc({ '여의도(5)': { 21: at(0.85) }, '신길(1·5)': { 21: at(0.14) }, '샛강(9)': { 21: at(0.62) } }), '21');
  eq(r.open.length, 3);
  eq(r.open[0].dk, '신길(1·5)'); eq(r.open[2].dk, '여의도(5)');
  ok(r.open[0].load < r.open[1].load && r.open[1].load < r.open[2].load, '오름차순이 아니다');
});

t('통제와 데이터 없음을 구분한다 (결함 대장 M2)', () => {
  // index.html 은 load==null 을 통제로 렌더해 결손을 "무정차 통과"로 오표시했다. 새 화면은 나눈다.
  const r = B.rank(fc({
    '여의나루(5)': { 21: { load: null, closed: true } },
    '샛강(9)': { 21: { load: null, closed: false } },
    '신길(1·5)': { 21: at(0.2) },
  }), '21');
  eq(r.closed.length, 1, '통제는 1건'); eq(r.closed[0].dk, '여의나루(5)');
  eq(r.missing.length, 1, '데이터 없음은 1건'); eq(r.missing[0].dk, '샛강(9)');
  ok(!r.missing[0].note.includes('무정차'), '결손을 통제 문구로 말하면 안 된다');
});

t('통제 문구가 시간대별로 다르고 단정하지 않는다 (H2)', () => {
  const n20 = B.closedNote('20'), n21 = B.closedNote('21'), nd = B.closedNote('19');
  ok(n20 !== n21, '20시와 21시 문구가 같다');
  ok(/현장 확인/.test(n20), '20시에는 조기 무정차 이력을 알려야');
  ok(/21:40/.test(n21), '21시에는 해제 시각을 알려야');
  ok(typeof nd === 'string' && nd.length > 0, '기본 문구가 없다');
});

t('대기 시간이 있으면 분으로, 없으면 줄 길이 말로 준다', () => {
  const r = B.rank(fc({ '여의도(5)': { 21: at(0.9, { wait_min: 12 }) }, '신길(1·5)': { 21: at(0.2) }, '샛강(9)': { 21: at(0.85) } }), '21');
  const by = Object.fromEntries(r.open.map(x => [x.dk, x.note]));
  ok(/12분/.test(by['여의도(5)']), `대기 분이 없다: ${by['여의도(5)']}`);
  ok(/줄 거의 없음/.test(by['신길(1·5)']), `여유 문구가 없다: ${by['신길(1·5)']}`);
  ok(/줄/.test(by['샛강(9)']), `경계 문구가 없다: ${by['샛강(9)']}`);
  eq(r.open.length, 3, 'latest.json 에 없는 키는 무시한다');
});

t('예측이 없으면 실적 폴백으로 내려가고 그렇다고 말한다', () => {
  const r = B.rank(fc({}), '21');
  eq(r.mode, 'fallback');
  ok(r.open.length >= 5, '폴백에도 출구가 나와야');
  ok(/2024|2025|실적/.test(r.modeNote), `모드 설명이 없다: ${r.modeNote}`);
});

t('사전 예측표는 live 가 아니라 prior 로 표시된다 (M6)', () => {
  const r = B.rank(fc({ '신길(1·5)': { 21: at(0.14) } }, { prior: true }), '21');
  eq(r.mode, 'prior');
  ok(!/실시간/.test(r.modeNote), '사전 예측을 실시간으로 말하면 안 된다');
});

t('α 는 관측이 있을 때만 값으로 준다 (M6)', () => {
  eq(B.alphaLabel({ prior: true, alpha: 1 }), '사전값 1.00 (관측 전)');
  eq(B.alphaLabel({}), '—');
  eq(B.alphaLabel({ alpha: 1.24, assimilation: { n_obs: { alighting: 3, boarding: 2 } } }), '1.24');
});

t('신선도를 분으로 재고 12시간 넘으면 사전으로 물러난다', () => {
  const now = Date.parse('2026-09-05T21:00:00');
  eq(B.ageMin('2026-09-05T20:45:00', now), 15);
  eq(B.isStale('2026-09-05T20:45:00', now), false);
  eq(B.isStale('2026-09-05T08:00:00', now), true);
  eq(B.ageMin(null, now), null);
});

t('출구 사전이 latest.json 키와 맞는다', () => {
  const dks = B.EXITS.map(e => e.dk);
  eq(new Set(dks).size, dks.length, '중복 키');
  eq(dks.length, 7, '출구 7개여야');
  for (const e of B.EXITS) { ok(e.name && e.desc && e.ll, `필드 누락: ${e.dk}`); }
});

t('방향별 오프라인 플랜 4개가 있다', () => {
  ok(B.PLANS.length === 4, `플랜 ${B.PLANS.length}개`);
  for (const p of B.PLANS) ok(p.items.length >= 2, `${p.title} 항목 부족`);
});

t('수집이 끊기면 발행이 신선해도 실시간이라 말하지 않는다', () => {
  const now = Date.parse('2026-09-05T22:00:00');
  const pub = '2026-09-05T21:58:00';            // 발행은 2분 전 — 화면은 이것만 보고 "실시간"이라 했다 (H10)
  const fresh = { data_freshness: { citydata: { last_ok: '2026-09-05T21:56:00' }, subway: { last_ok: '2026-09-05T21:57:00' } } };
  const dead = { data_freshness: { citydata: { last_ok: '2026-09-05T21:20:00' }, subway: { last_ok: '2026-09-05T21:20:00' } },
                 degraded_sources: ['citydata', 'subway'] };
  const live = B.freshness(fresh, pub, now);
  eq(live.reason, 'live'); eq(live.live, true); eq(live.srcAge, 4);
  const gone = B.freshness(dead, pub, now);
  eq(gone.reason, 'collection'); eq(gone.live, false); eq(gone.warn, true); eq(gone.srcAge, 40);
  // degraded_sources 가 비어 있어도 나이만으로 잡는다 (nowcast 가 옛 스키마일 때 대비)
  eq(B.freshness({ data_freshness: { citydata: { last_ok: '2026-09-05T21:20:00' } } }, pub, now).reason, 'collection');
});

t('수집 시작 전과 수집 끊김을 구분한다', () => {
  const now = Date.parse('2026-09-05T22:00:00');
  const pre = { data_freshness: { citydata: { last_ok: null }, subway: { last_ok: null } } };
  eq(B.freshness(pre, '2026-09-05T21:58:00', now).reason, 'pre');
  // 원천은 신선한데 발행이 늦은 경우는 또 다른 상태다
  eq(B.freshness({ data_freshness: { citydata: { last_ok: '2026-09-05T21:56:00' } } }, '2026-09-05T21:00:00', now).reason, 'publish');
});

process.stdout.write(JSON.stringify(results));
