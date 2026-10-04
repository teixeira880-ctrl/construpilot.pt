#!/usr/bin/env python3
"""Tradutor automático FR→PT-PT para strings hardcoded no frontend.

Fluxo:
  1. Carrega `/app/memory/fr_strings_inventory.json`.
  2. Para cada string FR distinta:
     a. Procura em `pt_auto.json` (match exacto).
     b. Senão, traduz via Claude Opus 5.5 com instrução PT-PT estrita.
     c. Guarda a nova tradução em `pt_auto.json` (append).
  3. Aplica substituições whole-literal nos ficheiros .jsx/.js.

Modo `--dry-run` (default) só reporta. `--apply` escreve.

Preserva: aspas originais, interpolação template literals `${...}` (não traduz
templates com placeholders — fica para revisão manual).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("translate_fr_pt")

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

INVENTORY = Path("/app/memory/fr_strings_inventory.json")
PT_DICT = Path("/app/frontend/src/i18n/pt_auto.json")
FRONTEND_ROOT = Path("/app/frontend/src")

# Padrão PT-BR→PT-PT para auto-correção (importado do i18n_revise_pt)
BR_TO_PT = [
    (re.compile(r"\barquivos?\b"), "ficheiro"),
    (re.compile(r"\bArquivos?\b"), "Ficheiro"),
    (re.compile(r"\btelas?\b"), "ecrã"),
    (re.compile(r"\bTelas?\b"), "Ecrã"),
    (re.compile(r"\busuários?\b"), "utilizador"),
    (re.compile(r"\bUsuários?\b"), "Utilizador"),
    (re.compile(r"\bsalvar\b"), "guardar"),
    (re.compile(r"\bSalvar\b"), "Guardar"),
    (re.compile(r"\bdeletar\b"), "eliminar"),
    (re.compile(r"\bDeletar\b"), "Eliminar"),
    (re.compile(r"\bconectar\b"), "ligar"),
    (re.compile(r"\bConectar\b"), "Ligar"),
    (re.compile(r"\bbaixar\b"), "transferir"),
    (re.compile(r"\bBaixar\b"), "Transferir"),
]


def pt_br_sanitize(s: str) -> str:
    for pat, repl in BR_TO_PT:
        s = pat.sub(repl, s)
    return s


async def translate_claude(fr_batch: list[str]) -> list[str]:
    """Traduz um batch FR→PT-PT em uma única chamada Claude Opus 5.5."""
    if not fr_batch:
        return []
    from engines.ai_providers.router import ai_router

    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(fr_batch))
    prompt = (
        "Traduz do francês para Português Europeu (PT-PT, nunca PT-BR) as "
        "seguintes strings de UI de uma app profissional de construção civil. "
        "Mantém capitalização, pontuação, interpolação (`{var}`, `${var}`) e "
        "contexto técnico (BTP). Nunca uses palavras PT-BR: "
        "`arquivo→ficheiro`, `tela→ecrã`, `usuário→utilizador`, `salvar→guardar`, "
        "`deletar→eliminar`, `conectar→ligar`, `baixar→transferir`.\n\n"
        "Devolve EXCLUSIVAMENTE um array JSON de strings (`[\"...\",\"...\"]`), "
        "mesma ordem, mesmo nº de elementos. Nenhum texto antes/depois.\n\n"
        f"Strings:\n{numbered}"
    )
    r = await ai_router.coach_ask(
        prompt=prompt,
        system="És um tradutor profissional FR→PT-PT especializado em terminologia de construção civil (BTP) para Portugal.",
        history=None, max_tokens=4000, temperature=0.0, enrich_with_web=False,
    )
    txt = r.text.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```\s*$", "", txt)
    try:
        arr = json.loads(txt)
    except Exception:
        start = txt.find("[")
        end = txt.rfind("]")
        arr = json.loads(txt[start:end + 1]) if start != -1 and end != -1 else None
    if not isinstance(arr, list) or len(arr) != len(fr_batch):
        log.warning("Claude devolveu formato inesperado para batch de %d · fallback 1:1", len(fr_batch))
        return fr_batch  # fallback: devolve originais
    return [pt_br_sanitize(str(s)) for s in arr]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Aplicar substituições (default: dry-run)")
    ap.add_argument("--limit", type=int, default=0, help="Limitar nº de strings a traduzir (0 = todas)")
    args = ap.parse_args()

    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    rows = inventory["rows"]
    pt_dict = json.loads(PT_DICT.read_text(encoding="utf-8"))

    # Deduplicar strings
    unique_fr: dict[str, list[dict]] = {}
    for r in rows:
        unique_fr.setdefault(r["fr"], []).append(r)
    unique_list = list(unique_fr.keys())
    if args.limit:
        unique_list = unique_list[: args.limit]

    log.info("Strings FR únicas: %d (ocorrências: %d em %d ficheiros)",
             len(unique_list), len(rows), len(inventory["per_file"]))

    # Classificar: já no pt_auto.json / precisam Claude
    via_dict: dict[str, str] = {}
    via_claude_needed: list[str] = []
    for fr in unique_list:
        if fr in pt_dict and pt_dict[fr] and pt_dict[fr] != fr:
            via_dict[fr] = pt_dict[fr]
        else:
            via_claude_needed.append(fr)

    log.info("  · via pt_auto.json: %d · via Claude: %d", len(via_dict), len(via_claude_needed))

    # Traduzir em batches de 25 via Claude
    via_claude: dict[str, str] = {}
    BATCH = 25
    for i in range(0, len(via_claude_needed), BATCH):
        batch = via_claude_needed[i:i + BATCH]
        log.info("  Claude batch %d/%d (%d strings)…", i // BATCH + 1,
                 (len(via_claude_needed) + BATCH - 1) // BATCH, len(batch))
        try:
            translated = await translate_claude(batch)
        except Exception as e:  # noqa: BLE001
            log.error("  batch falhou: %s · a saltar", e)
            continue
        for fr, pt in zip(batch, translated):
            if pt and pt.strip() and pt != fr:
                via_claude[fr] = pt
        # Rate-limit anti-stress
        await asyncio.sleep(0.3)

    # Atualizar pt_auto.json
    pt_dict.update(via_claude)
    if args.apply:
        PT_DICT.write_text(json.dumps(pt_dict, ensure_ascii=False, indent=0), encoding="utf-8")
        log.info("✓ pt_auto.json actualizado · %d chaves novas", len(via_claude))

    # Mapa final FR→PT (sem casos que falharam)
    translations = {**via_dict, **via_claude}

    # Aplicar substituições whole-literal
    files_touched = set()
    total_subs = 0
    skipped = 0
    for fname, hits in inventory["per_file"].items():
        fpath = FRONTEND_ROOT / fname
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        new_text = text
        file_changes = 0
        # Encontrar strings deste ficheiro
        for row in rows:
            if row["file"] != fname:
                continue
            fr = row["fr"]
            pt = translations.get(fr)
            if not pt:
                skipped += 1
                continue
            # Substituição whole-literal: só se envolvida em aspas simples/duplas/backticks
            for quote in ('"', "'", "`"):
                src = f"{quote}{fr}{quote}"
                dst = f"{quote}{pt}{quote}"
                if src in new_text:
                    new_text = new_text.replace(src, dst)
                    file_changes += new_text.count(dst) - text.count(dst)
        if file_changes:
            total_subs += file_changes
            files_touched.add(fname)
            if args.apply:
                fpath.write_text(new_text, encoding="utf-8")

    log.info("")
    log.info("══════ RESUMO ══════")
    log.info("Ficheiros tocados   : %d", len(files_touched))
    log.info("Substituições       : %d", total_subs)
    log.info("Strings sem tradução: %d", skipped)
    log.info("Dicionário (hits)   : %d", len(via_dict))
    log.info("Claude (novas)      : %d", len(via_claude))
    if not args.apply:
        log.info("MODO DRY-RUN · usa `--apply` para escrever.")


if __name__ == "__main__":
    asyncio.run(main())
