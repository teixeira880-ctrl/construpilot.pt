"""Instruções do medidor (23/11/2026): o modelo ainda acredita que «o motor de volumes não aceita doc_…» e gasta
chamadas a «importar» plantas (extract_autodesk_data, leituras) antes de medir. A ponte doc_→plan_ já faz isso sozinha:
diz-se-lhe explicitamente. Âncora = fim da METRE_INSTRUCTIONS (frase do allow_vision, presente desde a base d8a)."""
import sys

P = "backend/engines/metre/tools.py"
s = open(P, encoding="utf-8").read()
if "NUNCA chames extract_autodesk_data" in s:
    print("já aplicado", P); sys.exit(0)
anc = 'allow_vision=true com o acordo do utilizador (ou se os cortes já tiverem sido lidos)."'
if s.count(anc) != 1:
    print(f"ERRO {P}: âncora final da METRE_INSTRUCTIONS encontrada {s.count(anc)}× (esperado 1)")
    for i, l in enumerate(s.splitlines(), 1):
        if "allow_vision" in l:
            print(f"   linha {i}: {l.strip()[:150]}")
    sys.exit(1)
novo = ('allow_vision=true com o acordo do utilizador (ou se os cortes já tiverem sido lidos).\\n'
        'Identificadores: TODAS as ferramentas de planta aceitam também o doc_… de um DWG/DXF anexado — a plataforma '
        'importa-o automaticamente como planta, incluindo no lower_dxf_plan_id. NUNCA chames extract_autodesk_data, '
        'read_document nem nenhuma leitura «para importar» ou «converter» uma planta: chama diretamente a ferramenta de '
        'medição com o doc_…/plan_… que o inventário deu. Se não indicares o piso inferior, a plataforma escolhe-o sozinha '
        'pelo nome do ficheiro (fondations → R-1/PH-1/SS → RDC → R+1…)."')
s = s.replace(anc, novo, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
