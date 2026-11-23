"""Leitor DWFX (= XPS da Autodesk) : caminhos e textos de cada folha com a CAMADA do CAD e coordenadas em METROS do modelo.

- A escala vem do recurso W2X : <Units Transform="k,…,offX,offY,0,1"> → unidades DWF = metros × k + off.
- A camada vem de <RenditionSync refName="Nome_do_Path"><Layer Name="…"/> : aplica-se a partir desse caminho, por ordem do documento.
- Os RenderTransform das Canvas são compostos ; tudo é levado ao referencial dos caminhos do desenho antes de passar a metros.
Determinístico, só biblioteca padrão."""
from __future__ import annotations

import html
import io
import math
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

NS = "{http://schemas.microsoft.com/xps/2005/06}"
_TOK = re.compile(r"[MmLlHhVvCcQqSsZzAaF]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_ARC = re.compile(r"[aA]\s*(-?[0-9.]+)\s*[, ]\s*(-?[0-9.]+)\s+[-0-9.]+\s+[01]\s+[01]")


@dataclass
class Elemento:
    camada: str
    tipo: str                          # "path" | "texto"
    pls: list = field(default_factory=list)   # polilinhas em metros [(x, y), …]
    fill: str | None = None
    texto: str = ""
    pos: tuple = (0.0, 0.0)            # centro aproximado do texto, em metros
    altura: float = 0.0                # altura do texto, em metros
    arcos: list = field(default_factory=list)  # raios dos arcos, em metros


@dataclass
class Folha:
    indice: int
    nome: str
    upm: float | None                  # unidades DWF por metro (None = sem escala → não mensurável)
    elementos: list
    camadas: list


def e_dwfx(data: bytes) -> bool:
    if not data[:2] == b"PK":
        return False
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        return False
    return any(n.endswith(".fdseq") for n in names) and any(n.endswith(".fpage") for n in names)


def parse_data(d: str) -> list:
    """Mini-linguagem de caminhos XPS → polilinhas (curvas reduzidas aos pontos finais)."""
    t = _TOK.findall(d.replace(",", " "))
    i, cmd, cur, start, out, pl = 0, None, (0.0, 0.0), None, [], []

    def num():
        nonlocal i
        v = float(t[i]); i += 1
        return v
    try:
        while i < len(t):
            if re.fullmatch(r"[A-Za-z]", t[i]):
                cmd = t[i]; i += 1
                if cmd == "F":                  # regra de preenchimento : F0 / F1
                    i += 1; cmd = None; continue
            if cmd is None:
                i += 1; continue
            if cmd in "Mm":
                x, y = num(), num()
                if cmd == "m":
                    x, y = cur[0] + x, cur[1] + y
                if len(pl) > 1:
                    out.append(pl)
                cur = (x, y); start = cur; pl = [cur]; cmd = "L" if cmd == "M" else "l"
            elif cmd in "Ll":
                x, y = num(), num()
                if cmd == "l":
                    x, y = cur[0] + x, cur[1] + y
                cur = (x, y); pl.append(cur)
            elif cmd in "Hh":
                x = num(); cur = (cur[0] + x if cmd == "h" else x, cur[1]); pl.append(cur)
            elif cmd in "Vv":
                y = num(); cur = (cur[0], cur[1] + y if cmd == "v" else y); pl.append(cur)
            elif cmd in "Cc":
                v = [num() for _ in range(6)]
                cur = (cur[0] + v[4], cur[1] + v[5]) if cmd == "c" else (v[4], v[5]); pl.append(cur)
            elif cmd in "QqSs":
                v = [num() for _ in range(4)]
                cur = (cur[0] + v[2], cur[1] + v[3]) if cmd in "qs" else (v[2], v[3]); pl.append(cur)
            elif cmd in "Aa":
                v = [num() for _ in range(7)]
                cur = (cur[0] + v[5], cur[1] + v[6]) if cmd == "a" else (v[5], v[6]); pl.append(cur)
            elif cmd in "Zz":
                if start:
                    pl.append(start); cur = start
                if len(pl) > 1:
                    out.append(pl)
                pl = [cur]; cmd = None
            else:
                i += 1
    except (IndexError, ValueError):
        pass
    if len(pl) > 1:
        out.append(pl)
    return out


def abrir(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def folhas(z: zipfile.ZipFile) -> list:
    """[(fpage, secção, nome da folha)] pela ordem do documento."""
    names = set(z.namelist())
    seq = []
    for doc in sorted(n for n in names if n.endswith(".fdoc")):
        seq += re.findall(r'Source="([^"]+\.fpage)"', z.read(doc).decode("utf-8", "ignore"))
    res = []
    for fp in seq:
        fp = fp.lstrip("/")
        sec = fp.rsplit("/", 1)[0]
        nome = ""
        if sec + "/descriptor.xml" in names:
            m = re.search(r'<ePlot:Page[^>]* name="([^"]+)"', z.read(sec + "/descriptor.xml").decode("utf-8", "ignore"))
            nome = html.unescape(m.group(1)) if m else ""
        res.append((fp, sec, nome or fp.rsplit("/", 2)[-2]))
    return res


def _mat(s: str | None):
    if not s:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    try:
        v = [float(x) for x in s.split(",")]
        return tuple(v[:6]) if len(v) >= 6 else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    except ValueError:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _mul(a, b):
    """a ∘ b (aplica b e depois a), matrizes XPS m11,m12,m21,m22,dx,dy (vetor linha)."""
    return (b[0] * a[0] + b[1] * a[2], b[0] * a[1] + b[1] * a[3],
            b[2] * a[0] + b[3] * a[2], b[2] * a[1] + b[3] * a[3],
            b[4] * a[0] + b[5] * a[2] + a[4], b[4] * a[1] + b[5] * a[3] + a[5])


def _ap(m, p):
    return (p[0] * m[0] + p[1] * m[2] + m[4], p[0] * m[1] + p[1] * m[3] + m[5])


def _inv(m):
    det = m[0] * m[3] - m[1] * m[2]
    if abs(det) < 1e-12:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    a, b, c, d = m[3] / det, -m[1] / det, -m[2] / det, m[0] / det
    return (a, b, c, d, -(m[4] * a + m[5] * c), -(m[4] * b + m[5] * d))


def ler(z: zipfile.ZipFile, idx: int, lista=None) -> Folha:
    lista = lista or folhas(z)
    fp, sec, nome = lista[idx]
    upm, off, layers, sync = None, (0.0, 0.0), {}, {}
    for n in z.namelist():
        if not (n.startswith(sec + "/") and n.endswith(".xml")) or "descriptor" in n:
            continue
        s = z.read(n).decode("utf-8", "ignore")
        m = re.search(r'<Units[^>]*Transform="([^"]+)"', s)
        if not m:
            continue
        v = [float(x) for x in m.group(1).split(",")]
        if len(v) == 16 and v[0] > 0:
            upm, off = v[0], (v[12], v[13])
        for rs in re.finditer(r'<RenditionSync refName="([^"]+)">(.*?)</RenditionSync>', s, re.S):
            lm = re.search(r'<Layer(?: Name="([^"]*)")? Number="(\d+)"', rs.group(2))
            if lm:
                if lm.group(1):
                    layers[lm.group(2)] = html.unescape(lm.group(1))
                sync[rs.group(1)] = lm.group(2)
    root = ET.fromstring(z.read(fp))
    brutos, cur = [], [None]

    def walk(node, M):
        for ch in node:
            nm = ch.get("Name")
            if nm in sync:
                cur[0] = sync[nm]
            Mc = _mul(M, _mat(ch.get("RenderTransform")))
            lay = layers.get(cur[0], cur[0] or "0")
            if ch.tag == NS + "Path" and ch.get("Data"):
                brutos.append(("path", lay, Mc, ch))
            elif ch.tag == NS + "Glyphs" and ch.get("UnicodeString"):
                brutos.append(("texto", lay, Mc, ch))
            walk(ch, Mc)
    walk(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    # referencial do desenho = transformação mais frequente dos caminhos
    modo = Counter(tuple(round(x, 6) for x in b[2]) for b in brutos if b[0] == "path").most_common(1)
    Mi = _inv(modo[0][0]) if modo else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    k = upm or 1.0
    tom = (lambda p: ((p[0] - off[0]) / k, (p[1] - off[1]) / k))
    els = []
    for tipo, lay, Mc, ch in brutos:
        T = _mul(Mi, Mc)
        esc = math.sqrt(abs(T[0] * T[3] - T[1] * T[2])) or 1.0
        if tipo == "path":
            d = ch.get("Data")
            pls = [[tom(_ap(T, p)) for p in pl] for pl in parse_data(d)]
            arcos = [abs(float(a)) * esc / k for a, _ in _ARC.findall(d)]
            els.append(Elemento(lay, "path", pls, ch.get("Fill"), arcos=arcos))
        else:
            txt = " ".join(ch.get("UnicodeString").split())
            em = float(ch.get("FontRenderingEmSize") or 0)
            o = (float(ch.get("OriginX") or 0), float(ch.get("OriginY") or 0))
            c = (o[0] + 0.28 * len(txt) * em, o[1] - 0.35 * em)          # centro aproximado da linha de texto
            els.append(Elemento(lay, "texto", texto=txt, pos=tom(_ap(T, c)), altura=em * esc / k))
    return Folha(idx, nome, upm, els, sorted(set(layers.values())))
