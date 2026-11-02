"""Lote 46 PT — dossier demo « Moradia Ferreira » na conta demo Pro do .pt.

Uso: python3 lots/l46/apply_l46.py /app /app/lots/l46
Copia os ficheiros de lots/l46/files/ e aplica 3 patches por âncora em
backend/core/websummit_seed_pt.py. Para (exit 1) se uma âncora faltar.
"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
lot = pathlib.Path(sys.argv[2])

# 1) Ficheiros novos
files = lot / "files"
n = 0
for src in sorted(files.rglob("*")):
    if src.is_file():
        dst = root / src.relative_to(files)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
print(f"copiados: {n}")

# 2) Patches em websummit_seed_pt.py
p = root / "backend" / "core" / "websummit_seed_pt.py"
s = p.read_text(encoding="utf-8")
if "apply_demo_dossier_pt" in s:
    print("websummit_seed_pt.py já tem o Lote 46 — nada a fazer")
    print("L46 OK")
    sys.exit(0)

PATCHES = [
    (  # arranque: dossier demo na conta Pro (não reescreve o existente)
        "    # Showcase BET-core: documentos demo + branding fictício nas contas demo.\n"
        "    # Idempotente, não duplica, preserva dados pré-existentes.\n",
        "    # Lote 46: dossier demo « Moradia Ferreira » (planta, levantamento, orçamento, faturas) na conta Pro.\n"
        "    if cfg[\"pro\"][\"password\"]:\n"
        "        try:\n"
        "            from core.demo_dossier_pt import apply_demo_dossier_pt\n"
        "            _pro = await db.users.find_one({\"email\": cfg[\"pro\"][\"email\"], \"is_demo\": True}, {\"user_id\": 1})\n"
        "            summary[\"dossier\"] = await apply_demo_dossier_pt(db, (_pro or {}).get(\"user_id\"), DEMO_SOURCE)\n"
        "        except Exception as exc:  # noqa: BLE001\n"
        "            logger.warning(\"websummit demo seed: dossier step failed (%s)\", exc)\n"
        "            summary[\"dossier\"] = f\"error: {exc}\"\n"
        "\n"
        "    # Showcase BET-core: documentos demo + branding fictício nas contas demo.\n"
        "    # Idempotente, não duplica, preserva dados pré-existentes.\n",
    ),
    (  # reset diário: limpa também documentos/plantas/clientes/obras criados durante a demo
        "            \"notifications\", \"email_logs\", \"stripe_customer_actions\",\n"
        "        ]\n",
        "            \"notifications\", \"email_logs\", \"stripe_customer_actions\",\n"
        "            \"pro_documents\", \"plans_takeoff\", \"clients\", \"chantiers\",\n"
        "        ]\n",
    ),
    (  # reset diário: repõe o dossier no estado original
        "    # Re-aplicar documentos BET-core demo + branding fictício. Idempotente.\n",
        "    # Lote 46: repõe o dossier demo « Moradia Ferreira » da conta Pro.\n"
        "    try:\n"
        "        from core.demo_dossier_pt import apply_demo_dossier_pt\n"
        "        reset_summary[\"dossier\"] = await apply_demo_dossier_pt(\n"
        "            db, reset_summary.get(\"pro_user_id\"), DEMO_SOURCE, restore=True)\n"
        "    except Exception as exc:  # noqa: BLE001\n"
        "        logger.warning(\"websummit demo reset: dossier step failed (%s)\", exc)\n"
        "        reset_summary[\"dossier\"] = f\"error: {exc}\"\n"
        "\n"
        "    # Re-aplicar documentos BET-core demo + branding fictício. Idempotente.\n",
    ),
]
for i, (old, new) in enumerate(PATCHES, 1):
    c = s.count(old)
    if c != 1:
        print(f"ÂNCORA {i} encontrada {c} vezes — PARAR, nada foi escrito em websummit_seed_pt.py")
        sys.exit(1)
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8")
print("patches: 3/3")
print("L46 OK")
