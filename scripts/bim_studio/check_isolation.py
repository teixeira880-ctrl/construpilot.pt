#!/usr/bin/env python3
"""Verifica que a implementação do BIM Studio não toca na ConstruPilot França.

Regras (falha com código ≠ 0 se alguma for violada):
  1. O repositório é teixeira880-ctrl/construpilot.pt (nunca construpilot.fr / construpilot.fr_1).
  2. Só ficheiros da lista autorizada foram criados/alterados em relação à branch base.
  3. Ficheiros partilhados (server.py, requirements.txt, App.js, navigation.js) só recebem
     linhas acrescentadas relacionadas com o BIM Studio — nenhuma linha removida.
  4. Nenhum .env, configuração Emergent (.emergent/) ou ficheiro de deploy foi alterado.
  5. O código novo não referencia domínios, bases de dados ou variáveis francesas.

Uso: python scripts/bim_studio/check_isolation.py [--base origin/Construpilot]
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALLOWED_NEW_OR_CHANGED = [
    "backend/bim_studio/*", "backend/routes/bim_studio.py", "backend/tests/test_bim/*",
    "frontend/src/pages/BimStudio.jsx", "frontend/src/components/bim/*", "frontend/tests/bim/*",
    "docs/bim_studio/*", "scripts/bim_studio/*", "frontend/jest.bim.config.cjs",
]
# Ficheiros existentes onde só se aceitam linhas acrescentadas com estas palavras
SHARED_ADDITIVE = {
    "backend/server.py": re.compile(r"bim_studio|BIM Studio"),
    "backend/requirements.txt": re.compile(r"^(ifcopenshell|isodate|lark)=="),
    "frontend/src/App.js": re.compile(r"BimStudio|bim-studio"),
    "frontend/src/components/workspace/navigation.js": re.compile(r"bim-studio|BIM Studio|Box\b|bimStudio"),
}
FORBIDDEN = [".env", "*/.env", ".emergent/*", "frontend/.env", "backend/.env"]
FR_PATTERNS = re.compile(r"construpilot\.fr|construpilot\.fr_1|SITE_COUNTRY\s*=\s*['\"]FR", re.I)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/Construpilot")
    base = ap.parse_args().base
    errors: list[str] = []

    remote = git("remote", "get-url", "origin").strip()
    if not re.search(r"teixeira880-ctrl/construpilot\.pt(\.git)?$", remote):
        errors.append(f"Remote inesperado: {remote}")

    changed = set(filter(None, git("diff", "--name-only", base).splitlines()))
    changed |= set(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
    for path in sorted(changed):
        if any(fnmatch.fnmatch(path, p) for p in FORBIDDEN):
            errors.append(f"Ficheiro proibido alterado: {path}")
            continue
        if path in SHARED_ADDITIVE:
            diff = git("diff", "-U0", base, "--", path)
            for line in diff.splitlines():
                if line.startswith(("+++", "---", "@@")):
                    continue
                if line.startswith("-"):
                    errors.append(f"{path}: linha removida/alterada: {line[:120]}")
                elif line.startswith("+") and line[1:].strip() and not SHARED_ADDITIVE[path].search(line[1:]):
                    errors.append(f"{path}: linha acrescentada fora do âmbito BIM: {line[:120]}")
            continue
        if not any(fnmatch.fnmatch(path, p) for p in ALLOWED_NEW_OR_CHANGED):
            errors.append(f"Ficheiro fora do âmbito autorizado: {path}")
            continue
        if path.endswith((".py", ".js", ".jsx")) and path != "scripts/bim_studio/check_isolation.py":
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            if FR_PATTERNS.search(text):
                errors.append(f"{path}: referência à plataforma francesa")

    print(f"Base: {base} | ficheiros alterados/novos: {len(changed)}")
    for p in sorted(changed):
        print("  ·", p)
    if errors:
        print("\nISOLAMENTO VIOLADO:")
        for e in errors:
            print("  ✗", e)
        return 1
    print("\nOK — nenhuma alteração fora do âmbito BIM Studio PT; nada da plataforma francesa foi tocado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
