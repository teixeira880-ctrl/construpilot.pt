#!/usr/bin/env python3
"""Translate engines/diy.py FR->PT-PT using Emergent LLM (Claude Sonnet 4.5)."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

SRC = Path("/app/backend/engines/diy.py")

SYSTEM = """You are a precise technical translator from French to European Portuguese (PT-PT) for construction/DIY Python code.

STRICT RULES:
1. Preserve Python syntax exactly (quotes, braces, commas, indentation).
2. Translate ONLY string VALUES inside dict fields: safety, title, text, tips, mistakes, tools, name, duration.
3. NEVER modify dict KEYS or Python identifiers, imports, function names.
4. NEVER modify values of "key" or "lot" or "calculator" or "structure" (they are internal identifiers: plafond_placo, cloison, plafond, etc.).
5. Return ONLY the translated Python file. No markdown fences, no explanations.

PT-PT GLOSSARY (strict):
- placo/plaques de plâtre -> Pladur
- carrelage -> azulejo (piso: pavimento cerâmico)
- béton -> betão | chape -> betonilha
- devis -> orçamento | chantier -> obra
- mètre -> metro | niveau laser -> nível laser | visseuse -> aparafusadora
- suspente -> suspensão | fourrure -> perfil
- pare-vapeur -> barreira pára-vapor
- lit d'isolant -> camada de isolamento | pont thermique -> ponte térmica
- cordeau -> cordão marcador
- enduit -> massa | poncer -> lixar | girafe -> girafa (lixadora)
- sous-couche -> primário | rechampir -> recortar
- manchon -> rolo | primaire d'accrochage -> primário de aderência
- ragréage -> nivelamento | calepiner -> planear disposição
- encoller -> aplicar cola | croisillons -> cruzetas
- joint (matéria) -> junta | joint souple -> junta flexível
- pistolet à mastic -> pistola de silicone
- combles -> sótão | solives -> vigas de madeira
- salle d'eau/salle de bain -> casa de banho
- receveur -> base de duche | meuble vasque -> móvel de lavatório
- cloison -> tabique | PER/multicouche -> PEX/multicamada
- nourrice -> distribuidor | vanne d'arrêt -> torneira de corte
- sertir -> prensar | VMC/Consuel/NF C 15-100 -> keep as-is
- électricien -> eletricista | burineur -> martelo demolidor
- cloueur -> pistola de pregos | échafaudage roulant -> andaime móvel
- escabeau -> escadote | lunettes -> óculos de proteção
- genouillères -> joelheiras | cheville -> bucha | vis -> parafusos
- bâche -> lona | plinthes -> rodapés | éponge -> esponja | seau -> balde
- humidimètre -> higrómetro | hydrofuge -> hidrófugo
- fissure -> fissura | reboucher -> tapar
- masquage -> proteção | adhésif -> fita adesiva
- rouleau -> rolo | perche -> extensor | bac -> tabuleiro
- crayon de chantier -> lápis de obra
- couteau (ferramenta de massa) -> espátula
- couteau à laine -> faca de lã mineral
- agrafeuse -> agrafador | pince -> alicate
- pince à sertir -> alicate de prensar | clé à molette -> chave inglesa
- carrelette -> cortador manual de cerâmica
- scie sauteuse -> serra tico-tico
- maillet caoutchouc -> martelo de borracha
- peigne -> pente (de aplicar cola)
- règle de 2 m -> régua de 2 m | équerre -> esquadro
- cales -> calços | lève-plaque -> elevador de placas
- Aérer -> Ventilar | Étanchéité -> Estanqueidade
- SPEC -> SPEC (Sistema de Proteção à Água sob Azulejo)
- Duração: "h" mantém, "à deux" -> "a dois"

Return ONLY the fully translated Python file. Start with the docstring, end with the final closing brace of build_guide."""


async def main():
    code = SRC.read_text(encoding="utf-8")
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        print("EMERGENT_LLM_KEY missing", file=sys.stderr)
        sys.exit(1)

    chat = LlmChat(
        api_key=key,
        session_id="diy-translate-v2",
        system_message=SYSTEM,
    ).with_model("openai", "gpt-4o")

    user_text = "Translate the following Python file from FR to PT-PT following the rules above.\n\n" + code
    msg = UserMessage(text=user_text)
    resp = await chat.send_message(msg)

    text = resp.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    if "TASKS = [" not in text or "TASKS_BY_KEY" not in text or "def build_guide" not in text:
        print("TRANSLATION SANITY FAILED", file=sys.stderr)
        print(text[:1000], file=sys.stderr)
        sys.exit(2)

    SRC.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
    print(f"OK: wrote {SRC} ({len(text)} chars)")


if __name__ == "__main__":
    asyncio.run(main())
