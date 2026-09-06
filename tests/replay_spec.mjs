// docs/app/replay.js (발행 스냅샷 재생 — URL 해석·경로·이웃 칩·시계) 검증. pytest(tests/test_replay.py)가 node 로 실행한다.
//   node tests/replay_spec.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import url from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(url.fileURLToPath(import.meta.url)));
const R = require(path.join(ROOT, 'docs', 'app', 'replay.js'));

const results = [];
const t = (name, fn) => {
  try { fn(); results.push({ name, ok: true }); }
  catch (e) { results.push({ name, ok: false, detail: String((e && e.message) || e).slice(0, 300) }); }
};
const ok = (c, msg) => { if (!c) throw new Error(msg || 'false'); };
const eq = (a, b, msg) => { if (a !== b) throw new Error(`${msg || ''} ${JSON.stringify(a)} !== ${JSON.stringify(b)}`); };

t('?at=YYYYMMDDTHHMM 을 해석한다', () => {
  const r = R.parse('?at=20260905T2206');
  eq(r.at, '20260905T2206'); eq(r.date, '20260905'); eq(r.hhmm, '2206'); eq(r.label, '2026-09-05 22:06');
});
t('없거나 틀린 at 은 null (실시간)', () => {
  eq(R.parse(''), null); eq(R.parse('?x=1'), null); eq(R.parse('?at=2026-09-05'), null);
  eq(R.parse('?at=20260905T2560'), null, '분 60 이상'); eq(R.parse('?at=20260905T2406'), null, '시 24 이상');
});
t('다른 파라미터와 섞여도 잡는다', () => {
  eq(R.parse('?theme=light&at=20260905T2131').hhmm, '2131');
});
t('시계는 발행 스냅샷과 같은 규약(로컬 naive)이다 — ageMin 이 Date.parse 로 로컬로 읽는다', () => {
  const r = R.parse('?at=20260905T2206'), d = new Date(r.now);
  eq(d.getFullYear(), 2026); eq(d.getMonth(), 8); eq(d.getDate(), 5); eq(d.getHours(), 22); eq(d.getMinutes(), 6);
  const age = Math.round((r.now - Date.parse('2026-09-05T22:06:53')) / 60000);
  ok(Math.abs(age) <= 1, '같은 분 발행분의 나이는 0~1분');
});
t('재생 파일 경로', () => {
  const r = R.parse('?at=20260905T2206');
  eq(R.file(r), 'data/replay/20260905/2206.json'); eq(R.index(r), 'data/replay/20260905/index.json');
});
t('링크 — 재생·실시간', () => {
  eq(R.href('go.html', '20260905T2131'), 'go.html?at=20260905T2131');
  eq(R.href('index.html', '20260905T2206'), 'index.html?at=20260905T2206');
});
t('이웃 칩 — 양 끝은 null', () => {
  const chips = [{ at: '2005' }, { at: '2101' }, { at: '2206' }];
  const m = R.neighbors(chips, '2101'); eq(m.prev, '2005'); eq(m.next, '2206');
  eq(R.neighbors(chips, '2005').prev, null); eq(R.neighbors(chips, '2206').next, null);
  eq(R.neighbors(chips, '9999').prev, null);
});

process.stdout.write(JSON.stringify(results));
