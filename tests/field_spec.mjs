// docs/app/field.js 의 GP 회귀 검증. pytest(tests/test_field.py)가 node 로 실행하고 결과 JSON 을 읽는다.
//   node tests/field_spec.mjs
import { createRequire } from 'node:module';
import path from 'node:path';
import url from 'node:url';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(path.dirname(url.fileURLToPath(import.meta.url)));
const F = require(path.join(ROOT, 'docs', 'app', 'field.js'));

const results = [];
const t = (name, fn) => {
  try { fn(); results.push({ name, ok: true }); }
  catch (e) { results.push({ name, ok: false, detail: String(e && e.message || e).slice(0, 300) }); }
};
const near = (a, b, tol, msg) => { if (!(Math.abs(a - b) <= tol)) throw new Error(`${msg || ''} ${a} vs ${b} (tol ${tol})`); };
const ok = (c, msg) => { if (!c) throw new Error(msg || 'false'); };

// 여의도 근방 좌표 — 격자는 작게 잡아 테스트를 가볍게
const GRID = { x0: 126.92, y0: 37.52, dx: 0.002, dy: 0.002, cols: 8, rows: 6 };
const KERNEL = { varShort: 0.125, lenShort: 150, varLong: 0.125, lenLong: 700 };
const PRIOR = 0.33;
const at = (f, ix, iy) => f.mean[iy * f.cols + ix];
const sdAt = (f, ix, iy) => f.sd[iy * f.cols + ix];
const cellCenter = (ix, iy) => [GRID.x0 + (ix + 0.5) * GRID.dx, GRID.y0 + (iy + 0.5) * GRID.dy];

// ── 커널 ──
t('matern32 는 r=0 에서 분산이고 단조 감소한다', () => {
  near(F.matern32(0, 300), 1, 1e-12, 'r=0');
  const v = [0, 50, 150, 400, 1000].map(r => F.matern32(r, 300));
  for (let i = 1; i < v.length; i++) ok(v[i] < v[i - 1], `단조 감소 아님 @${i}`);
  ok(v[v.length - 1] < 0.05, '먼 거리에서 0 으로 수렴해야');
});

// ── 촐레스키 ──
t('cholesky 가 A 를 복원한다', () => {
  const A = [[4, 1, 0.5], [1, 3, 0.2], [0.5, 0.2, 2]];
  const L = F.cholesky(A);
  ok(L, 'PD 인데 null');
  for (let i = 0; i < 3; i++) for (let j = 0; j <= i; j++) {
    let s = 0; for (let k = 0; k <= j; k++) s += L[i][k] * L[j][k];
    near(s, A[i][j], 1e-9, `복원 (${i},${j})`);
  }
});

t('cholesky 가 비-PD 에 null 을 준다', () => {
  ok(F.cholesky([[1, 2], [2, 1]]) === null, '비-PD 인데 null 아님');
});

// ── 관측 노이즈: 배제하지 않고 신뢰도를 σ 로 ──
t('보정 카메라가 미보정보다 σ 가 작다', () => {
  const cal = F.obsNoise({ kind: 'cctv_calibrated' });
  const unc = F.obsNoise({ kind: 'cctv_uncalibrated' });
  ok(cal < unc, `보정 ${cal} < 미보정 ${unc} 이어야`);
});

t('confidence low 는 배제가 아니라 σ 확대다', () => {
  const good = F.obsNoise({ kind: 'cctv_calibrated' });
  const low = F.obsNoise({ kind: 'cctv_calibrated', confidence: 'low' });
  ok(low > good, 'low 가 더 커야');
  ok(Number.isFinite(low), '유한해야 — 배제(∞)가 아니다');
});

t('flags 가 많을수록 σ 가 커진다', () => {
  const a = F.obsNoise({ kind: 'cctv_calibrated', flags: [] });
  const b = F.obsNoise({ kind: 'cctv_calibrated', flags: ['low_light'] });
  const c = F.obsNoise({ kind: 'cctv_calibrated', flags: ['low_light', 'bg_fail'] });
  ok(a < b && b < c, `${a} < ${b} < ${c} 이어야`);
});

t('오래된 관측일수록 σ 가 커진다 (M3 스테일을 하드컷 대신 감쇠로)', () => {
  const s = [0, 15, 30, 60, 120].map(m => F.obsNoise({ kind: 'cctv_calibrated', ageMin: m }));
  for (let i = 1; i < s.length; i++) ok(s[i] > s[i - 1], `단조 증가 아님 @${i}`);
  ok(s[4] > 4 * s[0], '2시간이면 크게 벌어져야');
});

t('중복 투입은 σ 를 √n 배 해 정보량을 1건으로 유지한다', () => {
  const one = F.obsNoise({ kind: 'poi' });
  const five = F.obsNoise({ kind: 'poi', dup: 5 });
  near(five / one, Math.sqrt(5), 1e-9, 'dup=5');
});

// ── GP 사후 ──
t('관측 없으면 전부 사전 평균, 불확실성 최대', () => {
  const f = F.buildField({ observations: [], grid: GRID, prior: PRIOR, kernel: KERNEL });
  for (let i = 0; i < f.mean.length; i++) near(f.mean[i], PRIOR, 1e-12, `칸 ${i}`);
  const full = Math.sqrt(KERNEL.varShort + KERNEL.varLong);
  for (let i = 0; i < f.sd.length; i++) near(f.sd[i], full, 1e-9, `sd 칸 ${i}`);
});

t('관측점에서는 관측값 쪽으로 끌리고, 멀어지면 사전으로 돌아온다', () => {
  const p = cellCenter(1, 1);
  const f = F.buildField({
    observations: [{ x: p, y: 1.0, sigma: 0.05 }],
    grid: GRID, prior: PRIOR, kernel: KERNEL,
  });
  const near_ = at(f, 1, 1), far_ = at(f, 7, 5);
  ok(near_ > 0.8, `관측점 근처가 관측값에 가까워야: ${near_}`);
  near(far_, PRIOR, 0.05, '먼 곳은 사전으로');
  ok(sdAt(f, 1, 1) < sdAt(f, 7, 5), '관측점 근처 불확실성이 더 작아야');
});

t('σ 가 큰 관측은 사후를 덜 끌어당긴다', () => {
  const p = cellCenter(1, 1);
  const mk = sigma => at(F.buildField({
    observations: [{ x: p, y: 1.0, sigma }], grid: GRID, prior: PRIOR, kernel: KERNEL,
  }), 1, 1);
  const tight = mk(0.05), loose = mk(0.60);
  ok(tight > loose, `σ 작을수록 더 끌려야: ${tight} vs ${loose}`);
  ok(loose > PRIOR, '그래도 사전보다는 관측 쪽');
});

t('신뢰 낮은 관측 하나가 신뢰 높은 관측을 뒤집지 못한다', () => {
  const p = cellCenter(2, 2);
  const f = F.buildField({
    observations: [
      { x: p, y: 0.0, sigma: 0.05 },                       // 보정 카메라: 한산
      { x: [p[0] + 0.0002, p[1]], y: 1.0, sigma: 0.60 },   // 미보정·저신뢰: 심각 오탐
    ],
    grid: GRID, prior: PRIOR, kernel: KERNEL,
  });
  ok(at(f, 2, 2) < 0.3, `저신뢰 오탐에 끌려가면 안 됨: ${at(f, 2, 2)}`);
});

t('같은 지점 중복 관측이 수치적으로 폭주하지 않는다', () => {
  const p = cellCenter(3, 2);
  const obs = Array.from({ length: 6 }, () => ({ x: p, y: 0.8, sigma: 0.2 }));
  const f = F.buildField({ observations: obs, grid: GRID, prior: PRIOR, kernel: KERNEL });
  ok(f.ok, 'PD 실패 — jitter 폴백이 없다');
  for (let i = 0; i < f.mean.length; i++) ok(Number.isFinite(f.mean[i]), `NaN/Inf 칸 ${i}`);
  ok(at(f, 3, 2) > 0.5 && at(f, 3, 2) <= 1.0, `범위 밖: ${at(f, 3, 2)}`);
});

t('사후 표준편차는 사전 표준편차를 넘지 않는다', () => {
  const f = F.buildField({
    observations: [{ x: cellCenter(2, 3), y: 0.9, sigma: 0.1 }],
    grid: GRID, prior: PRIOR, kernel: KERNEL,
  });
  const full = Math.sqrt(KERNEL.varShort + KERNEL.varLong);
  for (let i = 0; i < f.sd.length; i++) {
    ok(f.sd[i] >= 0, `음수 sd 칸 ${i}`);
    ok(f.sd[i] <= full + 1e-9, `사전 초과 칸 ${i}: ${f.sd[i]}`);
  }
});

t('등급 사상은 서울시 4단계를 0·⅓·⅔·1 로 보낸다', () => {
  near(F.gradeToUnit('여유'), 0, 1e-12);
  near(F.gradeToUnit('보통'), 1 / 3, 1e-12);
  near(F.gradeToUnit('약간 붐빔'), 2 / 3, 1e-12);
  near(F.gradeToUnit('붐빔'), 1, 1e-12);
  ok(F.gradeToUnit('보정전') === null, '알 수 없는 등급은 null');
});

t('밀도는 서울시 3/4/5명/m² 기준으로 0~1 에 사상된다', () => {
  near(F.densityToUnit(0), 0, 1e-12);
  near(F.densityToUnit(5), 1, 1e-12);
  ok(F.densityToUnit(3) > 0 && F.densityToUnit(3) < 1);
  near(F.densityToUnit(9), 1, 1e-12, '상한 클램프');
});

t('불확실한 값은 사후 평균이 아니라 사후 표준편차로 드러난다', () => {
  // 같은 관측값이라도 σ 가 크면 sd 가 크게 남아야 한다 (화면에서 흐리게 표시할 근거)
  const p = cellCenter(4, 3);
  const sd = sigma => sdAt(F.buildField({
    observations: [{ x: p, y: 0.7, sigma }], grid: GRID, prior: PRIOR, kernel: KERNEL,
  }), 4, 3);
  ok(sd(0.6) > sd(0.05), '저신뢰 관측은 불확실성을 더 남겨야');
});


t('unitToGrade 는 서울시 인파밀집 기준(3/4/5명/m²)을 등급으로 되돌린다', () => {
  ok(F.unitToGrade(F.densityToUnit(1.0)) === '여유', '1명/m²');
  ok(F.unitToGrade(F.densityToUnit(3.0)) === '주의', '3명/m²');
  ok(F.unitToGrade(F.densityToUnit(4.0)) === '경계', '4명/m²');
  ok(F.unitToGrade(F.densityToUnit(5.0)) === '심각', '5명/m²');
  ok(F.unitToGrade(-0.2) === '여유' && F.unitToGrade(1.5) === '심각', '범위 밖 클램프');
});

t('levelToUnit 은 밀도 등급을 밴드 중앙값으로 되돌린다 (unitToGrade 와 왕복)', () => {
  ['여유','주의','경계','심각'].forEach(g => {
    const u = F.levelToUnit(g);
    ok(u != null, g + ' 매핑 없음');
    ok(F.unitToGrade(u) === g, `왕복 실패: ${g} → ${u} → ${F.unitToGrade(u)}`);
  });
  ok(F.levelToUnit('보정전') === null, '보정 전은 값이 없다');
  ok(F.levelToUnit('여유') < F.levelToUnit('주의'), '단조');
  ok(F.levelToUnit('주의') < F.levelToUnit('경계'), '단조');
  ok(F.levelToUnit('경계') < F.levelToUnit('심각'), '단조');
});

t('infoWeight 는 관측이 사후에 실제로 기여하는 정도를 0~1 로 준다', () => {
  const kxx = KERNEL.varShort + KERNEL.varLong;
  near(F.infoWeight(0, kxx), 1, 1e-12, 'σ=0 이면 관측이 사후를 완전히 결정');
  ok(F.infoWeight(0.1, kxx) > 0.9, '정밀 관측');
  ok(F.infoWeight(99, kxx) < 0.01, '3일 지난 관측은 사실상 기여 없음');
  const w = [0.05, 0.2, 0.5, 2, 99].map(s => F.infoWeight(s, kxx));
  for (let i = 1; i < w.length; i++) ok(w[i] < w[i - 1], `σ 커지면 단조 감소 아님 @${i}`);
  // 사후 축소와 일치해야 한다: 관측점에서 μ 는 사전에서 관측 쪽으로 정확히 w 만큼 간다
  const p = cellCenter(2, 2), y = 1.0, sigma = 0.3;
  const f = F.buildField({ observations: [{ x: p, y, sigma }], grid: GRID, prior: PRIOR, kernel: KERNEL });
  near(at(f, 2, 2), PRIOR + F.infoWeight(sigma, kxx) * (y - PRIOR), 1e-6, '사후 축소와 불일치');
});

t('autoPrior 는 관측들의 신뢰도 가중 평균으로 사전을 잡되, 관측이 적으면 기본값에 붙는다', () => {
  const kxx = KERNEL.varShort + KERNEL.varLong;
  // 관측 0 → 기본값
  near(F.autoPrior([], kxx, .3), .3, 1e-12, '관측 없음');
  // 신뢰 높은 관측이 여럿이면 그쪽으로
  // 가짜 관측 PRIOR_PSEUDO 건이 섞이므로 관측 평균에 '근접' 하되 넘지는 않는다.
  // 관측 12건(σ=0.1) 이면 기본값이 약 20% 남는다 — 관측이 적을수록 보수적이라는 뜻이다.
  const many = Array.from({length: 12}, (_, i) => ({x:[126.93+i*.002,37.52], y:.8, sigma:.1}));
  const pm = F.autoPrior(many, kxx, .3);
  ok(pm > .65 && pm < .8, `다수 관측이면 관측 평균 쪽으로 (넘지는 않게): ${pm}`);
  // 관측 1건이 지도 전체를 정하면 안 된다
  const one = [{x:[126.93,37.52], y:1.0, sigma:.1}];
  const p1 = F.autoPrior(one, kxx, .3);
  ok(p1 > .3 && p1 < .6, `1건은 절제되어야: ${p1}`);
  // σ 가 큰 관측은 덜 끌어당긴다
  const tight = F.autoPrior([{x:[126.93,37.52],y:1,sigma:.1}], kxx, .3);
  const loose = F.autoPrior([{x:[126.93,37.52],y:1,sigma:.9}], kxx, .3);
  ok(tight > loose, `σ 작을수록 더 끌어야: ${tight} vs ${loose}`);
});

t('사전이 관측 수준을 따르면 주의급 관측이 여유로 주저앉지 않는다', () => {
  // 미보정 카메라(σ=0.30) 하나가 0.70(주의) 을 보는데 주변도 붐비는 상황
  const around = [];
  for (let i = 0; i < 8; i++) around.push({x:[126.925+i*.004, 37.523+ (i%2)*.004], y:.72, sigma:.30});
  const grid = { x0:126.92, y0:37.518, dx:.002, dy:.002, cols:10, rows:8 };
  const at0 = (f) => f.mean[Math.round((37.523-grid.y0)/grid.dy)*grid.cols + Math.round((126.925-grid.x0)/grid.dx)];
  const fixed = F.buildField({observations: around, grid, prior:.3, kernel:KERNEL});
  const auto  = F.buildField({observations: around, grid, prior:null, kernel:KERNEL});
  ok(at0(fixed) < .63, `고정 사전이면 여유로 주저앉는다(재현): ${at0(fixed)}`);
  ok(at0(auto) >= .63, `자동 사전이면 주의 밴드에 남아야: ${at0(auto)}`);
});

process.stdout.write(JSON.stringify(results));
process.exit(results.every(r => r.ok) ? 0 : 1);
