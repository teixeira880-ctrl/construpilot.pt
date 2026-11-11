"""Manifesto das mensagens do BACKEND que aparecem no ecrã (erros, avisos, confirmações).

Complementa ``data/i18n_manifest.json`` (textos do frontend, gerado no build) para que o motor de
tradução (routes/i18n_auto.py) também traduza o que a API devolve e o frontend mostra em toasts
e caixas de erro: ``HTTPException(…, "…")``, ``detail="…"``, ``{"detail"|"message"|"error": "…"}``.

f-strings viram padrões com variáveis: f"Ficheiro {nome} vazio" → "Ficheiro {0} vazio".
Só texto escrito no código-fonte entra aqui — nunca dados de utilizadores.

Uso:  python scripts/i18n_backend_manifest.py   (escreve data/i18n_manifest_backend.json)
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ["routes", "engines", "core"]
OUT = ROOT / "data" / "i18n_manifest_backend.json"
KEYS = {"detail", "message", "error", "warning", "hint", "reason", "msg"}
SKIP_PARTS = {"tests", "__pycache__", "bet_agent"}
DATA_DICTS = [("engines/plan_i18n.py", "PLAN_I18N", "en")]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _looks_like_text(s: str) -> bool:
    if not s or len(s) < 3 or len(s) > 1500:
        return False
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", s):
        return False
    if " " not in s and not re.search(r"[À-ÿ]", s):
        return False                      # códigos ("not_found", "quota_exceeded") ficam de fora
    if re.match(r"^(https?:|/api/|/[a-z_]+/)", s):
        return False
    return True


def _from_node(node: ast.AST) -> tuple[str | None, bool]:
    """(texto ou padrão, é_padrão)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _norm(node.value), False
    if isinstance(node, ast.JoinedStr):
        parts, n = [], 0
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{%d}" % n)
                n += 1
        pat = _norm("".join(parts))
        if n == 0:
            return pat, False
        static = re.sub(r"\{\d+\}", " ", pat)
        if not re.search(r"[A-Za-zÀ-ÿ]{3}", static) or re.fullmatch(r"\{\d+\}", pat):
            return None, False
        return pat, True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):   # "a" + "b"
        a, pa = _from_node(node.left)
        b, pb = _from_node(node.right)
        if a and b and not pa and not pb:
            return _norm(a + b), False
    return None, False


def extract() -> dict:
    exact: set[str] = set()
    patterns: set[str] = set()

    def add(node):
        txt, is_pat = _from_node(node)
        if not txt:
            return
        if is_pat:
            if _looks_like_text(re.sub(r"\{\d+\}", "x", txt)):
                patterns.add(txt)
        elif _looks_like_text(txt):
            exact.add(txt)

    for top in SCAN:
        for f in sorted((ROOT / top).rglob("*.py")):
            if SKIP_PARTS & set(f.parts):
                continue
            try:
                tree = ast.parse(f.read_text("utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                    if name == "HTTPException":
                        for a in node.args[1:2]:
                            add(a)
                    for kw in node.keywords:
                        if kw.arg in KEYS:
                            add(kw.value)
                elif isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values):
                        if isinstance(k, ast.Constant) and k.value in KEYS:
                            add(v)
    # Dados de interface vindos da API (ex.: nomes, descrições e vantagens dos planos em inglês,
    # base do ucraniano): todas as strings do sub-dicionário indicado.
    for rel, var, sub in DATA_DICTS:
        f = ROOT / rel
        if not f.exists():
            continue
        for node in ast.walk(ast.parse(f.read_text("utf-8"))):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var for t in node.targets) \
                    and isinstance(node.value, ast.Dict):
                for k, v in zip(node.value.keys, node.value.values):
                    if isinstance(k, ast.Constant) and k.value == sub:
                        for c in ast.walk(v):
                            if isinstance(c, ast.Constant) and isinstance(c.value, str) and _looks_like_text(_norm(c.value)):
                                exact.add(_norm(c.value))
    ex = sorted(exact)
    pa = sorted(p for p in patterns if p not in exact)
    version = hashlib.sha1(json.dumps([ex, pa], ensure_ascii=False).encode()).hexdigest()[:12]
    return {"version": version, "generated_from": "backend (routes, engines, core)", "exact": ex, "patterns": pa}


def main() -> None:
    m = extract()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"[i18n-backend] {len(m['exact'])} textos + {len(m['patterns'])} padrões → {out} (v{m['version']})")


if __name__ == "__main__":
    main()
