"""Valores calculados dentro dos Excel de orçamento.

O openpyxl grava as fórmulas (=D5*E5, =SUM(F5:F40)…) sem o resultado. O Excel do computador recalcula ao abrir, mas as
pré-visualizações (telemóvel Android, Google Drive, browser, WhatsApp, a própria plataforma) mostram as células dos totais
VAZIAS: o cliente vê um orçamento «sem os cálculos totais». Aqui calcula-se cada fórmula e grava-se o resultado na célula
(<v>), mantendo a fórmula: continua editável e aparece certo em todo o lado.

Avaliador pequeno e seguro (sem eval): números, referências da mesma folha (F12, $F$12), + - * /, parênteses, SUM/SOMA,
ROUND/ARRED, MIN, MAX. Uma fórmula que não perceba fica como está (o Excel recalcula; nada se perde).
"""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

_CELL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(/>|>(.*?)</c>)', re.S)
_TOK = re.compile(r"\s*(?:(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)|([A-Z]+)\(|([-+*/(),;]))")


def _col(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def _ref(s: str):
    m = re.match(r"\$?([A-Z]+)\$?(\d+)", s)
    return _col(m.group(1)), int(m.group(2))


class _Avaliador:
    def __init__(self, num: dict, form: dict):
        self.num, self.form, self.cache, self.pilha = num, form, {}, set()

    def valor(self, c):
        if c in self.cache:
            return self.cache[c]
        if c in self.form:
            if c in self.pilha:
                raise ValueError("ciclo")
            self.pilha.add(c)
            try:
                v = self.expr(self.form[c])
            finally:
                self.pilha.discard(c)
            self.cache[c] = v
            return v
        return self.num.get(c, 0.0)

    def expr(self, f: str) -> float:
        toks, pos = [], 0
        while pos < len(f):
            m = _TOK.match(f, pos)
            if not m or m.end() == pos:
                if f[pos:].strip() == "":
                    break
                raise ValueError(f"token {f[pos:]!r}")
            toks.append(m.groups())
            pos = m.end()
        self.t, self.i = toks, 0
        v = self._soma()
        if self.i != len(self.t):
            raise ValueError("fim inesperado")
        return v

    def _peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None, None, None)

    def _soma(self):
        v = self._prod()
        while self._peek()[3] in ("+", "-"):
            op = self.t[self.i][3]
            self.i += 1
            w = self._prod()
            v = v + w if op == "+" else v - w
        return v

    def _prod(self):
        v = self._un()
        while self._peek()[3] in ("*", "/"):
            op = self.t[self.i][3]
            self.i += 1
            w = self._un()
            v = v * w if op == "*" else (v / w if w else 0.0)
        return v

    def _un(self):
        if self._peek()[3] == "-":
            self.i += 1
            return -self._un()
        if self._peek()[3] == "+":
            self.i += 1
            return self._un()
        return self._atom()

    def _args(self):
        out = []
        while True:
            num, ref, fn, op = self._peek()
            if ref and ":" in ref:
                self.i += 1
                (c1, r1), (c2, r2) = (_ref(x) for x in ref.split(":"))
                out += [self.valor((c, r)) for r in range(min(r1, r2), max(r1, r2) + 1) for c in range(min(c1, c2), max(c1, c2) + 1)]
            else:
                out.append(self._soma())
            op = self._peek()[3]
            self.i += 1
            if op == ")":
                return out
            if op not in (",", ";"):
                raise ValueError("argumentos")

    def _atom(self):
        num, ref, fn, op = self._peek()
        self.i += 1
        if num:
            return float(num)
        if ref:
            if ":" in ref:
                raise ValueError("intervalo fora de função")
            return self.valor(_ref(ref))
        if fn:
            a = self._args()
            fn = fn.upper()
            if fn in ("SUM", "SOMA"):
                return float(sum(a))
            if fn in ("MIN", "MÍNIMO"):
                return float(min(a)) if a else 0.0
            if fn in ("MAX", "MÁXIMO"):
                return float(max(a)) if a else 0.0
            if fn in ("ROUND", "ARRED"):
                return float(round(a[0], int(a[1]) if len(a) > 1 else 0))
            raise ValueError(f"função {fn}")
        if op == "(":
            v = self._soma()
            if self._peek()[3] != ")":
                raise ValueError("parêntese")
            self.i += 1
            return v
        raise ValueError("átomo")


def _fmt(v: float) -> str:
    return repr(round(v, 10)) if v != int(v) or abs(v) >= 1e15 else str(int(v))


def _folha(xml: str) -> tuple[str, int]:
    num, form = {}, {}
    for m in _CELL.finditer(xml):
        c = (_col(m.group(1)), int(m.group(2)))
        attrs, body = m.group(3), m.group(5) or ""
        fm = re.search(r"<f>(.*?)</f>", body, re.S)
        if fm:
            form[c] = fm.group(1).replace("&amp;", "&")
            continue
        vm = re.search(r"<v>(.*?)</v>", body, re.S)
        tipo = re.search(r'\bt="([^"]*)"', attrs)
        if vm and (not tipo or tipo.group(1) == "n"):
            try:
                num[c] = float(vm.group(1))
            except ValueError:
                pass
    if not form:
        return xml, 0
    ev, feitos = _Avaliador(num, form), [0]

    def troca(m):
        c = (_col(m.group(1)), int(m.group(2)))
        if c not in form:
            return m.group(0)
        try:
            v = ev.valor(c)
        except Exception:  # noqa: BLE001 — fórmula que não se percebe: fica como estava
            return m.group(0)
        body = re.sub(r"<v>.*?</v>|<v/>", "", m.group(5) or "", flags=re.S)
        attrs = re.sub(r'\s+t="[^"]*"', "", m.group(3))
        feitos[0] += 1
        return f'<c r="{m.group(1)}{m.group(2)}"{attrs}>{body}<v>{_fmt(v)}</v></c>'
    return _CELL.sub(troca, xml), feitos[0]


def preencher(path) -> int:
    """Grava o resultado de cada fórmula no próprio .xlsx (in place). Devolve o número de células preenchidas."""
    path = Path(path)
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        novo = Path(tmp) / path.name
        with zipfile.ZipFile(path) as zin, zipfile.ZipFile(novo, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                data = zin.read(it.filename)
                if it.filename.startswith("xl/worksheets/sheet") and it.filename.endswith(".xml"):
                    xml, n = _folha(data.decode("utf-8"))
                    total += n
                    data = xml.encode("utf-8")
                elif it.filename == "xl/workbook.xml":           # o Excel recalcula ao abrir (valores sempre frescos)
                    xml = data.decode("utf-8")
                    if "<calcPr" in xml:
                        xml = re.sub(r"<calcPr([^>]*?)/>", lambda m: "<calcPr" + re.sub(r'\s+fullCalcOnLoad="[^"]*"', "", m.group(1)) + ' fullCalcOnLoad="1"/>', xml)
                    else:
                        xml = xml.replace("</workbook>", '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
                    data = xml.encode("utf-8")
                zout.writestr(it, data)
        shutil.move(str(novo), str(path))
    return total
