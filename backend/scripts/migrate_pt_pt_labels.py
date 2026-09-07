"""One-shot migration — traduz nomes FR → PT-PT em docs Mongo existentes.

Executar UMA VEZ após deploy do backend com strings traduzidas:
    python -m scripts.migrate_pt_pt_labels

Collections atualizadas:
- catalog_items       (name, label, description)
- quotes.lots         (lot, lines[].designation, lines[].category)
- plans_takeoff       (lots[].lot, lots[].lines[].designation)
- pc_studies          (lots[].lot, lots[].lines[].designation, order_items[].name)
- price_catalog       (name)
- default_materials   (name)
"""
import asyncio
import os
import re
import sys
from motor.motor_asyncio import AsyncIOMotorClient

# Adiciona o backend ao PYTHONPATH quando executado standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Glossário determinístico FR → PT-PT (ordem importa — as maiores primeiro para evitar
# substituições parciais indesejadas).
GLOSSARY = [
    # Rubricas / lots
    ("Gros œuvre — béton", "Estrutura — betão"),
    ("gros œuvre — béton", "estrutura — betão"),
    ("gros œuvre béton", "estrutura betão"),
    ("Gros œuvre", "Estrutura"),
    ("gros œuvre", "estrutura"),
    ("Depuis analyse plan", "A partir da análise da planta"),
    ("Installation de chantier & engins", "Instalação de estaleiro e equipamentos"),
    ("Installation de chantier", "Instalação de estaleiro"),
    ("Terrassement complet", "Movimento de terras completo"),
    ("Terrassement", "Movimento de terras"),
    ("Fondations", "Fundações"),
    ("Planchers / Dalles", "Lajes / Pavimentos"),
    ("Élévations — murs brique isobrique 20 cm", "Elevação — paredes tijolo isobrique 20 cm"),
    ("Escalier béton", "Escada de betão"),
    ("Charpente & Couverture", "Estrutura e Cobertura"),
    ("Menuiseries extérieures", "Caixilharia exterior"),
    ("Structure béton (métré plan)", "Estrutura betão (medição da planta)"),
    ("Réservations & huisseries", "Aberturas e caixilharia"),
    ("Installation & sécurité", "Estaleiro e segurança"),
    # Line designations
    ("Huisseries — pré-cadres / réservations de baies", "Caixilharia — pré-aros / aberturas de vãos"),
    ("Aciers HA (ferraillage — env.", "Aço nervurado (armadura — aprox."),
    ("Aciers HA (fer à béton armé — env.", "Aço nervurado (varões p/ betão armado — aprox."),
    ("Aciers HA façonnés", "Aço HA moldado"),
    ("Aciers HA", "Aço nervurado"),
    ("Main d'œuvre béton (coffrage, coulage, ferraillage)", "Mão de obra betão (cofragem, betonagem, armadura)"),
    ("Béton — semelles / fondations", "Betão — sapatas / fundações"),
    ("Béton de propreté", "Betão de limpeza"),
    ("Béton — poteaux", "Betão — pilares"),
    ("Béton — poutres / linteaux", "Betão — vigas / lintéis"),
    ("Béton — dalles / planchers", "Betão — lajes / pavimentos"),
    ("Béton — voiles / murs porteurs", "Betão — paredes resistentes / muros"),
    ("Béton coulé (poteaux + poutres + dalles + voiles + semelles)",
     "Betão vazado (pilares + vigas + lajes + paredes + sapatas)"),
    ("Béton coulé", "Betão vazado"),
    ("Béton prêt à l'emploi C25/30 — semelles", "Betão pronto C25/30 — sapatas"),
    ("Béton prêt à l'emploi C25/30 — dalle / plancher", "Betão pronto C25/30 — laje / pavimento"),
    ("Béton C25/30 — chaînages & raidisseurs", "Betão C25/30 — cintas e travamentos"),
    ("Béton C25/30 — escalier", "Betão C25/30 — escada"),
    ("Béton", "Betão"),
    ("béton", "betão"),
    ("Plancher béton — dalle pleine BA", "Laje betão — laje maciça BA"),
    ("Plancher béton", "Laje betão"),
    ("Plancher / sol (surface au sol)", "Pavimento / solo (área de pavimento)"),
    ("Plancher d'étage complet — poutrelles-hourdis + table de compression",
     "Laje de piso completa — vigotas-abobadilhas + capa de compressão"),
    ("Plancher poutrelles-hourdis — étage (fourniture complète)",
     "Laje vigotas-abobadilhas — piso (fornecimento completo)"),
    ("Poutres / linteaux", "Vigas / lintéis"),
    ("Poutres béton — béton C25/30", "Vigas de betão — betão C25/30"),
    ("Poteaux béton — béton C25/30", "Pilares de betão — betão C25/30"),
    ("Poteaux béton", "Pilares de betão"),
    ("Voiles / murs béton — béton C25/30", "Paredes resistentes / muros de betão — betão C25/30"),
    ("Coffrage voiles (2 faces)", "Cofragem paredes (2 faces)"),
    ("Coffrage poutres", "Cofragem vigas"),
    ("Coffrage + étaiement dalle", "Cofragem + escoramento laje"),
    ("Coffrage escaliers", "Cofragem escadas"),
    ("Coffrage de rives de dalle", "Cofragem de bordos de laje"),
    ("Aciers voiles", "Aço paredes"),
    ("Aciers poutres", "Aço vigas"),
    ("Aciers poteaux", "Aço pilares"),
    ("Aciers dalle", "Aço laje"),
    ("Aciers escaliers", "Aço escadas"),
    ("Aciers escalier", "Aço escada"),
    ("Aciers semelles", "Aço sapatas"),
    ("Aciers chaînages", "Aço cintas"),
    ("Aciers", "Aço"),
    ("Dalle / plancher béton", "Laje / pavimento de betão"),
    ("Dallage RDC — dalle BA", "Laje térrea — laje BA"),
    ("Escaliers béton — paillasses & marches", "Escadas de betão — lajes inclinadas e degraus"),
    ("Escalier béton armé coulé en place", "Escada em betão armado betonada no local"),
    ("Escalier béton armé", "Escada em betão armado"),
    ("Escalier béton", "Escada betão"),
    ("Linteaux béton armé", "Lintéis em betão armado"),
    ("Linteaux BA sur ouvertures", "Lintéis BA sobre vãos"),
    ("Linteaux / coffrage BA 20 × 20", "Lintéis / cofragem BA 20 × 20"),
    ("Linteaux", "Lintéis"),
    ("Réservations (traçage + coffrage)", "Aberturas (marcação + cofragem)"),
    ("Réservations", "Aberturas"),
    ("Huisseries", "Caixilharia"),
    ("Semelles filantes BA 60 × 30 cm", "Sapatas contínuas BA 60 × 30 cm"),
    ("Semelles filantes", "Sapatas contínuas"),
    ("Semelles / fondations", "Sapatas / fundações"),
    ("Semelles", "Sapatas"),
    ("Mise en œuvre fondations — implantation, coffrage, réglage & coulage",
     "Execução de fundações — implantação, cofragem, nivelamento e betonagem"),
    ("Mise en œuvre fondations — implantation, coffrage, coulage",
     "Execução de fundações — implantação, cofragem, betonagem"),
    ("Bandes noyées / poutres noyées", "Vigas embutidas / faixas embebidas"),
    ("Murs porteurs (maçonnerie)", "Paredes resistentes (alvenaria)"),
    ("Murs — enduit/peinture", "Paredes — reboco/pintura"),
    ("Murs brique isobrique", "Paredes tijolo isobrique"),
    ("Murs en brique isobrique", "Paredes em tijolo isobrique"),
    ("Cloisons", "Divisórias"),
    ("Fournitures et pose — Portes", "Fornecimento e assentamento — Portas"),
    ("Fournitures et pose — Fenêtres", "Fornecimento e assentamento — Janelas"),
    ("Fournitures et pose — Baies vitrées", "Fornecimento e assentamento — Janelas de sacada"),
    ("Chaînages horizontaux + raidisseurs verticaux BA 20 × 20",
     "Cintas horizontais + travamentos verticais BA 20 × 20"),
    ("Chaînages CH + CV (BA 20 × 20)", "Cintas + travamentos verticais (BA 20 × 20)"),
    ("Chaînages", "Cintas"),
    ("Treillis soudé ST25C + chapeaux", "Rede electrossoldada ST25C + reforços"),
    ("Treillis soudé ST25C", "Rede electrossoldada ST25C"),
    ("Charpente traditionnelle — bois massif assemblé", "Estrutura tradicional — madeira maciça montada"),
    ("Charpente traditionnelle", "Estrutura tradicional"),
    ("Couverture tuiles — tuiles, écran sous-toiture, liteaux & faîtage",
     "Cobertura em telha — telhas, sub-telha, ripas e cumeeira"),
    ("Couverture tuiles — tuiles, écran, liteaux & faîtage",
     "Cobertura em telha — telhas, sub-telha, ripas e cumeeira"),
    ("Couverture tuiles", "Cobertura em telha"),
    ("Tuiles + écran sous-toiture + liteaux (fourniture)", "Telhas + sub-telha + ripas (fornecimento)"),
    ("Menuiseries extérieures — fenêtres & portes-fenêtres posées",
     "Caixilharia exterior — janelas e portas-janela assentes"),
    ("Menuiseries extérieures — fenêtres (fourniture)", "Caixilharia exterior — janelas (fornecimento)"),
    ("Menuiseries", "Caixilharia"),
    ("Engins & machines — grue/manuscopique, bétonnière, outillage",
     "Equipamentos e máquinas — grua/manipulador telescópico, betoneira, ferramentas"),
    ("Installation de chantier — base vie, clôture, benne gravats",
     "Instalação de estaleiro — base de vida, vedação, contentor de entulho"),
    ("Installation de chantier — base vie, clôture, benne",
     "Instalação de estaleiro — base de vida, vedação, contentor"),
    ("Échafaudage périphérique — location, montage & démontage",
     "Andaimes perimetrais — aluguer, montagem e desmontagem"),
    ("Échafaudage périphérique — location & montage", "Andaimes perimetrais — aluguer e montagem"),
    ("Protection collective & sécurité — garde-corps périphériques, filets, signalisation & PPSPS",
     "Proteção coletiva e segurança — guarda-corpos perimetrais, redes, sinalização e PSS"),
    ("Protection collective & sécurité — garde-corps, filets, signalisation & PPSPS",
     "Proteção coletiva e segurança — guarda-corpos, redes, sinalização e PSS"),
    ("Protection collective & sécurité — garde-corps, filets, PPSPS",
     "Proteção coletiva e segurança — guarda-corpos, redes, PSS"),
    # Materials
    ("Cales béton", "Calços de betão"),
    ("Parpaing", "Bloco de betão"),
    ("Fil à ligaturer", "Arame de amarrar"),
    ("Fenêtre PVC double vitrage", "Janela PVC vidro duplo"),
    ("Carrelage grès cérame", "Grés porcelânico"),
    ("Parquet flottant", "Soalho flutuante"),
    ("Peinture acrylique", "Tinta acrílica"),
    ("Câble électrique", "Cabo elétrico"),
    ("Point électrique (appareillage)", "Ponto elétrico (aparelhagem)"),
    ("Tube PER / cuivre", "Tubo PER / cobre"),
    ("Bouche VMC", "Grelha VMC"),
    ("Enduit façade", "Reboco de fachada"),
    ("Enduit / bande", "Reboco / fita"),
    ("Écran sous-toiture", "Sub-telha"),
    ("Plaque de plâtre BA13", "Placa de gesso cartonado BA13"),
    ("Rail / montant ossature", "Perfil / montante estrutura"),
    ("Laine de verre", "Lã de vidro"),
    ("Mortier / colle", "Argamassa / cola"),
    ("Armature semelle filante", "Armadura sapata contínua"),
    ("Acier HA (armatures)", "Aço HA (armaduras)"),
    ("Briques isobrique", "Tijolos isobrique"),
    ("Tuile", "Telha"),
    ("Liteau", "Ripa"),
    ("Chevron", "Vigota"),
    # Units
    ("forfait", "vg"),
]

def _translate(s: str) -> str:
    """Aplica o glossário FR→PT sequencialmente."""
    if not isinstance(s, str):
        return s
    out = s
    for fr, pt in GLOSSARY:
        if fr in out:
            out = out.replace(fr, pt)
    return out


async def _update_collection(db, coll_name: str, field_paths: list[str]) -> dict:
    """Percorre todos os docs; se algum field_path contiver strings FR, atualiza in-place.
    field_paths: notação com pontos (ex: 'lots.lines.designation')."""
    stats = {"scanned": 0, "updated": 0}
    coll = db[coll_name]
    async for doc in coll.find({}):
        stats["scanned"] += 1
        original = _deep_snapshot(doc)
        for path in field_paths:
            _translate_path(doc, path.split("."))
        if _deep_snapshot(doc) != original:
            await coll.replace_one({"_id": doc["_id"]}, doc)
            stats["updated"] += 1
    return stats


def _deep_snapshot(d):
    """Snapshot serializável (str repr) para deteção de alterações."""
    return repr(d)


def _translate_path(obj, keys: list[str]):
    """Percorre dicts/listas a aplicar _translate nos campos-alvo."""
    if not keys or obj is None:
        return
    k = keys[0]
    rest = keys[1:]
    if isinstance(obj, list):
        for item in obj:
            _translate_path(item, keys)
        return
    if not isinstance(obj, dict):
        return
    if not rest:
        # último segmento — aplicar tradução
        if k in obj and isinstance(obj[k], str):
            obj[k] = _translate(obj[k])
        return
    if k in obj:
        _translate_path(obj[k], rest)


async def main():
    # Carregar .env se presente (execução standalone)
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        pass
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME") or "construpilot"
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    plan = [
        ("catalog_items",  ["name", "label", "description", "category"]),
        ("library_items",  ["name", "label", "description", "category", "designation"]),
        ("price_catalog",  ["name", "designation", "label", "category"]),
        ("quotes",         ["lots.lot", "lots.lines.designation", "lots.lines.category",
                            "lines.designation", "lines.category"]),
        ("plans_takeoff",  ["lots.lot", "lots.lines.designation", "lots.lines.category"]),
        ("plans",          ["takeoff.lots.lot", "takeoff.lots.lines.designation",
                            "takeoff.lots.lines.category",
                            "ai_analysis.lots.lot", "ai_analysis.lots.lines.designation"]),
        ("pc_studies",     ["lots.lot", "lots.lines.designation", "order_items.name",
                            "levels_breakdown.name"]),
        ("default_materials", ["name"]),
    ]
    print(f"[migrate_pt_pt_labels] DB={db_name} — glossary={len(GLOSSARY)} entries")
    for coll_name, fields in plan:
        try:
            stats = await _update_collection(db, coll_name, fields)
            print(f"  · {coll_name:20s}  scanned={stats['scanned']:6d}  updated={stats['updated']:6d}")
        except Exception as e:
            print(f"  ! {coll_name}: {e}")
    client.close()
    print("[migrate_pt_pt_labels] done.")


if __name__ == "__main__":
    asyncio.run(main())
