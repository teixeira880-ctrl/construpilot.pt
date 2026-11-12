"""Digitalização / foto / imagem → traços vetoriais, para seguir exatamente o mesmo motor que um PDF vetorial.

Etapas: binarização robusta (fundo irregular, ruído) → endireitamento pelo ângulo dominante dos traços → esqueleto
(eixo de cada traço desenhado) → segmentos retos (Hough probabilístico sobre o esqueleto) → alinhamento ortogonal
dos segmentos quase horizontais/verticais → fusão dos colineares. Coordenadas devolvidas no referencial da imagem
ORIGINAL (a rotação é desfeita), para a sobreposição no ecrã bater certo com o que o utilizador vê.

Substitui, para a leitura automática, o detetor Canny + Hough (`engines/plan_cv.detect_walls`), que confundia paredes,
cotas e hachuras. Um modelo treinado (segmentação) poderá substituir `vetorizar` mais tarde sem mudar o resto.
"""
from __future__ import annotations

import base64
import math

import cv2
import numpy as np


def _carregar(imagem) -> np.ndarray:
    if isinstance(imagem, np.ndarray):
        img = imagem
    else:
        if isinstance(imagem, str):
            imagem = base64.b64decode(imagem.split(",", 1)[-1])
        img = cv2.imdecode(np.frombuffer(imagem, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("imagem ilegível")
    if img.ndim == 3:
        if img.shape[2] == 4:
            alpha = img[:, :, 3:4].astype(float) / 255
            img = (img[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def binarizar(gray: np.ndarray) -> np.ndarray:
    """Tinta = 1. Fundo irregular corrigido por divisão pelo fundo estimado; ruído isolado removido."""
    fundo = cv2.medianBlur(gray, 31) if min(gray.shape) > 64 else np.full_like(gray, 255)
    norm = cv2.divide(gray, np.maximum(fundo, 1), scale=255)
    norm = cv2.GaussianBlur(norm, (3, 3), 0)
    otsu, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Os traços finos (vidros, folhas de porta, linhas de cota) ficam cinzentos depois da digitalização: o limiar de Otsu,
    # que separa o preto do branco, perde-os. Limiar = fundo − 4 desvios do ruído do fundo (estimado pela MAD).
    fundo_px = norm[norm > max(otsu, 200)]
    sigma = 1.4826 * float(np.median(np.abs(fundo_px - np.median(fundo_px)))) if fundo_px.size else 8.0
    limiar = max(float(otsu), min(245.0, float(np.median(fundo_px) if fundo_px.size else 255) - max(12.0, 4 * sigma)))
    b = (norm < limiar).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(b, 8)
    pequenos = stats[:, cv2.CC_STAT_AREA] < 6
    pequenos[0] = False
    b[pequenos[lab]] = 0
    return b


def angulo_dominante(tinta: np.ndarray) -> float:
    """Inclinação da folha (graus, |a| ≤ 10): estimativa pelos traços longos (Hough) e afinação ao centésimo de grau
    pelo perfil de projeção (as paredes alinhadas dão picos mais altos). Um erro de 0,1° desloca 4 px ao fim de uma
    parede de 2000 px — o suficiente para partir uma face em dois alinhamentos."""
    linhas = cv2.HoughLinesP(tinta * 255, 1, np.pi / 1800, 120, minLineLength=max(60, min(tinta.shape) // 12), maxLineGap=3)
    base = 0.0
    if linhas is not None:
        angs, pesos = [], []
        for x1, y1, x2, y2 in linhas.reshape(-1, 4):
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            ang = ((ang + 45) % 90) - 45
            if abs(ang) <= 10:
                angs.append(ang)
                pesos.append(math.hypot(x2 - x1, y2 - y1))
        if angs:
            ordem = np.argsort(angs)
            acum = np.cumsum(np.array(pesos)[ordem])
            base = float(np.array(angs)[ordem][np.searchsorted(acum, acum[-1] / 2)])
    # afinação: perfis horizontal + vertical, numa versão reduzida (≤ 1600 px)
    f = min(1.0, 1600 / max(tinta.shape))
    peq = cv2.resize(tinta.astype(np.float32), None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else tinta.astype(np.float32)
    h, w = peq.shape
    melhor, nota_max = base, -1.0
    for d in np.arange(-.2, .2001, .01):
        ang = base + d
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        r = cv2.warpAffine(peq, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        nota = float((r.sum(axis=1) ** 2).sum() + (r.sum(axis=0) ** 2).sum())
        if nota > nota_max:
            melhor, nota_max = ang, nota
    return float(melhor)


def vetorizar(imagem, px_por_m: float | None = None, dpi: float | None = None) -> dict:
    """Imagem → {linhas: [{p:((x1,y1),(x2,y2))}], angulo_graus, tamanho}. `px_por_m` (se conhecido) dimensiona os limiares."""
    from skimage.morphology import skeletonize
    gray = _carregar(imagem)
    h, w = gray.shape
    tinta = binarizar(gray)
    ang = angulo_dominante(tinta)
    centro = (w / 2, h / 2)
    if abs(ang) > .05:
        M = cv2.getRotationMatrix2D(centro, ang, 1.0)
        tinta = cv2.warpAffine(tinta, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    # fecha micro-falhas do traço (digitalização) sem colar traços paralelos próximos
    tinta = cv2.morphologyEx(tinta, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    min_len = max(8, int((.06 * px_por_m) if px_por_m else 12))
    # Texto (nomes, áreas, cotas escritas) e símbolos soltos: componentes isolados pequenos. Uma parede, uma janela
    # ou uma porta estão ligadas à rede das paredes e são grandes; uma letra nunca. Saem antes de procurar traços.
    lado_max = (.45 * px_por_m) if px_por_m else max(20, min(h, w) // 60)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(tinta, 8)
    lw, lh, la = stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT], stats[:, cv2.CC_STAT_AREA]
    soltos = np.maximum(lw, lh) < lado_max
    # Palavras (letras coladas a 1:100 ou a baixa resolução): faixa baixa (≤ 0,35 m e ≥ 6 px de altura), até 3 m de
    # comprimento, densa em tinta. Um traço de parede tem 2–4 px de altura; um móvel tem mais de 0,35 m nos dois lados.
    if px_por_m:
        baixa = np.minimum(lw, lh)
        palavra = (baixa >= 6) & (baixa <= .35 * px_por_m) & (np.maximum(lw, lh) <= 3 * px_por_m) & (la >= .10 * lw * lh)
        soltos |= palavra
    soltos[0] = False
    texto = soltos[lab]
    tinta[texto] = 0
    # Paredes cheias (« poché »): esvaziadas para ficar só o contorno — as faces da parede são as bordas da mancha.
    dt = cv2.distanceTransform(tinta, cv2.DIST_L2, 3)
    # Só é parede cheia uma mancha com ≥ 5 cm reais e ≥ 6 px de largura: um traço desfocado pela digitalização
    # (3–4 px) continua a ser lido pelo seu eixo, senão a face interior seria tomada pela face da parede.
    # Um traço desenhado tem < 0,8 mm no papel; uma parede cheia tem ≥ 1 mm (0,10 m a 1:100). Com o dpi conhecido, o
    # limiar acompanha a resolução — a 300 dpi um traço desfocado chega a 7 px e continua a ser um traço.
    meia = max(3.0, (.025 * px_por_m) if px_por_m else 3.0, (.4 * dpi / 25.4) if dpi else 0.0)
    nucleo = cv2.erode((dt >= meia).astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1)
    espesso = int(2 * meia) + 1      # um componente mais largo do que isto é uma mancha (parede cheia), não um traço
    tinta = tinta & (1 - nucleo)
    segs = []
    resto = tinta.copy()
    for horizontal in (True, False):
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (min_len, 1) if horizontal else (1, min_len))
        mask = cv2.morphologyEx(tinta, cv2.MORPH_OPEN, k)
        segs += _segmentos_da_mascara(mask, horizontal, espesso, min_len)
        resto[cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0] = 0
    # traços oblíquos (paredes inclinadas, arcos aproximados): Hough sobre o esqueleto do que sobra
    esq = skeletonize(resto.astype(bool)).astype(np.uint8)
    if esq.any():
        gap = max(2, int((.012 * px_por_m) if px_por_m else 3))
        hl = cv2.HoughLinesP(esq * 255, 1, np.pi / 360, max(6, min_len // 2), minLineLength=min_len, maxLineGap=gap)
        if hl is not None:
            segs += [tuple(map(float, l)) for l in hl.reshape(-1, 4)]
    segs = _fundir_colineares(_ortogonalizar(segs), tol=1.6)
    # desfaz a rotação: referencial da imagem original
    if abs(ang) > .05:
        Minv = cv2.getRotationMatrix2D(centro, -ang, 1.0)
        def back(x, y):
            return (Minv[0, 0] * x + Minv[0, 1] * y + Minv[0, 2], Minv[1, 0] * x + Minv[1, 1] * y + Minv[1, 2])
    else:
        def back(x, y):
            return (x, y)
    linhas = [{"p": (back(x1, y1), back(x2, y2)), "camada": "", "largura": None} for x1, y1, x2, y2 in segs]
    endireitadas = [{"p": ((x1, y1), (x2, y2)), "camada": "", "largura": None} for x1, y1, x2, y2 in segs]
    return {"linhas": linhas, "linhas_endireitadas": endireitadas, "angulo_graus": round(ang, 3), "tamanho": [w, h],
            "rotacao": {"centro": centro, "angulo": ang}}


def _segmentos_da_mascara(mask: np.ndarray, horizontal: bool, espesso: int, min_len: int):
    """Cada componente de uma máscara direcional é um traço: fino → o seu eixo; espesso (parede cheia, « poché »)
    → as suas duas faces. Um traço contínuo dá UM segmento (sem a fragmentação do Hough)."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        comp, larg = (w, h) if horizontal else (h, w)
        if comp < min_len:
            continue
        if larg <= espesso:
            ys, xs = np.nonzero(lab[y:y + h, x:x + w] == i)
            c = (ys.mean() + y) if horizontal else (xs.mean() + x)
            out.append((x, c, x + w - 1, c) if horizontal else (c, y, c, y + h - 1))
        else:
            if horizontal:
                out += [(x, y, x + w - 1, y), (x, y + h - 1, x + w - 1, y + h - 1)]
            else:
                out += [(x, y, x, y + h - 1), (x + w - 1, y, x + w - 1, y + h - 1)]
    return [tuple(map(float, s)) for s in out]


def _ortogonalizar(segs, tol_graus: float = 2.0):
    out = []
    for x1, y1, x2, y2 in segs:
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        if min(a, 180 - a) <= tol_graus:
            y = (y1 + y2) / 2
            out.append((min(x1, x2), y, max(x1, x2), y))
        elif abs(a - 90) <= tol_graus:
            x = (x1 + x2) / 2
            out.append((x, min(y1, y2), x, max(y1, y2)))
        else:
            out.append((x1, y1, x2, y2))
    return out


def _fundir_colineares(segs, tol: float):
    """Funde os segmentos horizontais (e verticais) da mesma linha que se tocam ou se sobrepõem — o esqueleto parte-os."""
    hs = sorted((s for s in segs if s[1] == s[3]), key=lambda s: (s[1], s[0]))
    vs = sorted((s for s in segs if s[0] == s[2] and s[1] != s[3]), key=lambda s: (s[0], s[1]))
    outros = [s for s in segs if s not in hs and s not in vs]

    def fundir(lista, horizontal):
        linhas = []        # agrupa por coordenada transversal (tolerância), depois funde intervalos
        for s in lista:
            c = s[1] if horizontal else s[0]
            a, b = (s[0], s[2]) if horizontal else (s[1], s[3])
            for L in linhas:
                if abs(L["c"] - c) <= tol:
                    L["iv"].append((a, b, c, b - a))
                    tot = sum(i[3] for i in L["iv"])
                    L["c"] = sum(i[2] * i[3] for i in L["iv"]) / tot if tot else c
                    break
            else:
                linhas.append({"c": c, "iv": [(a, b, c, b - a)]})
        res = []
        for L in linhas:
            ivs = sorted((a, b) for a, b, *_ in L["iv"])
            cur = list(ivs[0])
            fundidos = []
            for a, b in ivs[1:]:
                if a <= cur[1] + tol * 1.5:
                    cur[1] = max(cur[1], b)
                else:
                    fundidos.append(tuple(cur))
                    cur = [a, b]
            fundidos.append(tuple(cur))
            for a, b in fundidos:
                res.append((a, L["c"], b, L["c"]) if horizontal else (L["c"], a, L["c"], b))
        return res
    return fundir(hs, True) + fundir(vs, False) + outros
