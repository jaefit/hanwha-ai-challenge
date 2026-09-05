/* 혼잡장 추정 — 신뢰도가 제각각인 이종 관측을 가우시안 과정 회귀로 하나의 장에 합친다.
 *
 * 작성 2026-09-01. 검증: tests/field_spec.mjs (pytest tests/test_field.py 가 node 로 실행)
 *
 * 왜 이렇게 하나
 *   관측이 CCTV 23대(그중 ROI 보정 5대만 명/m² 실측) + 서울시 구역 등급뿐이다. 격자는 수천 칸이다.
 *   신뢰 못 할 관측을 버리면 정보가 0이 된다. 대신 관측마다 노이즈 σ 를 다르게 줘서 약한 정보로 살린다.
 *   사후 평균은 색으로, 사후 표준편차는 채도로 낸다 — 아는 곳과 모르는 곳이 그림에 그대로 드러나게.
 *
 *   y_i = C(x_i) + ε_i,  ε_i ~ N(0, σ_i²)
 *   μ(x) = m₀ + k(x)ᵀ(K+Σ)⁻¹(y − m₀)
 *   s²(x) = k(x,x) − k(x)ᵀ(K+Σ)⁻¹k(x)
 *
 * 가정 (전부 미검증 — T10 에서 LOO 교차검증으로 교체할 것)
 *   커널      Matérn 3/2. RBF 는 무한 미분가능이라 인파 장에 과하게 매끄럽다.
 *   길이척도  짧은 쪽 150m(카메라 시야 규모) · 긴 쪽 1,200m(구역 규모).
 *             근거 후보: 관측 주기 5분 동안 ρ=3명/m² 에서 보행 이동 ≈ 99m (보고서 §3.2 속도식).
 *   노이즈    보정 CCTV 0.10 · 미보정 CCTV 0.30 · 구역 등급 0.20.
 *             미보정은 점유율 기준 임시 등급이라(collector_cctv.py) 화각·설치각 의존이 크다.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.Field = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SQRT3 = Math.sqrt(3);

  // 서울시 인파밀집 기준 3/4/5명/m² — 5 를 상한으로 0~1 에 사상
  var DENSITY_SEVERE = 5;
  // 서울시 실시간 도시데이터 혼잡도 4단계
  var GRADES = { "여유": 0, "보통": 1 / 3, "약간 붐빔": 2 / 3, "붐빔": 1 };

  // 보행 속도-밀도 (Weidmann 1993 Kladek). src/nowcast.py kladek() 과 같은 값이어야 한다 —
  // 두 곳이 갈리면 화면이 말하는 소요 시간과 모델이 쓰는 지연이 어긋난다.
  var V_FREE = 1.34;      // 자유보행 m/s
  var RHO_JAM = 5.4;      // 정체 밀도 명/m²
  var KLADEK_G = 1.913;
  var V_MIN = 0.15;       // 하한(추정). 원식은 5명/m² 에서 0.04 m/s 까지 떨어져 비현실적이다
  // 못 본 곳의 기본 밀도(가로, 명/m²). 관측이 없는 곳을 사전 평균(0.3~0.5 → 1.5~2.25)으로 읽으면
  // 카메라 없는 이면도로까지 붐비는 것으로 보여 우회가 사라진다. 확신도로 관측과 이 값을 섞는다.
  // 2026-09-05 정정: 1.5(2.9km/h)는 이미 붐비는 인도라 한산한 시각에도 느리게 읽혔다 → 0.8(4.2km/h). 가정값, 출처 없음.
  // nowcast 의 도달 지연(첫 300m 3.0·이후 1.5)은 그대로다 — 이건 화면의 걷는 시간·경로 비용만 바꾼다.
  var STREET_RHO = 0.8;
  var CONF_FULL = 0.15;   // index.html 과 같은 정규화 — 미보정 카메라 바로 위(conf≈0.49)도 '충분히 안다'

  var BASE_SIGMA = { cctv_calibrated: 0.10, cctv_uncalibrated: 0.30, poi: 0.20 };
  var LOW_CONFIDENCE_MULT = 2.5;   // 배제가 아니라 확대 — 오탐이 사후를 못 끌게
  var FLAG_MULT = 1.3;             // 플래그(저조도·배경차분 실패·밀도 포화) 하나당
  var AGE_HALF_MIN = 15;           // 이 분만큼 지나면 σ 가 √2 배. 2시간이면 8배 ≈ 사전으로 회귀
  // 서울시 도시데이터(poi)는 발행 자체가 늦다 — ppltn_time 이 수신보다 28.8분 뒤, 9/4 17:08~9/5 16:38 전 틱에서 일정(실측).
  // 그건 낡음이 아니라 시차라 나이에서 뺀다. 전엔 이 28분을 깎아 σ 가 1.1 로 불어 「붐빔」이 장에서 사실상 무시됐다(2026-09-05 정정).
  var POI_LAG_MIN = 28;

  function matern32(r, len) {
    if (!(len > 0)) return r === 0 ? 1 : 0;
    var a = SQRT3 * Math.abs(r) / len;
    return (1 + a) * Math.exp(-a);
  }

  // 위경도 → m. 다른 모듈(nowcast.haversine_m·index.html apfDistanceM)과 같은 근사를 쓴다.
  function distanceM(a, b) {
    var lat = (a[1] + b[1]) * Math.PI / 360;
    var dy = (a[1] - b[1]) * 111320;
    var dx = (a[0] - b[0]) * 111320 * Math.cos(lat);
    return Math.hypot(dx, dy);
  }

  function gradeToUnit(grade) {
    return Object.prototype.hasOwnProperty.call(GRADES, grade) ? GRADES[grade] : null;
  }

  /** 밀도(명/m²) → 보행 속도(m/s). */
  function walkSpeed(rho) {
    if (!(rho > 0)) return V_FREE;
    return Math.max(V_MIN, V_FREE * (1 - Math.exp(-KLADEK_G * (1 / rho - 1 / RHO_JAM))));
  }

  // 등급 → 밀도 사다리. LEVEL_UNIT 의 역이다. 선형(u×5)으로 사상하면 「여유」가 0~3 으로 퍼져 한산한 시각에도 느리게 읽힌다.
  // 2026-09-05 정정: 여유 1.5 → 0.5명/m²(4.7km/h). 1.5 는 Kladek 로 2.9km/h 라 "여유"가 아니었다. 주의 3.0·경계 4.0·심각 5.0 은 그대로.
  // 사다리 값은 전부 가정(출처 없음) — 9/5 실측 뒤 다시 본다.
  var UNIT_RHO = [[0, 0.3], [0.3, 0.5], [0.7, 3.0], [0.9, 4.0], [1, DENSITY_SEVERE]];

  /** 장 값 0~1 → 밀도(명/m²). 등급 대표값을 지나는 단조 증가 꺾은선. */
  function unitToDensity(u) {
    u = Math.max(0, Math.min(1, u || 0));
    for (var i = 0; i < UNIT_RHO.length - 1; i++) {
      var a = UNIT_RHO[i], b = UNIT_RHO[i + 1];
      if (u >= a[0] && u <= b[0]) {
        var t = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 0;
        return a[1] + (b[1] - a[1]) * t;
      }
    }
    return DENSITY_SEVERE;
  }

  /** 그 혼잡도에서 이 거리를 걷는 데 걸리는 초. 경로 비용이자 화면에 뜨는 시간이다.
   *  거리 × 벌점(1.25) 로 고르던 것을 여기로 바꾼다 — 벌점은 출처가 없었고,
   *  최소화 대상이 사람이 신경 쓰는 값(시간)도 아니었다. */
  // 걷는 시간에만 쓰는 속도 배율. Weidmann 식은 3.5명/m² 에서 0.8 km/h 까지 떨어져 서울시 「붐빔」 배경 관측이 깔린
  // 광장 일대에서 여의도역 1.4km 가 72분으로 읽혔다(2026-09-05 22:10). 22:20 에 바닥 2.2 km/h 를 넣었다가 주의·경계·심각의
  // 시간 차가 사라져 철회(22:30). 대신 시간을 1.4 로 나눈다(속도 ×1.4, 자유보행 1.34 m/s 는 넘지 않게). 등급 간 비율은 그대로.
  // 1.4 는 가정값(출처 없음). walkSpeed 자체는 nowcast.kladek 과 같은 식으로 둔다.
  var PACE_GAIN = 1.4;
  function paceSpeed(rho) { return Math.min(V_FREE, walkSpeed(rho) * PACE_GAIN); }

  function walkSeconds(meters, unit) {
    return Math.max(0, meters || 0) / paceSpeed(unitToDensity(unit));
  }

  /** 장의 σ → 확신도 0~1. σ 가 사전 폭(sdMax)이면 0. index.html 의 cn 과 같은 정규화. */
  function confidence(sd, sdMax) {
    if (!(sdMax > 0)) return 0;
    var conf = Math.max(0, 1 - (sd == null ? sdMax : sd) / sdMax);
    return Math.max(0, Math.min(1, conf / CONF_FULL));
  }

  /** 확신도 혼합 밀도. 본 곳은 관측 밀도, 못 본 곳은 가로 기본, 사이는 선형.
   *  경로를 고르는 비용과 화면에 보여주는 시간이 **같이** 이것을 쓴다 —
   *  2026-09-04: 라우터가 장 전체를 믿고 표시가 처음 300m 만 믿어 "더 돌게 하고
   *  더 느리다고 말하는" 모순이 났다. 한 함수로 합친다. */
  function blendDensity(unit, sd, sdMax) {
    var cn = confidence(sd, sdMax);
    return cn * unitToDensity(unit) + (1 - cn) * STREET_RHO;
  }

  /** 그 간선을 걷는 데 걸리는 초 — 경로 비용이자 표시 시간. */
  function blendSeconds(meters, unit, sd, sdMax) {
    return Math.max(0, meters || 0) / paceSpeed(blendDensity(unit, sd, sdMax));
  }

  function densityToUnit(rho) {
    if (rho == null || !isFinite(rho)) return null;
    return Math.max(0, Math.min(1, rho / DENSITY_SEVERE));
  }

  // 0~1 → 서울시 인파밀집 기준 등급. 3/4/5명/m² 가 그대로 0.6/0.8/1.0 에 걸린다.
  function unitToGrade(u) {
    if (u == null || !isFinite(u)) return null;
    return u >= 1 ? "심각" : u >= 0.8 ? "경계" : u >= 0.6 ? "주의" : "여유";
  }

  // 밀도 등급 → 지수. 미보정 카메라는 점유율 기준으로 등급만 나오므로(collector_cctv.level) 밴드 대표값을 쓴다.
  // 값은 unitToGrade 의 경계와 왕복하도록 잡은 밴드 중앙(심각은 상한). 밴드 폭만큼의 오차는 σ 로 흡수된다.
  var LEVEL_UNIT = { "여유": 0.3, "주의": 0.7, "경계": 0.9, "심각": 1.0 };

  function levelToUnit(level) {
    return Object.prototype.hasOwnProperty.call(LEVEL_UNIT, level) ? LEVEL_UNIT[level] : null;
  }

  /** 관측 신뢰도를 σ 하나로 접는다. 배제하지 않는 것이 요점. */
  function obsNoise(o) {
    o = o || {};
    var s = BASE_SIGMA[o.kind];
    if (s == null) s = BASE_SIGMA.cctv_uncalibrated;
    if (o.confidence === "low") s *= LOW_CONFIDENCE_MULT;
    var nf = (o.flags && o.flags.length) || 0;
    if (nf) s *= Math.pow(FLAG_MULT, nf);
    var age = o.ageMin;
    if (o.kind === "poi" && age != null && isFinite(age)) age = Math.max(0, age - POI_LAG_MIN);
    if (age != null && isFinite(age) && age > 0) s *= Math.sqrt(1 + Math.pow(age / AGE_HALF_MIN, 2));
    // 같은 관측을 n 개 지점에 복제해 넣을 때(구역 등급 → 관람구역 5곳) 정보량을 1건으로 유지
    if (o.dup && o.dup > 1) s *= Math.sqrt(o.dup);
    return s;
  }

  /** 관측 하나가 자기 위치의 사후에 기여하는 비율. 단일 관측 사후 축소 계수와 같다: k/(k+σ²).
   *  화면(타일·마커·배지)이 장과 같은 기준으로 "이 관측이 실제로 반영됐나" 를 말하게 하는 데 쓴다. */
  function infoWeight(sigma, kxx) {
    if (!(kxx > 0)) return 0;
    var s2 = sigma * sigma;
    return kxx / (kxx + s2);
  }

  // 사전 평균을 관측 수준에서 잡는다 (경험적 베이즈).
  //   왜: 고정 0.3 이면 주변이 다 붐벼도 사후가 "여유" 로 끌려간다. 미보정 카메라(σ=0.30)가 0.70 을 봐도
  //   사후는 0.3 + 0.735·(0.70−0.3) = 0.594 라 여유 밴드에 주저앉는다 — 화면의 마커(70)와 면(59)이 어긋난다.
  //   관측이 말하는 수준을 사전으로 삼으면 이 편향이 사라진다.
  //   단 관측 1건이 지도 전체를 정하면 안 되므로, 기본값을 PRIOR_PSEUDO 건만큼의 가짜 관측으로 섞는다.
  var PRIOR_PSEUDO = 3;

  function autoPrior(obs, kxx, fallback) {
    var sw = PRIOR_PSEUDO, sy = PRIOR_PSEUDO * fallback, i, w;
    for (i = 0; i < obs.length; i++) {
      w = infoWeight(obs[i].sigma, kxx);
      sw += w; sy += w * obs[i].y;
    }
    return sw > 0 ? sy / sw : fallback;
  }

  /** 하삼각 L (A = LLᵀ). PD 가 아니면 null. */
  function cholesky(A) {
    var n = A.length, L = [], i, j, k;
    for (i = 0; i < n; i++) { L.push(new Array(n)); for (j = 0; j < n; j++) L[i][j] = 0; }
    for (i = 0; i < n; i++) {
      for (j = 0; j <= i; j++) {
        var s = A[i][j];
        for (k = 0; k < j; k++) s -= L[i][k] * L[j][k];
        if (i === j) {
          if (!(s > 0)) return null;
          L[i][i] = Math.sqrt(s);
        } else {
          L[i][j] = s / L[j][j];
        }
      }
    }
    return L;
  }

  function forwardSolve(L, b) {           // L z = b
    var n = L.length, z = new Array(n), i, k;
    for (i = 0; i < n; i++) {
      var s = b[i];
      for (k = 0; k < i; k++) s -= L[i][k] * z[k];
      z[i] = s / L[i][i];
    }
    return z;
  }

  function backSolve(L, z) {              // Lᵀ x = z
    var n = L.length, x = new Array(n), i, k;
    for (i = n - 1; i >= 0; i--) {
      var s = z[i];
      for (k = i + 1; k < n; k++) s -= L[k][i] * x[k];
      x[i] = s / L[i][i];
    }
    return x;
  }

  function kernelPair(kern, r) {
    return kern.varShort * matern32(r, kern.lenShort) + kern.varLong * matern32(r, kern.lenLong);
  }

  /**
   * 관측 → 격자 위 사후 평균·표준편차.
   * opts.observations: [{x:[lng,lat], y, sigma}]
   * opts.grid: {x0,y0,dx,dy,cols,rows}  (x0,y0 = 격자 좌하단 모서리)
   * opts.prior: m₀ (구역 배경 등급)
   * opts.kernel: {varShort,lenShort,varLong,lenLong}
   */
  function buildField(opts) {
    var obs = opts.observations || [], g = opts.grid, kern = opts.kernel;
    var n = obs.length, cells = g.cols * g.rows;
    var kxx = kern.varShort + kern.varLong;
    // prior 를 주지 않으면 관측 수준에서 잡는다 (fallbackPrior 는 관측이 없거나 적을 때의 기준)
    var prior = opts.prior == null
      ? autoPrior(obs, kxx, opts.fallbackPrior == null ? 0.3 : opts.fallbackPrior)
      : opts.prior;
    var mean = new Float64Array(cells), sd = new Float64Array(cells);
    var i, j, c, ix, iy;

    if (!n) {                                   // 관측 0 → 전부 사전, 불확실성 최대
      var full = Math.sqrt(kxx);
      for (i = 0; i < cells; i++) { mean[i] = prior; sd[i] = full; }
      return { mean: mean, sd: sd, cols: g.cols, rows: g.rows, n: 0, ok: true, jitter: 0 };
    }

    var A = [];
    for (i = 0; i < n; i++) {
      A.push(new Array(n));
      for (j = 0; j < n; j++) A[i][j] = kernelPair(kern, distanceM(obs[i].x, obs[j].x));
      A[i][i] += obs[i].sigma * obs[i].sigma;
    }
    // 같은 지점 관측이 겹치면 수치적으로 특이해질 수 있다 → jitter 를 키우며 재시도
    var L = null, jitter = 0;
    for (var attempt = 0; attempt < 6 && !L; attempt++) {
      if (attempt) {
        var add = 1e-10 * Math.pow(100, attempt - 1) * kxx;
        for (i = 0; i < n; i++) A[i][i] += add - jitter;
        jitter = add;
      }
      L = cholesky(A);
    }
    if (!L) {                                   // 끝내 못 풀면 사전으로 물러난다 (거짓 확신보다 낫다)
      var f2 = Math.sqrt(kxx);
      for (i = 0; i < cells; i++) { mean[i] = prior; sd[i] = f2; }
      return { mean: mean, sd: sd, cols: g.cols, rows: g.rows, n: n, ok: false, jitter: jitter };
    }

    var resid = new Array(n);
    for (i = 0; i < n; i++) resid[i] = obs[i].y - prior;
    var alpha = backSolve(L, forwardSolve(L, resid));

    var kx = new Array(n);
    for (iy = 0; iy < g.rows; iy++) {
      for (ix = 0; ix < g.cols; ix++) {
        var p = [g.x0 + (ix + 0.5) * g.dx, g.y0 + (iy + 0.5) * g.dy];
        var m = prior;
        for (i = 0; i < n; i++) { kx[i] = kernelPair(kern, distanceM(p, obs[i].x)); m += kx[i] * alpha[i]; }
        var v = forwardSolve(L, kx), q = 0;
        for (i = 0; i < n; i++) q += v[i] * v[i];
        c = iy * g.cols + ix;
        mean[c] = m;
        sd[c] = Math.sqrt(Math.max(0, kxx - q));
      }
    }
    return { mean: mean, sd: sd, cols: g.cols, rows: g.rows, n: n, ok: true, jitter: jitter };
  }

  return {
    matern32: matern32,
    distanceM: distanceM,
    cholesky: cholesky,
    forwardSolve: forwardSolve,
    backSolve: backSolve,
    obsNoise: obsNoise,
    infoWeight: infoWeight,
    autoPrior: autoPrior,
    PRIOR_PSEUDO: PRIOR_PSEUDO,
    gradeToUnit: gradeToUnit,
    walkSpeed: walkSpeed,
    unitToDensity: unitToDensity,
    walkSeconds: walkSeconds,
    confidence: confidence,
    blendDensity: blendDensity,
    blendSeconds: blendSeconds,
    STREET_RHO: STREET_RHO,
    POI_LAG_MIN: POI_LAG_MIN,
    PACE_GAIN: PACE_GAIN,
    V_FREE: V_FREE,
    V_MIN: V_MIN,
    densityToUnit: densityToUnit,
    unitToGrade: unitToGrade,
    levelToUnit: levelToUnit,
    LEVEL_UNIT: LEVEL_UNIT,
    buildField: buildField,
    GRADES: GRADES,
    DENSITY_SEVERE: DENSITY_SEVERE,
    BASE_SIGMA: BASE_SIGMA,
  };
});
