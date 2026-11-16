"""Leitura geométrica de uma folha de plantas estruturais (PDF vetorial).

Método (o mesmo que um medidor segue à mão, tornado determinístico) :
 1. escala lida no texto («Esc: 1/100») ou dada pelo utilizador ;
 2. os traços interrompidos são reconstituídos ; os que atravessam a planta e saem para lá das peças são ALINHAMENTOS (eixos)
    e delimitam cada planta da folha ; os restantes traços interrompidos são faces de vigas ;
 3. as tramas cheias a escuro são as secções cortadas (pilares, paredes, núcleos) : área, lados e perímetro medidos ;
    cada secção recebe a etiqueta mais próxima (P…, Par…, Nb…) ;
 4. os traços dividem a planta em faces fechadas : a laje é a reunião das faces que tocam peças estruturais ou que são
    moldes de aligeiramento ; as faces fechadas só por paredes de núcleo são aberturas (escadas, elevador) ;
 5. os moldes de aligeiramento são as faces quadradas repetidas com o mesmo módulo : contam-se uma a uma ;
 6. as vigas são as faces estreitas e compridas junto de uma etiqueta V… : largura e vão livre medidos ;
 7. as caixas de nível («Piso 1 / Zsup / Zinf / e=») dão as cotas e a espessura de cada laje.
Tudo o que não está no desenho é devolvido como pressuposto ou pergunta, nunca inventado."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import cv2
import numpy as np

from .vetores import Folha

PX = 0.01                      # resolução de medição : 1 px = 1 cm real
TRACO_MAX_PT = 12.0            # comprimento máximo (pt papel) de um traço de linha interrompida
FOLGA_PT = 7.0                 # intervalo máximo entre traços da mesma linha interrompida
RE_ESC = re.compile(r"esc(?:ala)?\.?\s*:?\s*1\s*[/:]\s*(\d{2,4})", re.I)
RE_ESC_SEM_BARRA = re.compile(r"esc(?:ala)?\.?\s*:\s*1(\d{2,3})\b", re.I)
RE_PILAR = re.compile(r"^P\d+[A-Za-z]?$")
RE_PAREDE = re.compile(r"^(?:Par|PAR|Pa|PA|PB|M|Mc|MC|W)\d+[A-Za-z]?$")
RE_NUCLEO = re.compile(r"^(?:Nb|NB|Nu|NU|Nuc|NUC|N|CE|CX)\d+[A-Za-z]?$")
RE_VIGA = re.compile(r"^(V[A-Za-z]?\d+(?:\.\d+)?)(?:\((\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\))?$")
RE_SEC = re.compile(r"^\((\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\)$")
RE_EIXO = re.compile(r"^(?:[A-Z]'?|\d{1,2}'?|[A-Z]\d)$")
RE_NUM = r"(-?\d+(?:[.,]\d+)?)"


def _num(s) -> float:
    return float(str(s).replace(",", "."))


def ler_escala(folha: Folha):
    """Denominador da escala (100 para 1/100) e se foi lido sem ambiguidade."""
    vals = [int(m) for m in RE_ESC.findall(folha.texto)] + [int(m) for p in folha.palavras for m in RE_ESC.findall(p[4])]
    if not vals:                                   # alguns extratores perdem a barra : «Esc:1100» = 1/100
        vals = [int(m) for p in folha.palavras for m in RE_ESC_SEM_BARRA.findall(p[4]) if int(m) in (20, 25, 50, 75, 100, 200, 250, 500)]
    if not vals:
        return None, False
    c = Counter(vals)
    return c.most_common(1)[0][0], len(c) == 1


def _texto(p: str) -> str:
    """Palavra normalizada : o texto vertical chega invertido de alguns extratores (marcado ↻)."""
    if not p.startswith("↻"):
        return p
    t = p[1:]
    for cand in (t[::-1], t):
        if RE_PILAR.match(cand) or RE_PAREDE.match(cand) or RE_NUCLEO.match(cand) or RE_VIGA.match(cand) or RE_SEC.match(cand):
            return cand
    return t


# ───────────────────────── traços interrompidos e alinhamentos ─────────────────────────

def _traco_tipo(comp: np.ndarray) -> float:
    """Comprimento máximo (pt) de um traço de linha interrompida nesta folha : 2,5 × o maior comprimento dominante entre os
    segmentos curtos (os traços e pontos repetem-se aos milhares ; os lados curtos de contornos não)."""
    curtos = comp[(comp > 0.3) & (comp <= TRACO_MAX_PT)]
    if len(curtos) < 50:
        return TRACO_MAX_PT
    c = Counter(np.round(curtos * 5).astype(int).tolist())             # classes de 0,2 pt
    dominantes = [kk / 5 for kk, n in c.items() if n >= 0.08 * len(curtos)]
    return min(TRACO_MAX_PT, max(3.0, 2.5 * max(dominantes))) if dominantes else TRACO_MAX_PT


def _linhas(segs: np.ndarray, lum: np.ndarray | None = None, trac: np.ndarray | None = None):
    """Separa os segmentos em : contínuos (N×4) e linhas interrompidas ortogonais reconstituídas [(orient, c, a, b, cor)].
    Linhas colineares de cores diferentes (eixo a cinzento sobre a face de uma viga a preto) ficam separadas."""
    cor = np.round((lum if lum is not None and len(lum) == len(segs) else np.zeros(len(segs))) * 4).astype(np.int64)
    dx, dy = np.abs(segs[:, 2] - segs[:, 0]), np.abs(segs[:, 3] - segs[:, 1])
    comp = np.hypot(dx, dy)
    hor, ver = (dy < 0.3) & (dx > 0.05), (dx < 0.3) & (dy > 0.05)
    tmax = _traco_tipo(comp[hor | ver])
    interrompidas, usados = [], np.zeros(len(segs), dtype=bool)
    if trac is not None and len(trac) == len(segs) and trac.any():   # PDF que guarda o padrão de interrompido no próprio traço
        for n in np.nonzero(trac & (hor | ver))[0]:
            x0, y0, x1, y1 = segs[n]
            interrompidas.append(("h", float((y0 + y1) / 2), float(min(x0, x1)), float(max(x0, x1)), int(cor[n])) if hor[n] else
                                 ("v", float((x0 + x1) / 2), float(min(y0, y1)), float(max(y0, y1)), int(cor[n])))
        usados |= trac
    for orient, mask in (("h", hor), ("v", ver)):
        idx = np.nonzero(mask & (comp <= tmax) & ~usados)[0]
        if not len(idx):
            continue
        s = segs[idx]
        c = (s[:, 1] + s[:, 3]) / 2 if orient == "h" else (s[:, 0] + s[:, 2]) / 2
        a = np.minimum(s[:, 0], s[:, 2]) if orient == "h" else np.minimum(s[:, 1], s[:, 3])
        b = np.maximum(s[:, 0], s[:, 2]) if orient == "h" else np.maximum(s[:, 1], s[:, 3])
        chave = np.round(c / 0.4).astype(np.int64) * 8 + cor[idx]
        ordem = np.lexsort((a, chave))
        i = 0
        while i < len(ordem):
            j, fim, grupo = i, b[ordem[i]], [ordem[i]]
            while j + 1 < len(ordem) and chave[ordem[j + 1]] == chave[ordem[i]] and a[ordem[j + 1]] - fim <= FOLGA_PT:
                j += 1
                fim = max(fim, b[ordem[j]])
                grupo.append(ordem[j])
            if len(grupo) >= 4:
                interrompidas.append((orient, float(np.mean(c[grupo])), float(a[ordem[i]]), float(fim), int(cor[idx[ordem[i]]])))
                usados[idx[grupo]] = True
            i = j + 1
    return segs[~usados], interrompidas


def _plantas(interrompidas, k: float, largura: float, altura: float):
    """Agrupa os alinhamentos que se cruzam : cada grupo (≥ 2 verticais e ≥ 2 horizontais) é uma planta. Devolve as caixas (pt)."""
    cand = [l for l in interrompidas if (l[3] - l[2]) * k >= 6.0]
    n = len(cand)
    pai = list(range(n))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i
    V = [i for i in range(n) if cand[i][0] == "v"]
    H = [i for i in range(n) if cand[i][0] == "h"]
    for i in V:
        _, x, y0, y1, _ = cand[i]
        for j in H:
            _, y, x0, x1, _ = cand[j]
            if x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1:
                pai[raiz(i)] = raiz(j)
    grupos = defaultdict(list)
    for i in range(n):
        grupos[raiz(i)].append(i)
    caixas = []
    for g in grupos.values():
        vs, hs = [cand[i] for i in g if cand[i][0] == "v"], [cand[i] for i in g if cand[i][0] == "h"]
        if len(vs) < 2 or len(hs) < 2:
            continue
        x0 = min(min(l[2] for l in hs), min(l[1] for l in vs))
        x1 = max(max(l[3] for l in hs), max(l[1] for l in vs))
        y0 = min(min(l[2] for l in vs), min(l[1] for l in hs))
        y1 = max(max(l[3] for l in vs), max(l[1] for l in hs))
        caixas.append((max(0, x0), max(0, y0), min(largura, x1), min(altura, y1)))
    caixas.sort(key=lambda c: (round(c[1] / 200), c[0]))
    return caixas


# ───────────────────────── caixas de nível ─────────────────────────

def _seguidas(ln, x0, folga=14.0):
    """Palavras de uma linha a partir de x0, enquanto estiverem juntas (pára no intervalo para a caixa vizinha)."""
    ws = sorted(w for w in ln if w[0] >= x0 - 6)
    out = []
    for w in ws:
        if out and w[0] - out[-1][2] > folga:
            break
        if not out and w[0] > x0 + 40:
            break
        out.append(w)
    return " ".join(w[4] for w in out).strip()


def _niveis(palavras, k: float):
    """Caixas «Piso n / Zsup: … m / Zinf: … m / e=… m». Devolve [{nome, zsup, zinf, e}] por ordem de leitura."""
    linhas = defaultdict(list)
    for x0, y0, x1, y1, t in palavras:
        linhas[round((y0 + y1) / 2 / 3)].append((x0, y0, x1, y1, t))
    ordenadas = [sorted(v) for _, v in sorted(linhas.items())]
    txt = [(min(w[0] for w in ln), sum((w[1] + w[3]) / 2 for w in ln) / len(ln), " ".join(w[4] for w in ln), ln) for ln in ordenadas]
    out = []
    for x0, y0, x1, y1, t in palavras:
        if not re.match(r"^Zsup", t, re.I):
            continue
        mesma = [ln for ln in txt if abs(ln[1] - (y0 + y1) / 2) < 3]
        seg = " ".join(_seguidas(ln[3], x0) for ln in mesma)
        m = re.search(r"Zsup\s*:?\s*" + RE_NUM, seg, re.I)
        if not m:
            continue
        niv = {"zsup": _num(m.group(1)), "zinf": None, "e": None, "nome": None}
        abaixo = sorted([ln for ln in txt if 3 <= ln[1] - (y0 + y1) / 2 < 34], key=lambda ln: ln[1])
        for ln in abaixo:
            s = _seguidas(ln[3], x0)
            mz = re.search(r"Zinf\s*:?\s*" + RE_NUM, s, re.I)
            me = re.search(r"\be\s*=\s*" + RE_NUM, s, re.I)
            if mz and niv["zinf"] is None:
                niv["zinf"] = _num(mz.group(1))
            if me and niv["e"] is None:
                niv["e"] = _num(me.group(1))
        acima = sorted([ln for ln in txt if 3 <= (y0 + y1) / 2 - ln[1] < 16], key=lambda ln: -ln[1])
        for ln in acima:
            s = _seguidas(ln[3], x0)
            if s and not re.match(r"^(Zsup|Zinf|e\s*=)", s, re.I):
                niv["nome"] = s
                break
        niv["_xy"] = (x0, y0)
        out.append(niv)
    return out


# ───────────────────────── medição de uma planta ─────────────────────────

K3, K5 = np.ones((3, 3), np.uint8), np.ones((5, 5), np.uint8)


def _lado(v):
    return round(v + 1e-9, 2)


def _medidas(mask):
    """Área, perímetro (px) e lados do retângulo de área mínima de uma máscara, pelos contornos (exato para peças ortogonais)."""
    cs, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    area = per = 0.0
    ext = []
    for c, h in zip(cs, hier[0]):
        a = cv2.contourArea(c)
        if h[3] < 0:
            area += a
            ext.append(c)
        else:
            area -= a
        per += cv2.arcLength(c, True)
    (_, _), (w, h), _ = cv2.minAreaRect(np.vstack(ext))
    return area, per, max(w, h), min(w, h)


def _dist_caixa(x, y, c):
    return math.hypot(max(c[0] - x, 0, x - c[2]), max(c[1] - y, 0, y - c[3]))


def _faixas_viga(tracejadas, solidos, k):
    """Faixas de viga : pares de linhas paralelas VIZINHAS (duas interrompidas, ou uma interrompida e o bordo contínuo da laje)
    afastadas 0,15–0,75 m. Uma linha comprida pode formar faixa com vários troços (viga interrompida nos pilares)."""
    lo, hi = 0.15 / k, 0.75 / k
    tr = [l for l in tracejadas if (l[3] - l[2]) * k >= 0.8]
    centrais = set()                                       # linha a meio de duas faces paralelas = eixo da viga, não é face
    for n, r in enumerate(tr):
        esq = [p for p in tr if p[0] == r[0] and lo / 2 <= r[1] - p[1] <= hi / 2 and (min(p[3], r[3]) - max(p[2], r[2])) * k >= 0.5]
        dir_ = [p for p in tr if p[0] == r[0] and lo / 2 <= p[1] - r[1] <= hi / 2 and (min(p[3], r[3]) - max(p[2], r[2])) * k >= 0.5]
        if any(abs((r[1] - p[1]) - (q[1] - r[1])) * k <= 0.03 for p in esq for q in dir_):
            centrais.add(n)
    tr = [l for n, l in enumerate(tr) if n not in centrais]

    def sobrep(p, q):
        return max(p[2], q[2]), min(p[3], q[3])
    faixas, com_par = [], set()
    for i, p in enumerate(tr):
        for j in range(i + 1, len(tr)):
            q = tr[j]
            if p[0] != q[0] or not (lo <= abs(p[1] - q[1]) <= hi):
                continue
            a, b = sobrep(p, q)
            if (b - a) * k < 0.5:
                continue
            c1, c2 = min(p[1], q[1]), max(p[1], q[1])
            if any(r[0] == p[0] and c1 + 0.5 < r[1] < c2 - 0.5 and (min(r[3], b) - max(r[2], a)) * k >= 0.3 for r in tr):
                continue                                   # há outra linha entre as duas : não são faces da mesma viga
            faixas.append((p[0], c1, c2, a, b))
            com_par |= {i, j}
    if len(solidos):
        dx, dy = np.abs(solidos[:, 2] - solidos[:, 0]), np.abs(solidos[:, 3] - solidos[:, 1])
        sh = solidos[(dy < 0.3) & (dx * k >= 1.0)]
        sv = solidos[(dx < 0.3) & (dy * k >= 1.0)]
        for i, p in enumerate(tr):
            s = sh if p[0] == "h" else sv
            if not len(s):
                continue
            c = (s[:, 1] + s[:, 3]) / 2 if p[0] == "h" else (s[:, 0] + s[:, 2]) / 2
            a = np.minimum(s[:, 0], s[:, 2]) if p[0] == "h" else np.minimum(s[:, 1], s[:, 3])
            b = np.maximum(s[:, 0], s[:, 2]) if p[0] == "h" else np.maximum(s[:, 1], s[:, 3])
            d = np.abs(c - p[1])
            ok = (d >= lo) & (d <= hi) & ((np.minimum(b, p[3]) - np.maximum(a, p[2])) * k >= 0.5)
            if ok.any():
                dmin = d[ok].min()
                if i in com_par and dmin > min(q[2] - q[1] for q in faixas if q[0] == p[0] and (abs(q[1] - p[1]) < 0.5 or abs(q[2] - p[1]) < 0.5)) + 0.5:
                    continue                               # o bordo contínuo está mais longe do que a outra face : não é desta viga
                m = int(np.argmin(np.where(ok, d, 1e9)))
                col = np.abs(c - c[m]) <= 0.5                # troços colineares do mesmo bordo (interrompido por contornos de peças)
                faixas.append((p[0], min(p[1], c[m]), max(p[1], c[m]), max(p[2], a[col].min()), min(p[3], b[col].max())))
    return faixas


def _fundir_vaos(vaos, px):
    """Funde vãos repetidos e os que se tocam topo a topo na mesma faixa (a mesma viga medida por dois pares de linhas)."""
    out = []
    for v in sorted(vaos, key=lambda q: q["caixa"]):
        x0, y0, x1, y1 = v["caixa"]
        vert = (y1 - y0) > (x1 - x0)
        for o in out:
            a0, b0, a1, b1 = o["caixa"]
            if vert != ((b1 - b0) > (a1 - a0)):
                continue
            if vert and abs(a0 - x0) <= 2 and abs(a1 - x1) <= 2 and y0 <= b1 + 2 and y1 >= b0 - 2:
                o["caixa"] = (a0, min(b0, y0), a1, max(b1, y1))
                o["L"] = round((o["caixa"][3] - o["caixa"][1]) * px, 2)
                break
            if not vert and abs(b0 - y0) <= 2 and abs(b1 - y1) <= 2 and x0 <= a1 + 2 and x1 >= a0 - 2:
                o["caixa"] = (min(a0, x0), b0, max(a1, x1), b1)
                o["L"] = round((o["caixa"][2] - o["caixa"][0]) * px, 2)
                break
        else:
            out.append(dict(v))
    return out


def _atribuir(custos, limite):
    """Atribuição ótima etiqueta → vão (soma mínima das distâncias), só dentro do limite. Devolve [(i, j)]."""
    if not custos or not custos[0]:
        return []
    C = np.array(custos, dtype=np.float64)
    try:
        from scipy.optimize import linear_sum_assignment
        li, co = linear_sum_assignment(np.where(C <= limite, C, limite * 50))
        return [(int(i), int(j)) for i, j in zip(li, co) if C[i, j] <= limite]
    except ImportError:
        pares, ui, uj = [], set(), set()
        for d, i, j in sorted((C[i, j], i, j) for i in range(C.shape[0]) for j in range(C.shape[1]) if C[i, j] <= limite):
            if i not in ui and j not in uj:
                ui.add(i)
                uj.add(j)
                pares.append((i, j))
        return pares


def medir_planta(folha: Folha, solidos: np.ndarray, interrompidas, caixa, k: float) -> dict:
    """Mede uma planta delimitada por `caixa` (pt). k = metros reais por ponto PDF."""
    px = PX if max(caixa[2] - caixa[0], caixa[3] - caixa[1]) * k <= 70 else 2 * PX
    f = k / px                                             # px por pt
    mg = 0.5 / k
    X0, Y0, X1, Y1 = caixa[0] - mg, caixa[1] - mg, caixa[2] + mg, caixa[3] + mg
    W, H = int((X1 - X0) * f) + 3, int((Y1 - Y0) * f) + 3
    m2 = px * px

    def T(pts):
        return np.round((np.asarray(pts, dtype=np.float64).reshape(-1, 2) - (X0, Y0)) * f).astype(np.int32)

    def dentro(xa, ya, xb, yb):
        return max(xa, xb) >= X0 and min(xa, xb) <= X1 and max(ya, yb) >= Y0 and min(ya, yb) <= Y1

    # 1. secções cortadas (tramas cheias a escuro)
    cheio = np.zeros((H, W), np.uint8)
    pols = []
    for pol in folha.cheios:
        if pol[:, 0].max() >= X0 and pol[:, 0].min() <= X1 and pol[:, 1].max() >= Y0 and pol[:, 1].min() <= Y1:
            cv2.fillPoly(cheio, [T(pol)], 1)
            pols.append(pol)
    cheio = cv2.morphologyEx(cheio, cv2.MORPH_CLOSE, K3)
    n_el, el_lab, el_st, _ = cv2.connectedComponentsWithStats(cheio, 8)
    for i in range(1, n_el):                               # tramas minúsculas : setas, texto, símbolos
        if el_st[i][4] * m2 < 0.03 or min(el_st[i][2], el_st[i][3]) * px < 0.10:
            cheio[el_lab == i] = 0
    n_el, el_lab, el_st, _ = cv2.connectedComponentsWithStats(cheio, 8)

    exato = {}                                              # caixa vetorial exata (pt) de cada secção : lados sem erro de píxel
    for pol in pols:
        c = T(pol.mean(axis=0))[0]
        i = int(el_lab[min(max(c[1], 0), H - 1), min(max(c[0], 0), W - 1)])
        if i:
            q = exato.get(i)
            b4 = (pol[:, 0].min(), pol[:, 1].min(), pol[:, 0].max(), pol[:, 1].max())
            exato[i] = b4 if q is None else (min(q[0], b4[0]), min(q[1], b4[1]), max(q[2], b4[2]), max(q[3], b4[3]))

    # 2. alinhamentos : linhas interrompidas que saem para lá das peças nos dois extremos (e as colineares com elas)
    ys, xs = np.nonzero(cheio)
    if len(xs):
        ex0, ex1, ey0, ey1 = xs.min() / f + X0, xs.max() / f + X0, ys.min() / f + Y0, ys.max() / f + Y0
    else:
        ex0, ex1, ey0, ey1 = X0, X1, Y0, Y1
    fora = 0.5 / k
    locais = [l for l in interrompidas if (dentro(l[1], l[2], l[1], l[3]) if l[0] == "v" else dentro(l[2], l[1], l[3], l[1]))]
    eixo_c = {"v": [], "h": []}
    marcas = [((x0 + x1) / 2, (y0 + y1) / 2) for x0, y0, x1, y1, t in folha.palavras if RE_EIXO.match(t) and X0 <= (x0 + x1) / 2 <= X1 and Y0 <= (y0 + y1) / 2 <= Y1]
    perto, lado = 2.0 / k, 0.10 / k
    for o, c, a, b, cr in locais:                           # alinhamento : tem a sua marca (1, 2, A, B…) junto de um extremo, ou atravessa tudo
        if (b - a) * k < 3.0:
            continue
        lo, hi = (ey0, ey1) if o == "v" else (ex0, ex1)
        marcada = any(abs((mx if o == "v" else my) - c) <= lado and (a - perto <= (my if o == "v" else mx) <= a + lado or b - lado <= (my if o == "v" else mx) <= b + perto)
                      for mx, my in marcas)
        if marcada or (a < lo - fora and b > hi + fora):
            eixo_c[o].append((c, cr))

    def e_eixo(l):
        return any(abs(l[1] - c) < 0.6 and l[4] == cr for c, cr in eixo_c[l[0]])
    certos = [l for l in locais if e_eixo(l)]
    cores = Counter(l[4] for l in certos)
    eixos = certos
    if cores:
        cor_eixo, n_cor = cores.most_common(1)[0]
        outros = [l for l in locais if not e_eixo(l) and (l[3] - l[2]) * k >= 1.0]
        if n_cor >= 0.6 * len(certos) and sum(1 for l in outros if l[4] == cor_eixo) <= 0.2 * max(len(outros), 1):
            eixos = [l for l in locais if l[4] == cor_eixo]     # a cor distingue os alinhamentos : decide a cor
    ids = {id(l) for l in eixos}
    tracejadas = [l for l in locais if id(l) not in ids]

    # 3. barreiras (traços contínuos, linhas interrompidas, secções) e faces fechadas
    s = solidos[(np.maximum(solidos[:, 0], solidos[:, 2]) >= X0) & (np.minimum(solidos[:, 0], solidos[:, 2]) <= X1)
                & (np.maximum(solidos[:, 1], solidos[:, 3]) >= Y0) & (np.minimum(solidos[:, 1], solidos[:, 3]) <= Y1)]
    tracos = np.zeros_like(cheio)
    for xa, ya, xb, yb in np.round((s - (X0, Y0, X0, Y0)) * f).astype(np.int32):
        cv2.line(tracos, (int(xa), int(ya)), (int(xb), int(yb)), 1, 1)
    solido = cheio | tracos
    bar = solido.copy()
    for o, c, a, b, _ in tracejadas:
        p = T([(c, a), (c, b)] if o == "v" else [(a, c), (b, c)])
        cv2.line(bar, (int(p[0][0]), int(p[0][1])), (int(p[1][0]), int(p[1][1])), 1, 1)
    bar[0, :] = bar[-1, :] = 0
    bar[:, 0] = bar[:, -1] = 0
    n_fc, fc_lab, fc_st, _ = cv2.connectedComponentsWithStats((bar == 0).astype(np.uint8), 4)
    exterior = {int(v) for v in np.unique(np.concatenate([fc_lab[0, :], fc_lab[-1, :], fc_lab[:, 0], fc_lab[:, -1]]))}

    def anel_solido(mask, xa, ya):
        """Fração do contorno exterior de uma máscara local que assenta em traço contínuo ou trama."""
        anel = cv2.dilate(mask, K3) & (1 - mask)
        tot = int(anel.sum())
        hh, ww = mask.shape
        apoio = cv2.dilate(tracos[ya:ya + hh, xa:xa + ww], K3) | (cheio[ya:ya + hh, xa:xa + ww] & (1 - mask))
        return (float((anel & apoio).sum()) / tot) if tot else 0.0

    # 4. moldes de aligeiramento : faces quadradas repetidas com o mesmo módulo (as cortadas por cotas são recuperadas)
    quad = [v for v in range(1, n_fc) if v not in exterior and 0.3 <= fc_st[v][2] * px <= 1.3
            and abs(int(fc_st[v][2]) - int(fc_st[v][3])) <= 2 and fc_st[v][4] >= 0.9 * fc_st[v][2] * fc_st[v][3]]
    celulas, modulo = [], None                              # (x, y) do canto superior esquerdo, em px (centro do traço)
    if len(quad) >= 4:
        base, _ = Counter(int(fc_st[v][2]) for v in quad).most_common(1)[0]
        cand = [v for v in quad if abs(int(fc_st[v][2]) - base) <= 2]
        cantos = {(int(fc_st[v][0]), int(fc_st[v][1])) for v in cand}

        def vizinho(q):                                      # os moldes formam uma malha : cada um tem outro a um módulo de distância
            return any((q[0] + dx_ * (base + 1) + ax, q[1] + dy_ * (base + 1) + ay) in cantos
                       for dx_, dy_ in ((1, 0), (-1, 0), (0, 1), (0, -1)) for ax in (-2, -1, 0, 1, 2) for ay in (-2, -1, 0, 1, 2))
        if len(cand) >= 4 and len(cand) >= 0.5 * len(quad) and sum(1 for q in cantos if vizinho(q)) >= 0.75 * len(cantos):
            xs_c = sorted({int(fc_st[v][0]) for v in cand})
            difs = [b - a for a, b in zip(xs_c, xs_c[1:]) if abs((b - a) - (base + 1)) <= 3]
            mod_px = float(np.median(difs)) if difs else base + 1.0
            modulo = round(mod_px * px, 3)
            feitas = {(int(fc_st[v][0]) - 1, int(fc_st[v][1]) - 1) for v in cand}
            mp = int(round(mod_px))

            def aresta(xa, ya, xb, yb):
                xa, xb, ya, yb = max(0, xa - 1), min(W, xb + 2), max(0, ya - 1), min(H, yb + 2)
                r = bar[ya:yb, xa:xb]
                return (r.max(axis=0) if (xb - xa) > (yb - ya) else r.max(axis=1)).mean() if r.size else 0.0
            fila = list(feitas)
            while fila:
                cx, cy = fila.pop()
                for dx_, dy_ in ((mp, 0), (-mp, 0), (0, mp), (0, -mp)):
                    nx, ny = cx + dx_, cy + dy_
                    if any(abs(nx - q[0]) <= 2 and abs(ny - q[1]) <= 2 for q in ((nx, ny),) if q in feitas) or nx < 1 or ny < 1 or nx + mp >= W - 1 or ny + mp >= H - 1:
                        continue
                    if any((nx + ax, ny + ay) in feitas for ax in (-2, -1, 0, 1, 2) for ay in (-2, -1, 0, 1, 2)):
                        continue
                    if cheio[ny + 2:ny + mp - 1, nx + 2:nx + mp - 1].any():
                        continue
                    if min(aresta(nx, ny, nx + mp, ny), aresta(nx, ny + mp, nx + mp, ny + mp),
                           aresta(nx, ny, nx, ny + mp), aresta(nx + mp, ny, nx + mp, ny + mp)) >= 0.85:
                        feitas.add((nx, ny))
                        fila.append((nx, ny))
            celulas = sorted(feitas)
    m_moldes = np.zeros((H, W), np.uint8)
    if celulas:
        mp = int(round(modulo / px))
        for cx, cy in celulas:
            m_moldes[cy:cy + mp + 1, cx:cx + mp + 1] = 1
    face_molde = set()
    if celulas:
        for v in {int(q) for q in np.unique(fc_lab[m_moldes > 0])} - {0}:
            fx, fy, fw, fh, fa = (int(q) for q in fc_st[v])
            if fa * m2 < 4 and m_moldes[fy:fy + fh, fx:fx + fw][fc_lab[fy:fy + fh, fx:fx + fw] == v].mean() > 0.8:
                face_molde.add(v)

    # 5. etiquetas da planta
    rot = []
    for x0, y0, x1, y1, t in folha.palavras:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (X0 <= cx <= X1 and Y0 <= cy <= Y1):
            continue
        t = _texto(t)
        tipo = "Pilar" if RE_PILAR.match(t) else "Parede" if RE_PAREDE.match(t) else "Núcleo" if RE_NUCLEO.match(t) else "Viga" if RE_VIGA.match(t) else \
            "sec" if RE_SEC.match(t) else None
        if tipo:
            rot.append({"t": t, "tipo": tipo, "x": (cx - X0) * f, "y": (cy - Y0) * f})

    # 6. peças : cada trama cheia é uma secção (as tramas parciais ou em falta são resolvidas em medicao.py, entre plantas)
    pecas, face_de_peca = [], set()
    for i in range(1, n_el):
        x, y, w, h, _ = (int(v) for v in el_st[i])
        m = 70
        xa, ya, xb, yb = max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)
        sub = (el_lab[ya:yb, xa:xb] == i).astype(np.uint8)
        tocadas = {int(v) for v in np.unique(fc_lab[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3][cv2.dilate((el_lab[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3] == i).astype(np.uint8), K5) > 0])} - {0}
        completa = False
        area, per, L, B = _medidas(sub)
        qy, qx = np.nonzero(sub)
        ret = bool(area >= 0.93 * L * B)
        area, per, L, B = area * m2, per * px, L * px, B * px
        if ret and i in exato:                               # retângulo ortogonal : lados pela caixa vetorial, ao centímetro
            ew, eh = float(exato[i][2] - exato[i][0]) * k, float(exato[i][3] - exato[i][1]) * k
            if abs(max(ew, eh) - L) <= 0.03 and abs(min(ew, eh) - B) <= 0.03:
                L, B = round(max(ew, eh), 2), round(min(ew, eh), 2)
                area, per = L * B, 2 * (L + B)
        pecas.append({"id": i, "area": area, "a": _lado(L), "b": _lado(B), "retangular": ret,
                      "perimetro": per, "cx": xa + float(qx.mean()), "cy": ya + float(qy.mean()),
                      "caixa": (xa + int(qx.min()), ya + int(qy.min()), xa + int(qx.max()), ya + int(qy.max())),
                      "faces": tocadas, "com_trama": True, "completada": completa, "etiquetas": []})

    # secções desenhadas só em contorno (sem trama) : face retangular pequena fechada por traço contínuo
    vazias = []
    for v in range(1, n_fc):
        fx, fy, fw, fh, fa = (int(q) for q in fc_st[v])
        if v in exterior or v in face_de_peca or v in face_molde or not (0.02 <= fa * m2 <= 1.0) or min(fw, fh) * px < 0.12 or max(fw, fh) * px > 1.6:
            continue
        if fa / float(fw * fh) < 0.85:
            continue
        if modulo and abs(fw * px - modulo) < 0.05 and abs(fh * px - modulo) < 0.05:
            continue
        xa, ya = max(0, fx - 3), max(0, fy - 3)
        if anel_solido((fc_lab[ya:fy + fh + 3, xa:fx + fw + 3] == v).astype(np.uint8), xa, ya) < 0.9:
            continue
        vazias.append({"id": -v, "area": (fw + 1) * (fh + 1) * m2, "a": _lado(max(fw + 1, fh + 1) * px), "b": _lado(min(fw + 1, fh + 1) * px),
                       "retangular": True, "perimetro": 2 * (fw + fh + 2) * px, "cx": fx + fw / 2, "cy": fy + fh / 2,
                       "caixa": (fx, fy, fx + fw, fy + fh), "faces": set(), "com_trama": False, "completada": False, "etiquetas": []})

    lim = 1.3 / px
    pares = []
    for ri, r in enumerate(rot):
        if r["tipo"] not in ("Pilar", "Parede", "Núcleo"):
            continue
        for p in pecas:
            d = _dist_caixa(r["x"], r["y"], p["caixa"])
            if d <= lim:
                alongada = p["a"] / max(p["b"], 0.01) > 4 or p["area"] > 1.5
                pares.append((d + (0.6 / px if r["tipo"] == "Pilar" and alongada else 0), ri, p["id"]))
        if r["tipo"] != "Núcleo":
            for p in vazias:
                d = _dist_caixa(r["x"], r["y"], p["caixa"])
                if d <= 0.8 / px:
                    pares.append((d + 0.4 / px, ri, p["id"]))
    por_id = {p["id"]: p for p in pecas + vazias}
    usados_r, com_pilar = set(), set()
    for d, ri, pid in sorted(pares):
        p, r = por_id[pid], rot[ri]
        if ri in usados_r or (r["tipo"] == "Pilar" and pid in com_pilar) or (pid < 0 and p["etiquetas"]):
            continue
        p["etiquetas"].append(r)
        usados_r.add(ri)
        if r["tipo"] == "Pilar":
            com_pilar.add(pid)
    for p in pecas:                                         # pilar que nasce sobre uma parede de núcleo : a etiqueta não é da parede
        tipos = {r["tipo"] for r in p["etiquetas"]}
        if "Núcleo" in tipos and "Pilar" in tipos:
            for r in [r for r in p["etiquetas"] if r["tipo"] == "Pilar"]:
                p["etiquetas"].remove(r)
                usados_r.discard(rot.index(r))
    pecas += [p for p in vazias if p["etiquetas"]]
    sem_peca = [r["t"] for ri, r in enumerate(rot) if r["tipo"] in ("Pilar", "Parede", "Núcleo") and ri not in usados_r]

    elementos, n_anon = [], 0
    for p in pecas:
        tipos = Counter(r["tipo"] for r in p["etiquetas"])
        if tipos:
            tipo = tipos.most_common(1)[0][0]
            nome = " + ".join(sorted((r["t"] for r in p["etiquetas"]), key=lambda q: (re.sub(r"\d", "", q), int(re.sub(r"\D", "", q) or 0))))
        else:
            n_anon += 1
            tipo = "Parede" if (p["a"] / max(p["b"], 0.01) > 4 or p["area"] > 1.5) else "Pilar"
            nome = f"s/ etiqueta {n_anon}"
        p["tipo"], p["nome"] = tipo, nome
        elementos.append({"nome": nome, "tipo": tipo, "area": round(p["area"], 4), "a": p["a"], "b": p["b"], "retangular": p["retangular"],
                          "perimetro": round(p["perimetro"], 2), "com_trama": p["com_trama"], "completada": p["completada"],
                          "etiquetado": bool(tipos), "_caixa": p["caixa"]})

    # 7. laje : reunião das faces que tocam peças ou que são moldes ; área bruta = interior do contorno exterior
    toca = set()
    for p in pecas:
        if p["com_trama"]:
            toca |= p["faces"]
    sel = np.zeros(n_fc, dtype=bool)
    for v in (toca | face_molde | face_de_peca) - exterior:
        sel[v] = True
    laje = sel[fc_lab].astype(np.uint8)
    ids_laje = [p["id"] for p in pecas if p["com_trama"] and any(sel[v] for v in p["faces"])]
    laje[np.isin(el_lab, ids_laje)] = 1                      # as secções que tocam a laje fazem parte dela (não se deduzem)
    laje |= m_moldes
    laje = cv2.dilate(cv2.morphologyEx(laje, cv2.MORPH_CLOSE, K5), K3)
    cs, _ = cv2.findContours(laje, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cs = [c for c in cs if cv2.contourArea(c) * m2 >= 1.0]
    bruta = np.zeros_like(laje)
    cv2.drawContours(bruta, cs, -1, 1, -1)
    perto_laje = cv2.dilate(bruta, K5)                       # cantos pequenos fechados por traços (encontro de duas vigas de bordo)
    juntar = [v for v in range(1, n_fc) if v not in exterior and not sel[v] and fc_st[v][4] * m2 < 0.5
              and perto_laje[fc_st[v][1]:fc_st[v][1] + fc_st[v][3], fc_st[v][0]:fc_st[v][0] + fc_st[v][2]].any()]
    if juntar:
        _, x_lab = cv2.connectedComponents(np.isin(fc_lab, juntar).astype(np.uint8), 4)
        toca_x = {int(q) for q in np.unique(x_lab[(perto_laje == 1)])} - {0}
        if toca_x:
            laje = cv2.dilate(cv2.morphologyEx(bruta | np.isin(x_lab, list(toca_x)).astype(np.uint8), cv2.MORPH_CLOSE, K5), K3) | bruta
            cs, _ = cv2.findContours(laje, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cs = [c for c in cs if cv2.contourArea(c) * m2 >= 1.0]
            bruta = np.zeros_like(laje)
            cv2.drawContours(bruta, cs, -1, 1, -1)
    area_bruta = sum(cv2.contourArea(c) for c in cs) * m2
    perimetro = sum(cv2.arcLength(c, True) for c in cs) * px
    # aberturas : interior dos núcleos (escadas, elevador) = invólucro convexo de cada grupo de paredes de núcleo, sem as paredes
    nuc = np.zeros_like(laje)
    for p in pecas:
        if p["com_trama"] and p["tipo"] == "Núcleo":
            nuc[el_lab == p["id"]] = 1
    m_aber = np.zeros_like(laje)
    aberturas = []
    if nuc.any():
        r75 = int(0.75 / px)
        ng, g_lab = cv2.connectedComponents(cv2.dilate(nuc, np.ones((2 * r75 + 1, 2 * r75 + 1), np.uint8)), 8)
        for g in range(1, ng):
            pts = np.column_stack(np.nonzero((g_lab == g) & (nuc == 1))[::-1]).astype(np.int32)
            if len(pts) < 3:
                continue
            hm = np.zeros_like(laje)
            cv2.fillConvexPoly(hm, cv2.convexHull(pts), 1)
            ab = hm & (1 - cheio) & bruta
            a = float(ab.sum()) * m2
            if a >= 0.5:
                m_aber |= ab
                qy, qx = np.nonzero(ab)
                aberturas.append({"area": round(a, 2), "_caixa": (int(qx.min()), int(qy.min()), int(qx.max()), int(qy.max()))})
    area_fora = 0.0
    if len(xs) >= 3:
        hm = np.zeros_like(laje)
        cv2.fillConvexPoly(hm, cv2.convexHull(np.column_stack((xs, ys)).astype(np.int32)), 1)
        hm = cv2.dilate(hm, np.ones((41, 41), np.uint8))
        m_fora = ((bruta == 1) & (hm == 0)).astype(np.uint8)
        area_fora = float(m_fora.sum()) * m2
    else:
        m_fora = np.zeros_like(laje)

    # 8. vigas : faixas entre linhas paralelas, cortadas pelas peças → vãos livres ; cada etiqueta V… fica com o vão mais próximo
    vaos = []
    for o, c1, c2, a, b in _faixas_viga(tracejadas, s, k):
        cm = (c1 + c2) / 2
        p0, p1 = T([(cm, a), (cm, b)] if o == "v" else [(a, cm), (b, cm)])
        if o == "v":
            xx = int(min(max(p0[0], 0), W - 1))
            y0_, y1_ = max(0, int(p0[1])), min(H - 1, int(p1[1]))
            linha, ini = cheio[y0_:y1_ + 1, xx], y0_
        else:
            yy = int(min(max(p0[1], 0), H - 1))
            x0_, x1_ = max(0, int(p0[0])), min(W - 1, int(p1[0]))
            linha, ini = cheio[yy, x0_:x1_ + 1], x0_
        if not len(linha):
            continue
        livre = np.concatenate([[0], (linha == 0).astype(np.int8), [0]])
        d = np.diff(livre)
        for u, v in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
            if (v - u) * px >= 0.4:
                q1, q2 = T([(c1, 0), (c2, 0)] if o == "v" else [(0, c1), (0, c2)])
                cx = (int(q1[0]), ini + int(u), int(q2[0]), ini + int(v)) if o == "v" else (ini + int(u), int(q1[1]), ini + int(v), int(q2[1]))
                vaos.append({"b": round(float((c2 - c1) * k), 2), "L": round(float((v - u) * px), 2), "caixa": cx})
    vaos = _fundir_vaos(vaos, px)
    rv = [r for r in rot if r["tipo"] == "Viga"]
    secs = [r for r in rot if r["tipo"] == "sec"]
    vigas, ur, uf = [], set(), set()
    for i, j in _atribuir([[_dist_caixa(r["x"], r["y"], v["caixa"]) for v in vaos] for r in rv], 0.9 / px):
        ur.add(i)
        uf.add(j)
        m = RE_VIGA.match(rv[i]["t"])
        bs = hs = None
        if m.group(2):
            bs, hs = _num(m.group(2)) / 100, _num(m.group(3)) / 100
        else:
            perto = [q for q in secs if math.hypot(q["x"] - rv[i]["x"], q["y"] - rv[i]["y"]) <= 1.5 / px]
            if perto:
                ms = RE_SEC.match(min(perto, key=lambda q: math.hypot(q["x"] - rv[i]["x"], q["y"] - rv[i]["y"]))["t"])
                bs, hs = _num(ms.group(1)) / 100, _num(ms.group(2)) / 100
        vigas.append({"nome": m.group(1), "b_medido": vaos[j]["b"], "vao": vaos[j]["L"], "b": bs, "h": hs, "_caixa": vaos[j]["caixa"]})
    vigas.sort(key=lambda v: (int(re.sub(r"\D", "", v["nome"].split(".")[0]) or 0), v["nome"]))
    vigas_sem = [RE_VIGA.match(rv[i]["t"]).group(1) for i in range(len(rv)) if i not in ur]

    return {"caixa_pt": tuple(round(v, 1) for v in caixa), "px": px, "elementos": elementos, "vigas": vigas, "_vaos_viga": list(vigas),
            "vigas_sem_medida": vigas_sem, "etiquetas_sem_peca": sem_peca, "n_eixos": len(eixos),
            "laje": {"area_bruta": round(area_bruta, 2), "area_fora_do_perimetro": round(area_fora, 2), "perimetro": round(perimetro, 2),
                     "aberturas": aberturas, "moldes": len(celulas), "modulo": modulo},
            "_mascaras": {"bruta": bruta, "fora": m_fora, "cheio": cheio, "moldes": m_moldes, "aberturas": m_aber, "bar": bar}}


def ler_folha(folha: Folha, escala: int | None = None) -> dict:
    """Lê todas as plantas de uma folha. Devolve {escala, escala_lida, plantas: [...], avisos: [...]}."""
    avisos = []
    lida, unica = ler_escala(folha)
    esc = int(escala) if escala else lida
    if not esc:
        return {"ok": False, "erro": "escala", "avisos": ["Escala não encontrada no desenho : indique-a (ex.: 100 para 1/100)."], "plantas": []}
    if escala and lida and int(escala) != lida:
        avisos.append(f"Escala indicada 1/{escala} diferente da escrita no desenho (1/{lida}) : usada 1/{escala}.")
    if not escala and not unica:
        avisos.append(f"Várias escalas escritas na folha : usada 1/{esc} (a mais frequente). Confirme.")
    k = 0.0254 / 72 * esc
    if not len(folha.segs):
        return {"ok": False, "erro": "raster", "avisos": ["O PDF não tem desenho vetorial (é uma imagem digitalizada) : a medição direta não é possível."],
                "plantas": [], "escala": esc}
    solidos, interrompidas = _linhas(folha.segs, folha.seg_lum, folha.seg_trac)
    caixas = _plantas(interrompidas, k, folha.largura, folha.altura)
    if not caixas:
        if not folha.cheios:
            return {"ok": False, "erro": "sem_pecas", "escala": esc, "plantas": [],
                    "avisos": ["Não encontrei secções com trama cheia (pilares/paredes) nem alinhamentos : não é uma planta estrutural legível por este método."]}
        P = np.vstack(folha.cheios)
        caixas = [(float(P[:, 0].min()) - 2 / k, float(P[:, 1].min()) - 2 / k, float(P[:, 0].max()) + 2 / k, float(P[:, 1].max()) + 2 / k)]
        avisos.append("Sem alinhamentos reconhecidos : a folha foi tratada como uma única planta.")
    niveis = _niveis(folha.palavras, k)
    plantas = []
    for cx in caixas:
        p = medir_planta(folha, solidos, interrompidas, cx, k)
        if not p["elementos"]:
            continue
        p["niveis"] = [{kk: v for kk, v in n.items() if kk != "_xy"} for n in niveis
                       if cx[0] <= n["_xy"][0] <= cx[2] and cx[1] <= n["_xy"][1] <= cx[3]]
        plantas.append(p)
    lados = [e["b"] for p in plantas for e in p["elementos"] if e["tipo"] == "Pilar"]
    if lados and not (0.12 <= float(np.median(lados)) <= 1.5):
        avisos.append(f"Lado mediano dos pilares = {float(np.median(lados)):.2f} m : a escala 1/{esc} parece errada. Confirme a escala.")
    return {"ok": bool(plantas), "escala": esc, "escala_lida": lida, "plantas": plantas, "avisos": avisos, "motor": folha.motor,
            "erro": None if plantas else "sem_pecas"}
