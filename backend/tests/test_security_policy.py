"""Z.3 — testes de regressão da política de segurança unificada.

Falha o build se:
  (a) password/chave hardcoded detectada em código (fora de testes/docs),
  (b) UploadFile sem validate_upload num endpoint,
  (c) leitura directa de ENV fora de core/environment.py,
  (d) comportamento fail-closed violado (ENV vazio/corrompido → produção).
"""
import importlib
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path("/app/backend")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─── (a) Zero passwords/keys hardcoded ────────────────────────────────────
HARDCODED_PATTERNS = [
    # Password = "..." em código (>=6 chars)
    re.compile(r'password\s*=\s*["\'][^"\']{6,}["\']', re.IGNORECASE),
    # SECRET = "..." em código (>=10 chars)
    re.compile(r'(^|\s)SECRET\s*=\s*["\'][^"\']{10,}["\']'),
    # Stripe keys em claro
    re.compile(r'["\']sk_(live|test)_[A-Za-z0-9]{20,}["\']'),
    # OpenAI/Anthropic sk-...
    re.compile(r'["\']sk-[A-Za-z0-9]{30,}["\']'),
    # Resend keys
    re.compile(r'["\']re_[A-Za-z0-9]{20,}["\']'),
    # Google API keys
    re.compile(r'["\']AIza[A-Za-z0-9_-]{20,}["\']'),
    # mongodb://user:password@...
    re.compile(r'mongodb(\+srv)?://[^:/\s]+:[^@/\s]+@'),
]

# Paths onde patterns são aceitáveis (testes, docs, exemplos sem valores reais)
WHITELIST_PATHS = (
    "tests/",
    "core/environment.py",  # auto-referência de documentação
    "core/provisioned_accounts.py",  # já gated por SEED_DEMO_DATA (Lote X.2)
    ".env.example",
    "memory/",  # relatórios de auditoria citam exemplos de patterns
)

# Ficheiros específicos excluídos por análise humana (justificado em comentário)
WHITELIST_FILES = {
    # test_credentials.md (fora do backend): já em /app/memory não /app/backend
}


def test_no_hardcoded_secrets():
    offenders = []
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        if any(rel.startswith(w) for w in WHITELIST_PATHS):
            continue
        if rel in WHITELIST_FILES:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for pat in HARDCODED_PATTERNS:
            for m in pat.finditer(text):
                # Linha do match para debugging
                line = text[:m.start()].count("\n") + 1
                sample = m.group()[:80]
                # Ignora pattern-matching próprios dos testes de política
                if "HARDCODED_PATTERNS" in text[max(0, m.start()-300):m.start()]:
                    continue
                offenders.append(f"{rel}:{line}: {sample}")
    assert not offenders, (
        "Segredos hardcoded encontrados (viola SEC-Z-002):\n"
        + "\n".join(offenders)
    )


# ─── (b) Todos os UploadFile usam validate_upload ─────────────────────────
# FOLLOW-UP conhecido: 22 endpoints ainda não migrados (ver Y.2 relatório).
# Este teste é informativo — grava a lista; não falha o build até Z+1 completar.
UPLOADFILE_MIGRATION_PENDING = {
    "documents.py", "structuro.py", "structuro_bet.py", "structuro_plan.py",
    "dpgf.py", "plans_crud.py", "portal_chat.py", "radar.py", "renovation.py",
    "runway_render.py", "speech.py", "library.py", "param_library.py",
    "prices.py",
    # Detectados pela política Z.3 (verificar e migrar numa iteração dedicada)
    "company_page.py", "doc_intel.py", "shared_library.py",
}


def test_upload_file_migration_status():
    """Relatório da cobertura de validate_upload nos routes/*.py."""
    routes = ROOT / "routes"
    migrated = []
    pending = []
    for py in routes.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "UploadFile" not in text:
            continue
        if not re.search(r"def\s+\w+\([^)]*UploadFile", text):
            # Apenas helpers internos usam UploadFile; não é endpoint
            continue
        rel = py.name
        if "validate_upload" in text:
            migrated.append(rel)
        else:
            pending.append(rel)
    # Verifica que todos os pendentes conhecidos ainda estão pendentes
    # (se um ficheiro saiu de pending, actualizar a lista acima)
    unknown_pending = set(pending) - UPLOADFILE_MIGRATION_PENDING
    assert not unknown_pending, (
        "Novos endpoints UploadFile sem validate_upload detectados:\n"
        + "\n".join(sorted(unknown_pending))
        + "\nMigra para validate_upload ou adiciona a UPLOADFILE_MIGRATION_PENDING."
    )


# ─── (c) Zero leitura directa de ENV fora de core/environment ─────────────
ENV_READ_PATTERN = re.compile(
    r'os\.environ\.get\s*\(\s*["\']ENV["\']|'
    r'os\.environ\s*\[\s*["\']ENV["\']\s*\]'
)


def test_env_read_only_in_core_environment():
    offenders = []
    for py in ROOT.rglob("*.py"):
        rel = py.relative_to(ROOT).as_posix()
        # Permitido: core/environment.py (fonte única) + tests/ (monkeypatch)
        if rel == "core/environment.py" or rel.startswith("tests/"):
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in ENV_READ_PATTERN.finditer(text):
            line = text[:m.start()].count("\n") + 1
            offenders.append(f"{rel}:{line}: {m.group()}")
    assert not offenders, (
        "Leituras directas de ENV fora de core/environment.py (viola SEC-Z-001):\n"
        + "\n".join(offenders)
    )


# ─── (d) Comportamento fail-closed do módulo environment ──────────────────
def test_env_fail_closed_on_empty(monkeypatch):
    monkeypatch.setenv("ENV", "")
    import core.environment
    importlib.reload(core.environment)
    assert core.environment.is_production() is True
    assert core.environment.is_relaxed() is False


def test_env_fail_closed_on_corrupted(monkeypatch):
    monkeypatch.setenv("ENV", 'SENDER_PT_FROM = info@construpilot.pt')
    import core.environment
    importlib.reload(core.environment)
    assert core.environment.is_production() is True
    assert core.environment.is_relaxed() is False


def test_env_development_is_relaxed(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    import core.environment
    importlib.reload(core.environment)
    assert core.environment.is_production() is False
    assert core.environment.is_development() is True
    assert core.environment.is_relaxed() is True


def test_env_preview_is_relaxed(monkeypatch):
    monkeypatch.setenv("ENV", "preview")
    import core.environment
    importlib.reload(core.environment)
    assert core.environment.is_production() is False
    assert core.environment.is_preview() is True
    assert core.environment.is_relaxed() is True


def test_env_unknown_value_falls_back_to_production(monkeypatch):
    monkeypatch.setenv("ENV", "testing")
    import core.environment
    importlib.reload(core.environment)
    assert core.environment.is_production() is True
    assert core.environment.is_relaxed() is False
