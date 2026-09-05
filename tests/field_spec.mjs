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
  // 2026-09-05: 서울시 도시데이터는 발행 자체가 28분 늦다(9/4 17:08~9/5 16:38 실측, 28.8분 일정). 그건 낡음이 아니라 시차다.
  // 전엔 이 28분을 나이로 깎아 σ 가 1.1 까지 불어 「붐빔」이 장에서 사실상 무시됐다.
  near(F.obsNoise({ kind: 'poi', ageMin: F.POI_LAG_MIN }), one, 1e-9, '시차만큼의 나이는 페널티 0');
  near(F.obsNoise({ kind: 'poi', ageMin: F.POI_LAG_MIN + 15 }), one * Math.sqrt(2), 1e-9, '시차 뒤 15분이면 √2');
  near(F.obsNoise({ kind: 'cctv_uncalibrated', ageMin: 15 }), 0.30 * Math.sqrt(2), 1e-9, 'CCTV 는 시차 보정 없음');
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

/* ── 혼잡도별 보행 속도·시간 (경로 비용의 근거) ────────────────────
   경로를 "거리 × 벌점(1.25)" 으로 고르던 것을 "실제 걸리는 시간" 으로 바꾼다.
   1.25 는 출처가 없었고, 최소화 대상이 사람이 신경 쓰는 값도 아니었다. */
t('walkSpeed: 자유보행 1.34 m/s 에서 시작해 밀도가 오르면 단조 감소', () => {
  near(F.walkSpeed(0), 1.34, 1e-9, '밀도 0');
  let prev = Infinity;
  for (const r of [0.5, 1, 1.5, 2, 3, 4, 5]) {
    const v = F.walkSpeed(r);
    ok(v < prev, `밀도 ${r} 에서 속도가 안 줄었다`);
    prev = v;
  }
});
t('walkSpeed: 정체 하한 0.15 아래로 안 떨어진다 (원식은 0.04 까지 간다)', () => {
  ok(F.walkSpeed(5.4) >= 0.15 - 1e-12, '하한 미달');
  ok(F.walkSpeed(99) >= 0.15 - 1e-12, '극단 밀도에서 하한 미달');
});
t('walkSpeed: nowcast.kladek 과 같은 값 (Weidmann 1993, v0 1.34 · ρmax 5.4 · γ 1.913)', () => {
  const ref = r => Math.max(0.15, 1.34 * (1 - Math.exp(-1.913 * (1 / r - 1 / 5.4))));
  for (const r of [0.5, 1.5, 3.0, 4.0]) near(F.walkSpeed(r), ref(r), 1e-12, `밀도 ${r}`);
});
t('unitToDensity: 등급 대표값(여유0.5·주의3.0·경계4.0·심각5.0)을 지난다', () => {
  // 2026-09-05 정정: 여유 1.5 는 이미 붐비는 인도(2.9km/h)라 한산한 시각에도 여의도역 1.5km 가 32분으로 읽혔다.
  // 여유 = 0.5명/m²(4.7km/h). 주의 이상은 그대로 — 붐비면 느려지는 성질은 유지한다.
  near(F.unitToDensity(0.3), 0.5, 1e-12, '여유');
  near(F.unitToDensity(0.7), 3.0, 1e-12, '주의');
  near(F.unitToDensity(0.9), 4.0, 1e-12, '경계');
  near(F.unitToDensity(1.0), F.DENSITY_SEVERE, 1e-12, '심각');
  ok(F.unitToDensity(0) < 0.5, '완전히 빈 곳이 여유보다 덜해야 한다');
  ok(F.walkSpeed(F.unitToDensity(0.3)) * 3.6 > 4.5, '여유는 4.5km/h 넘게 걷는다');
  let prev = -1;                       // 단조 증가여야 경로 비용이 뒤집히지 않는다
  for (let u = 0; u <= 1.0001; u += 0.05) { const d = F.unitToDensity(u); ok(d > prev, `u ${u.toFixed(2)}`); prev = d; }
});
t('walkSeconds: 거리 ÷ 속도. 혼잡할수록 오래 걸린다', () => {
  const free = F.walkSeconds(1000, 0), busy = F.walkSeconds(1000, 0.7), jam = F.walkSeconds(1000, 1);
  // 장의 바닥(u=0, 완전히 빈 곳)은 unitToDensity(0) — 2026-09-05 부터 0.3명/m²(자유보행). 붐빔은 등급이 말한다.
  near(free, 1000 / F.walkSpeed(F.unitToDensity(0)), 1e-9, '장 바닥');
  ok(free < 1000 / 1.0, '그래도 가장 빠른 축이어야 한다');
  ok(busy > free * 2, `주의(3명/m²)면 두 배 넘게 걸려야 한다 — ${busy} vs ${free}`);
  ok(jam > busy, '심각이 주의보다 오래 걸려야 한다');
});
t('walkSeconds: 같은 밀도면 거리에 비례한다', () => {
  near(F.walkSeconds(2000, 0.5), 2 * F.walkSeconds(1000, 0.5), 1e-9);
});

/* ── 확신도 혼합 밀도 (경로 비용 = 표시 시간, 한 함수) ───────────────
   본 곳은 관측 밀도, 못 본 곳은 가로 기본(STREET_RHO — 2026-09-05 부터 0.8명/m², 4.2km/h). 장의 σ 에서 확신도 cn 을 얻어 섞는다.
   2026-09-04: 라우터가 장 전체를 믿고 표시가 300m 만 믿어 "더 돌게 하고 더 느리다고 말하는"
   모순이 났다. 사전 0.3 + σ 0.3 수축이 카메라 없는 곳까지 2.25명/m² 로 읽어 우회를 눌렀다. */
t('confidence: σ 가 사전 폭이면 0, 0 이면 1, 단조 감소', () => {
  const sdMax = Math.sqrt(0.25);
  near(F.confidence(sdMax, sdMax), 0, 1e-12, 'σ=sdMax');
  near(F.confidence(0, sdMax), 1, 1e-12, 'σ=0');
  let prev = 2;
  for (const sd of [0, 0.1, 0.2, 0.3, 0.4, 0.5]) { const c = F.confidence(sd, sdMax); ok(c <= prev + 1e-12, `σ ${sd}`); prev = c; }
  ok(F.confidence(0.6, sdMax) === 0, '사전 폭보다 큰 σ 는 0 으로 잘린다');
});
t('confidence: 미보정 카메라 바로 위(conf≈0.49)도 cn=1 — index.html 과 같은 0.15 정규화', () => {
  const sdMax = Math.sqrt(0.25);
  ok(F.confidence(sdMax * (1 - 0.15), sdMax) >= 1 - 1e-12, 'conf 0.15 에서 이미 1');
});
t('blendDensity: cn=1 이면 관측 밀도, cn=0 이면 가로 기본, 사이는 선형', () => {
  const sdMax = Math.sqrt(0.25);
  near(F.blendDensity(0.9, 0, sdMax), F.unitToDensity(0.9), 1e-12, '확신');
  near(F.blendDensity(0.9, sdMax, sdMax), F.STREET_RHO, 1e-12, '무지');
  ok(F.STREET_RHO <= 0.8 && F.walkSpeed(F.STREET_RHO) * 3.6 > 4.0, '못 본 길은 4km/h 넘게 걷는다 (2026-09-05)');
  const mid = F.blendDensity(0.9, sdMax * (1 - 0.075), sdMax);          // cn = 0.5
  near(mid, 0.5 * F.unitToDensity(0.9) + 0.5 * F.STREET_RHO, 1e-9, '반반');
});
t('blendDensity: 못 본 곳이 한산한 관측보다 느리게 읽히지 않는다 (사전 수축 제거의 요점)', () => {
  const sdMax = Math.sqrt(0.25);
  // 옛 방식: 사전으로 수축한 u≈0.5 → 2.25명/m². 새 방식: 못 본 곳 = 1.5
  ok(F.blendDensity(0.5, sdMax, sdMax) <= F.STREET_RHO + 1e-12, '못 본 곳은 가로 기본 이하');
});
t('blendSeconds: 거리 ÷ 속도(혼합 밀도). σ=0 이면 walkSeconds 와 같다', () => {
  const sdMax = Math.sqrt(0.25);
  near(F.blendSeconds(1000, 0.7, 0, sdMax), F.walkSeconds(1000, 0.7), 1e-9, '확신 = 옛 값');
  near(F.blendSeconds(1000, 0.9, sdMax, sdMax), 1000 / F.walkSpeed(F.STREET_RHO), 1e-9, '무지 = 가로 속도');
  ok(F.blendSeconds(1000, 0.9, 0, sdMax) > F.blendSeconds(1000, 0.9, sdMax, sdMax), '본 곳의 심각이 못 본 곳보다 느려야');
});

process.stdout.write(JSON.stringify(results));
process.exit(results.every(r => r.ok) ? 0 : 1);
