// Estúdio de Projeto — geometria pura do editor 2D (sem React): encaixe do cursor, projeção em paredes, edição do modelo.
// O modelo é o mesmo que o servidor valida e do qual deriva o 3D, os alçados, os cortes e as medições.

export const PASSO = 0.05;      // grelha de 5 cm
export const ENCAIXE = 0.3;     // distância (m) para colar a uma ponta ou a um eixo
export const ORTO_GRAUS = 7;    // abaixo deste desvio o troço fica horizontal / vertical

export const arred = (v, p = PASSO) => Math.round(v / p) * p;
export const r3 = (v) => Math.round(v * 1000) / 1000;
export const fmt = (v, d = 2) => Number(v || 0).toFixed(d).replace(".", ",");

export function espessuraTipo(tipo) {
  return (tipo?.camadas || []).reduce((s, c) => s + Number(c.esp_m || 0), 0);
}

export function geoParede(w) {
  const dx = w.b[0] - w.a[0], dy = w.b[1] - w.a[1];
  const L = Math.hypot(dx, dy);
  const u = L > 1e-9 ? [dx / L, dy / L] : [1, 0];
  return { L, u, n: [-u[1], u[0]] };
}

// Projeção de um ponto no eixo de uma parede: distância ao longo do eixo (limitada à parede) e afastamento.
export function projetar(w, p) {
  const { L, u } = geoParede(w);
  const s = (p[0] - w.a[0]) * u[0] + (p[1] - w.a[1]) * u[1];
  const sc = Math.max(0, Math.min(L, s));
  const q = [w.a[0] + u[0] * sc, w.a[1] + u[1] * sc];
  return { s: sc, ponto: q, dist: Math.hypot(p[0] - q[0], p[1] - q[1]), L };
}

export function paredeMaisProxima(paredes, p, max = 0.6) {
  let melhor = null;
  for (const w of paredes) {
    const pr = projetar(w, p);
    if (pr.dist <= max && (!melhor || pr.dist < melhor.dist)) melhor = { ...pr, parede: w };
  }
  return melhor;
}

// Encaixe do cursor: pontas de paredes → eixos de paredes → ortogonal em relação ao ponto de partida → grelha.
export function encaixar(p, paredes, origem = null, ignorar = null) {
  let melhor = null;
  for (const w of paredes) {
    if (w.id === ignorar) continue;
    for (const q of [w.a, w.b]) {
      const d = Math.hypot(p[0] - q[0], p[1] - q[1]);
      if (d <= ENCAIXE && (!melhor || d < melhor.d)) melhor = { d, ponto: [q[0], q[1]], tipo: "ponta" };
    }
  }
  if (melhor) return melhor;
  let q = [p[0], p[1]];
  let orto = false;
  if (origem) {
    const dx = q[0] - origem[0], dy = q[1] - origem[1];
    const ang = (Math.atan2(Math.abs(dy), Math.abs(dx)) * 180) / Math.PI;
    if (ang < ORTO_GRAUS) { q = [q[0], origem[1]]; orto = true; }
    else if (ang > 90 - ORTO_GRAUS) { q = [origem[0], q[1]]; orto = true; }
  }
  const eixo = paredeMaisProxima(paredes.filter((w) => w.id !== ignorar), q, ENCAIXE * 0.7);
  if (eixo) {
    // mantém a ortogonalidade quando possível: cruza a linha ortogonal com o eixo encontrado
    if (orto && origem) {
      const { u } = geoParede(eixo.parede);
      const horizontal = Math.abs(q[1] - origem[1]) < 1e-9;
      const den = horizontal ? u[1] : u[0];
      if (Math.abs(den) > 1e-6) {
        const t = horizontal ? (origem[1] - eixo.parede.a[1]) / u[1] : (origem[0] - eixo.parede.a[0]) / u[0];
        if (t >= -1e-6 && t <= eixo.L + 1e-6) {
          return { d: eixo.dist, ponto: [r3(eixo.parede.a[0] + u[0] * t), r3(eixo.parede.a[1] + u[1] * t)], tipo: "eixo" };
        }
      }
    }
    return { d: eixo.dist, ponto: [r3(eixo.ponto[0]), r3(eixo.ponto[1])], tipo: "eixo" };
  }
  return { d: 0, ponto: [r3(arred(q[0])), r3(arred(q[1]))], tipo: orto ? "orto" : "grelha" };
}

export function novoId(prefixo, existentes) {
  const usados = new Set(existentes.map((x) => x.id));
  let n = existentes.length + 1;
  while (usados.has(`${prefixo}${n}`)) n += 1;
  return `${prefixo}${n}`;
}

// Posição de um vão novo numa parede: centro pedido, limitado para caber com 5 cm de folga e sem pisar outros vãos.
export function posicaoVao(modelo, parede, s, largura, ignorarId = null) {
  const { L } = geoParede(parede);
  const meio = largura / 2 + 0.05;
  if (L < 2 * meio) return null;
  let pos = Math.max(meio, Math.min(L - meio, arred(s)));
  const outros = modelo.vaos.filter((v) => v.parede === parede.id && v.id !== ignorarId);
  const colide = (x) => outros.some((v) => Math.abs(v.pos_m - x) < (v.largura_m + largura) / 2 + 0.02);
  if (!colide(pos)) return r3(pos);
  for (let k = 1; k < 400; k += 1) {
    for (const x of [pos + k * PASSO, pos - k * PASSO]) {
      if (x >= meio - 1e-9 && x <= L - meio + 1e-9 && !colide(x)) return r3(x);
    }
  }
  return null;
}

export function adicionarParede(modelo, piso, a, b, tipo) {
  if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 0.1) return modelo;
  const id = novoId("w", modelo.paredes);
  return { ...modelo, paredes: [...modelo.paredes, { id, piso, a: [r3(a[0]), r3(a[1])], b: [r3(b[0]), r3(b[1])], tipo }] };
}

export function removerParede(modelo, id) {
  return { ...modelo, paredes: modelo.paredes.filter((w) => w.id !== id), vaos: modelo.vaos.filter((v) => v.parede !== id) };
}

export function mudarParede(modelo, id, patch) {
  return { ...modelo, paredes: modelo.paredes.map((w) => (w.id === id ? { ...w, ...patch } : w)) };
}

// Altera o comprimento mantendo o ponto «a» e a direção.
export function comprimentoParede(modelo, id, L) {
  const w = modelo.paredes.find((x) => x.id === id);
  if (!w || !(L >= 0.1)) return modelo;
  const { u } = geoParede(w);
  return mudarParede(modelo, id, { b: [r3(w.a[0] + u[0] * L), r3(w.a[1] + u[1] * L)] });
}

export function adicionarVao(modelo, parede, s, tipo, base) {
  const pos = posicaoVao(modelo, parede, s, base.largura_m);
  if (pos == null) return null;
  const id = novoId("v", modelo.vaos);
  return { modelo: { ...modelo, vaos: [...modelo.vaos, { id, parede: parede.id, tipo, pos_m: pos, ...base, lado: 1, dobradica: "a" }] }, id };
}

export function mudarVao(modelo, id, patch) {
  return { ...modelo, vaos: modelo.vaos.map((v) => (v.id === id ? { ...v, ...patch } : v)) };
}

export function removerVao(modelo, id) {
  return { ...modelo, vaos: modelo.vaos.filter((v) => v.id !== id) };
}

// Novo piso por cima do último: copia as paredes (e os vãos de janela) do piso de baixo, que é o ponto de partida habitual.
export function adicionarPiso(modelo) {
  const n = modelo.pisos.length;
  if (n >= 6) return modelo;
  const base = modelo.pisos[n - 1];
  const id = `p${n}${modelo.pisos.some((p) => p.id === `p${n}`) ? "b" : ""}`;
  const mapa = {};
  const paredes = modelo.paredes.filter((w) => w.piso === base.id).map((w, i) => {
    const nid = `${id}_w${i + 1}`;
    mapa[w.id] = nid;
    return { ...w, id: nid, piso: id };
  });
  const vaos = modelo.vaos.filter((v) => mapa[v.parede] && v.tipo === "janela").map((v, i) => ({ ...v, id: `${id}_v${i + 1}`, parede: mapa[v.parede] }));
  return {
    ...modelo,
    pisos: [...modelo.pisos, { id, nome: `${n}.º andar`, pe_direito_m: base.pe_direito_m, laje_m: base.laje_m }],
    paredes: [...modelo.paredes, ...paredes],
    vaos: [...modelo.vaos, ...vaos],
  };
}

export function removerUltimoPiso(modelo) {
  if (modelo.pisos.length <= 1) return modelo;
  const id = modelo.pisos[modelo.pisos.length - 1].id;
  const ids = new Set(modelo.paredes.filter((w) => w.piso === id).map((w) => w.id));
  return {
    ...modelo,
    pisos: modelo.pisos.slice(0, -1),
    paredes: modelo.paredes.filter((w) => w.piso !== id),
    vaos: modelo.vaos.filter((v) => !ids.has(v.parede)),
    rotulos: (modelo.rotulos || []).filter((r) => r.piso !== id),
  };
}

export function limitesModelo(modelo, piso) {
  const ws = modelo.paredes.filter((w) => !piso || w.piso === piso);
  const todas = ws.length ? ws : modelo.paredes;
  if (!todas.length) return [-2, -2, 14, 10];
  const xs = todas.flatMap((w) => [w.a[0], w.b[0]]), ys = todas.flatMap((w) => [w.a[1], w.b[1]]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---------------------------------------------------------------- divisões (nome e acabamentos próprios)
export function dentroPoligono(p, pts) {
  let dentro = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i, i += 1) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > p[1]) !== (yj > p[1]) && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

// Índice do rótulo que está dentro da divisão (o rótulo guarda o nome e os acabamentos próprios dela), ou −1.
export function rotuloDaDivisao(modelo, piso, pts) {
  return (modelo.rotulos || []).findIndex((r) => r.piso === piso && dentroPoligono([r.x, r.y], pts));
}

// Altera o nome ou um acabamento de uma divisão. Valor vazio num acabamento = voltar ao acabamento da casa.
export function definirDivisao(modelo, piso, divisao, patch) {
  const rot = [...(modelo.rotulos || [])];
  let i = rotuloDaDivisao(modelo, piso, divisao.pts);
  if (i < 0) {
    rot.push({ piso, x: divisao.centro[0], y: divisao.centro[1], nome: divisao.nome });
    i = rot.length - 1;
  }
  const r = { ...rot[i] };
  for (const [k, v] of Object.entries(patch)) {
    if (k === "nome") { if (String(v || "").trim()) r.nome = String(v).slice(0, 40); }
    else if (v === "" || v == null) delete r[k];
    else r[k] = v;
  }
  rot[i] = r;
  return { ...modelo, rotulos: rot };
}
