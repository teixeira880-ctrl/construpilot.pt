/**
 * ETRS89 / PT-TM06 (EPSG:3763) → ETRS89 (lat, lon em graus). Mesmos parâmetros do motor do servidor
 * (backend/engines/mdt_pt/pttm06.py): GRS80, φ0 = 39°40'05,73'' N, λ0 = 8°07'59,19'' W, k0 = 1, FE = FN = 0.
 * Séries de Krüger (ordem 4): erro inferior a 1 mm em Portugal continental.
 */
const A = 6378137.0;
const F = 1 / 298.257222101;
const LAT0 = 39 + 40 / 60 + 5.73 / 3600;
const LON0 = -(8 + 7 / 60 + 59.19 / 3600);
const n = F / (2 - F);
const n2 = n * n, n3 = n2 * n, n4 = n3 * n;
const AA = (A / (1 + n)) * (1 + n2 / 4 + n4 / 64);
const ALFA = [
  n / 2 - (2 * n2) / 3 + (5 * n3) / 16 + (41 * n4) / 180,
  (13 * n2) / 48 - (3 * n3) / 5 + (557 * n4) / 1440,
  (61 * n3) / 240 - (103 * n4) / 140,
  (49561 * n4) / 161280,
];
const BETA = [
  n / 2 - (2 * n2) / 3 + (37 * n3) / 96 - n4 / 360,
  n2 / 48 + n3 / 15 - (437 * n4) / 1440,
  (17 * n3) / 480 - (37 * n4) / 840,
  (4397 * n4) / 161280,
];
const E = Math.sqrt(F * (2 - F));

// norte da origem (ξ0·A): latitude da origem projetada sobre o meridiano central
const XI0 = (() => {
  const phi = (LAT0 * Math.PI) / 180;
  const t = Math.sinh(Math.atanh(Math.sin(phi)) - E * Math.atanh(E * Math.sin(phi)));
  const xi1 = Math.atan2(t, 1);
  return ALFA.reduce((s, a, j) => s + a * Math.sin(2 * (j + 1) * xi1), xi1);
})();

/** (M = este, P = norte) em metros PT-TM06 → [lat, lon] em graus. */
export function tm06ParaLatLon(M, P) {
  const xi = XI0 + P / AA;
  const eta = M / AA;
  let xi1 = xi, eta1 = eta;
  BETA.forEach((b, j) => {
    const k = 2 * (j + 1);
    xi1 -= b * Math.sin(k * xi) * Math.cosh(k * eta);
    eta1 -= b * Math.cos(k * xi) * Math.sinh(k * eta);
  });
  const chi = Math.asin(Math.sin(xi1) / Math.cosh(eta1));
  // latitude conforme → geodésica (iteração de ponto fixo; converge em 3–4 passos)
  let phi = chi;
  for (let i = 0; i < 8; i += 1) {
    phi = Math.asin(Math.tanh(Math.atanh(Math.sin(chi)) + E * Math.atanh(E * Math.sin(phi))));
  }
  const lam = Math.atan2(Math.sinh(eta1), Math.cos(xi1));
  return [(phi * 180) / Math.PI, LON0 + (lam * 180) / Math.PI];
}
