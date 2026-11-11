"""Dados fictícios da empresa de demonstração « Teste Websummit ».

Nenhum dado real: nomes, moradas, números fiscais e contactos são inventados para a demo.
Os e-mails dos colaboradores usam o subdomínio inexistente `tws.construpilot.pt`
(nenhuma mensagem chega a uma caixa real).
"""
from __future__ import annotations

COMPANY = {
    "name": "Teste Websummit",
    "legal_name": "Teste Websummit, Lda.",
    "owner_email": "teste.websummit@construpilot.pt",
    "owner_name": "Direção Teste Websummit",
    "slug": "teste-websummit",
    "accent": "#1F6B4F",
    "copper": "#B8733A",
    "hq": {"address": "Avenida da Liberdade, 110", "postal": "1250-146", "city": "Lisboa", "country": "PT"},
    "branches": [
        {"country": "PT", "label": "Portugal — Sede", "entity": "Teste Websummit, Lda.",
         "address": "Avenida da Liberdade, 110, 1250-146 Lisboa", "phone": "+351 210 000 110"},
        {"country": "FR", "label": "França — Filial", "entity": "Teste Websummit France SAS",
         "address": "18, rue de la Paix, 75002 Paris", "phone": "+33 1 00 00 01 18"},
        {"country": "GB", "label": "Reino Unido — Filial", "entity": "Teste Websummit UK Ltd",
         "address": "41 Fenchurch Street, London EC3M 3BU", "phone": "+44 20 0000 0041"},
        {"country": "US", "label": "Estados Unidos — Filial", "entity": "Teste Websummit USA Inc.",
         "address": "220 Hudson Street, New York, NY 10013", "phone": "+1 212 000 0220"},
    ],
}

EMAIL_DOMAIN = "tws.construpilot.pt"

# ------------------------------------------------------------------ equipa
DIRECTORS = [
    ("Rui Carvalho", "PT", "Diretor de obra — Lisboa"),
    ("Sofia Martins", "PT", "Diretora de obra — Porto"),
    ("Julien Moreau", "FR", "Directeur de travaux — France"),
    ("James Whitaker", "GB", "Construction Manager — United Kingdom"),
    ("Michael Reyes", "US", "Construction Manager — United States"),
]
ARCHITECT = ("Inês Duarte", "PT", "Arquiteta coordenadora")
ENGINEER = ("Pedro Almeida", "PT", "Engenheiro civil — estruturas")

_FIRST = {
    "PT": ["João", "António", "Manuel", "José", "Carlos", "Paulo", "Nuno", "Ricardo", "Tiago", "Miguel",
           "Bruno", "Hugo", "Fernando", "Luís", "Vítor", "Sérgio", "Diogo", "André", "Rui", "Mário"],
    "FR": ["Antoine", "Karim", "Lucas", "Mehdi", "Thomas", "Nicolas", "Yassine", "Hugo", "Romain",
           "Florian", "Kevin", "Jordan"],
    "GB": ["Oliver", "Harry", "Jack", "George", "Callum", "Liam", "Ryan", "Connor", "Daniel"],
    "US": ["Carlos", "Jose", "Tyler", "Brandon", "Marcus", "Luis", "Austin", "Kevin", "Derek"],
}
_LAST = {
    "PT": ["Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues", "Martins", "Sousa",
           "Fernandes", "Gonçalves", "Gomes", "Lopes", "Marques", "Alves", "Ribeiro", "Pinto", "Teixeira",
           "Moreira", "Correia"],
    "FR": ["Martin", "Bernard", "Dubois", "Lefèvre", "Girard", "Bonnet", "Mercier", "Fontaine", "Rousseau",
           "Garnier", "Faure", "Chevalier"],
    "GB": ["Smith", "Taylor", "Brown", "Wilson", "Evans", "Walker", "Wright", "Hughes", "Clarke"],
    "US": ["Garcia", "Johnson", "Miller", "Davis", "Hernandez", "Lopez", "Anderson", "Thomas", "Moore"],
}
# 50 trolhas: 20 PT, 12 FR, 9 UK, 9 US — taxa horária indicativa (€/h) por país.
MASON_SPLIT = [("PT", 20, 11.5), ("FR", 12, 17.5), ("GB", 9, 20.0), ("US", 9, 26.0)]


def masons() -> list[dict]:
    out = []
    n = 0
    for country, count, rate in MASON_SPLIT:
        firsts, lasts = _FIRST[country], _LAST[country]
        for i in range(count):
            n += 1
            name = f"{firsts[i % len(firsts)]} {lasts[(i * 7 + 3) % len(lasts)]}"
            chef = i < (2 if country == "PT" else 1)
            out.append({
                "name": name,
                "country": country,
                "email": f"trolha{n:02d}@{EMAIL_DOMAIN}",
                "poste": "Trolha — chefe de equipa" if chef else "Trolha",
                "hourly_rate": round(rate + (1.5 if chef else 0) + (i % 3) * 0.5, 2),
            })
    return out


# ------------------------------------------------------------------ clientes
CLIENTS = [
    {"key": "martins", "first_name": "Luísa", "last_name": "Martins", "email": "familia.martins@clientes.tws.construpilot.pt",
     "phone": "+351 912 000 101", "address": "Rua das Acácias, 14", "postal_code": "2750-310", "city": "Cascais",
     "siret": "", "notes": "Moradia T4 — cliente particular (demo)."},
    {"key": "aurora", "company": "Condomínio Edifício Aurora", "email": "administracao@clientes.tws.construpilot.pt",
     "phone": "+351 220 000 202", "address": "Rua de Santa Catarina, 820", "postal_code": "4000-446", "city": "Porto",
     "siret": "PT 900 000 202 (demo)", "notes": "Administração de condomínio — reabilitação de fachada e partes comuns."},
    {"key": "atlantico", "company": "Hotel Atlântico Cascais, S.A.", "email": "direcao@clientes.tws.construpilot.pt",
     "phone": "+351 214 000 303", "address": "Avenida Marginal, 3000", "postal_code": "2750-642", "city": "Cascais",
     "siret": "PT 900 000 303 (demo)", "notes": "Remodelação de 40 quartos com o hotel em funcionamento."},
    {"key": "jardins", "company": "SCI Les Jardins de Lyon", "email": "contact.jardins@clientes.tws.construpilot.pt",
     "phone": "+33 4 00 00 04 04", "address": "52, avenue Jean Jaurès", "postal_code": "69007", "city": "Lyon",
     "siret": "900 000 404 00012 (demo)", "notes": "Maître d'ouvrage — résidence de 12 logements."},
    {"key": "dubois", "first_name": "Claire", "last_name": "Dubois", "email": "claire.dubois@clientes.tws.construpilot.pt",
     "phone": "+33 6 00 00 05 05", "address": "27, boulevard Haussmann", "postal_code": "75009", "city": "Paris",
     "notes": "Appartement haussmannien 110 m² — rénovation complète."},
    {"key": "kensington", "company": "Kensington Living Ltd", "email": "projects.kensington@clientes.tws.construpilot.pt",
     "phone": "+44 20 0000 0606", "address": "12 Pembroke Gardens", "postal_code": "W8 6HS", "city": "London",
     "siret": "UK 00000606 (demo)", "notes": "Townhouse refurbishment — 4 storeys."},
    {"key": "hughes", "first_name": "Emma", "last_name": "Hughes", "email": "emma.hughes@clientes.tws.construpilot.pt",
     "phone": "+44 7700 000707", "address": "8 Didsbury Park", "postal_code": "M20 5LJ", "city": "Manchester",
     "notes": "Rear extension + loft conversion."},
    {"key": "hudson", "company": "Hudson Lofts Development LLC", "email": "pm.hudson@clientes.tws.construpilot.pt",
     "phone": "+1 212 000 0808", "address": "455 West 19th Street", "postal_code": "NY 10011", "city": "New York",
     "siret": "EIN 00-0000808 (demo)", "notes": "Office-to-loft fit-out, 2 floors."},
    {"key": "miami", "company": "Miami Bay Residences LLC", "email": "owner.miamibay@clientes.tws.construpilot.pt",
     "phone": "+1 305 000 0909", "address": "1200 Brickell Bay Drive", "postal_code": "FL 33131", "city": "Miami",
     "siret": "EIN 00-0000909 (demo)", "notes": "New waterfront villa — design & build."},
    {"key": "lumiar", "company": "Lumiar Office Park, Lda.", "email": "facilities@clientes.tws.construpilot.pt",
     "phone": "+351 217 000 010", "address": "Alameda das Linhas de Torres, 160", "postal_code": "1750-149", "city": "Lisboa",
     "siret": "PT 900 000 010 (demo)", "notes": "Cliente recorrente — manutenção e pequenas obras."},
]

# ------------------------------------------------------------------ fornecedores
SUPPLIERS = [
    {"name": "Materiais do Tejo, Lda.", "agency": "Loures", "client_number": "TWS-4410",
     "email": "encomendas.tejo@fornecedores.tws.construpilot.pt", "phone": "+351 219 000 441",
     "categories": ["Obra grossa", "Alvenarias", "Cimentos"], "delivery_address": "Estaleiro central, Loures"},
    {"name": "Cerâmicas do Norte, S.A.", "agency": "Aveiro", "client_number": "CN-2231",
     "email": "vendas.cn@fornecedores.tws.construpilot.pt", "phone": "+351 234 000 223",
     "categories": ["Revestimento cerâmico", "Cobertura"]},
    {"name": "ElectroLuso Distribuição", "agency": "Porto", "client_number": "EL-0912",
     "email": "pro.electroluso@fornecedores.tws.construpilot.pt", "phone": "+351 225 000 091",
     "categories": ["Eletricidade", "AVAC"]},
    {"name": "Négoce Bâtiment Rhône", "agency": "Lyon Gerland", "client_number": "NBR-7781",
     "email": "agence.lyon@fournisseurs.tws.construpilot.pt", "phone": "+33 4 00 00 77 81",
     "categories": ["Gros œuvre", "Isolation", "Plâtrerie"]},
    {"name": "BuildSupply London Ltd", "agency": "Battersea", "client_number": "BSL-3307",
     "email": "trade.desk@suppliers.tws.construpilot.pt", "phone": "+44 20 0000 3307",
     "categories": ["Timber", "Plasterboard", "Joinery"]},
    {"name": "Empire Building Supply Co.", "agency": "Brooklyn Yard", "client_number": "EBS-1150",
     "email": "orders.ebs@suppliers.tws.construpilot.pt", "phone": "+1 718 000 1150",
     "categories": ["Drywall", "Framing", "MEP"]},
]

# ------------------------------------------------------------------ biblioteca de preços (€, preços PT de referência)
# (ref, lote/categoria, designação, unidade, preço venda HT, preço custo HT, IVA %)
LIBRARY = [
    ("EST-01", "Estaleiro", "Montagem e desmontagem de estaleiro (vedação, contentores, sinalética)", "vg", 3800, 2650, 23),
    ("EST-02", "Estaleiro", "Andaime de fachada com rede de proteção, montagem e aluguer mensal", "m2", 9.5, 6.2, 23),
    ("DEM-01", "Demolição", "Demolição de paredes interiores em alvenaria, incl. remoção a vazadouro", "m2", 28, 17, 23),
    ("DEM-02", "Demolição", "Remoção de revestimentos cerâmicos de pavimento e parede", "m2", 16, 9.5, 23),
    ("DEM-03", "Demolição", "Gestão de resíduos de construção e demolição (RCD) com guia e-GAR", "m3", 42, 30, 23),
    ("TER-01", "Movimentação de terras", "Escavação geral em terreno de qualquer natureza, com carga", "m3", 18, 11, 23),
    ("TER-02", "Movimentação de terras", "Aterro compactado em camadas de 0,30 m", "m3", 22, 14, 23),
    ("EST-10", "Obra grossa / Estrutura", "Betão de limpeza C12/15, 0,10 m", "m2", 14, 9, 23),
    ("EST-11", "Obra grossa / Estrutura", "Sapatas em betão armado C25/30 XC2, aço A500 NR", "m3", 265, 188, 23),
    ("EST-12", "Obra grossa / Estrutura", "Pilares em betão armado C30/37, incl. cofragem e armaduras", "m3", 520, 372, 23),
    ("EST-13", "Obra grossa / Estrutura", "Vigas em betão armado C30/37, incl. cofragem e armaduras", "m3", 495, 351, 23),
    ("EST-14", "Obra grossa / Estrutura", "Laje maciça em betão armado C30/37, e=0,20 m", "m2", 92, 64, 23),
    ("EST-15", "Obra grossa / Estrutura", "Laje aligeirada de vigotas pré-esforçadas e abobadilhas, e=0,25 m", "m2", 58, 40, 23),
    ("EST-16", "Obra grossa / Estrutura", "Escada em betão armado, incl. degraus", "m2", 180, 125, 23),
    ("ALV-01", "Alvenarias", "Parede exterior dupla tijolo 15+11 com caixa de ar", "m2", 52, 35, 23),
    ("ALV-02", "Alvenarias", "Parede interior em tijolo de 11 cm", "m2", 24, 15.5, 23),
    ("ALV-03", "Alvenarias", "Reboco tradicional areado fino em paredes exteriores", "m2", 19, 12, 23),
    ("COB-01", "Cobertura", "Cobertura em telha cerâmica Lusa sobre ripado, incl. subtelha", "m2", 48, 32, 23),
    ("COB-02", "Cobertura", "Impermeabilização de terraço com membrana betuminosa dupla e proteção", "m2", 38, 25, 23),
    ("COB-03", "Cobertura", "Caleiras e tubos de queda em zinco", "ml", 34, 22, 23),
    ("ISO-01", "Isolamento", "Sistema ETICS com EPS 60 mm e acabamento acrílico", "m2", 46, 30, 23),
    ("ISO-02", "Isolamento", "Isolamento de cobertura com XPS 80 mm", "m2", 21, 13.5, 23),
    ("ISO-03", "Isolamento", "Lã mineral 50 mm em divisórias (acústico)", "m2", 7.5, 4.8, 23),
    ("CXE-01", "Caixilharia exterior", "Janela em alumínio com corte térmico e vidro duplo 4/16/4, oscilobatente", "m2", 340, 238, 23),
    ("CXE-02", "Caixilharia exterior", "Porta de entrada de segurança, classe 3", "u", 1450, 1015, 23),
    ("CXE-03", "Caixilharia exterior", "Estore exterior motorizado em alumínio térmico", "m2", 165, 112, 23),
    ("CAN-01", "Canalização", "Rede de abastecimento de água em PEX multicamada, por fogo", "vg", 1850, 1240, 23),
    ("CAN-02", "Canalização", "Rede de esgotos domésticos em PVC, por fogo", "vg", 1450, 960, 23),
    ("CAN-03", "Canalização", "Instalação de base de duche, misturadora termostática e resguardo", "u", 980, 650, 23),
    ("CAN-04", "Canalização", "Sanita suspensa com estrutura e placa de comando", "u", 520, 345, 23),
    ("CAN-05", "Canalização", "Bomba de calor para AQS 200 L", "u", 2350, 1620, 23),
    ("ELE-01", "Eletricidade", "Instalação elétrica completa de habitação (circuitos, aparelhagem), por m²", "m2", 48, 31, 23),
    ("ELE-02", "Eletricidade", "Quadro elétrico de habitação com diferenciais 30 mA", "u", 890, 590, 23),
    ("ELE-03", "Eletricidade", "Ponto de iluminação LED embutido", "u", 65, 41, 23),
    ("ELE-04", "Eletricidade", "Infraestruturas de telecomunicações ITED por fogo", "vg", 1150, 760, 23),
    ("ELE-05", "Eletricidade", "Posto de carregamento de veículo elétrico 7,4 kW", "u", 1290, 880, 23),
    ("AVC-01", "AVAC", "Bomba de calor ar-água para piso radiante, 8 kW", "u", 7200, 5050, 23),
    ("AVC-02", "AVAC", "Piso radiante hidráulico, incl. coletores", "m2", 62, 42, 23),
    ("AVC-03", "AVAC", "Ar condicionado multi-split, unidade interior mural", "u", 1050, 720, 23),
    ("AVC-04", "AVAC", "Ventilação mecânica de duplo fluxo com recuperação de calor", "vg", 4800, 3350, 23),
    ("PLA-01", "Estuques / Divisórias (placo)", "Divisória em gesso cartonado 100 mm (placa BA13 dupla face)", "m2", 39, 25.5, 23),
    ("PLA-02", "Estuques / Divisórias (placo)", "Teto falso em gesso cartonado suspenso", "m2", 34, 22, 23),
    ("PLA-03", "Estuques / Divisórias (placo)", "Estuque projetado em paredes interiores", "m2", 14, 8.8, 23),
    ("CER-01", "Revestimento cerâmico", "Pavimento em grés porcelânico 60x60 retificado, assente com cimento-cola", "m2", 52, 34, 23),
    ("CER-02", "Revestimento cerâmico", "Revestimento cerâmico de parede em casas de banho", "m2", 44, 29, 23),
    ("PAV-01", "Pavimentos", "Soalho flutuante em carvalho 14 mm com base acústica", "m2", 58, 39, 23),
    ("PAV-02", "Pavimentos", "Betonilha de regularização 5 cm", "m2", 15, 9.5, 23),
    ("PAV-03", "Pavimentos", "Rodapé em MDF lacado 10 cm", "ml", 12, 7.2, 23),
    ("CIN-01", "Carpintarias interiores", "Porta interior lacada branca, incl. aro e ferragens", "u", 420, 285, 23),
    ("CIN-02", "Carpintarias interiores", "Roupeiro embutido lacado, por metro linear", "ml", 640, 430, 23),
    ("CIN-03", "Carpintarias interiores", "Cozinha equipada (móveis, bancada em quartzo, eletrodomésticos)", "vg", 14500, 10150, 23),
    ("PIN-01", "Pintura", "Pintura de paredes e tetos interiores, 2 demãos de tinta aquosa", "m2", 9.5, 5.6, 23),
    ("PIN-02", "Pintura", "Pintura de fachadas com tinta de silicato", "m2", 14, 8.5, 23),
    ("PIN-03", "Pintura", "Envernizamento de madeiras exteriores", "m2", 18, 11, 23),
    ("EXT-01", "Arranjos exteriores", "Pavimento exterior em lajeado de granito", "m2", 78, 52, 23),
    ("EXT-02", "Arranjos exteriores", "Piscina em betão armado 8x4 m, chave na mão", "vg", 32000, 23200, 23),
    ("LIM-01", "Limpeza / Receção", "Limpeza final de obra e entrega ao cliente", "m2", 4.5, 2.6, 23),
]

# coeficiente de preço por país (referencial PT = 1,00) e IVA por defeito
COUNTRY_PRICING = {
    "PT": {"coef": 1.00, "vat": 23, "vat_reno": 6},
    "FR": {"coef": 1.42, "vat": 20, "vat_reno": 10},
    "GB": {"coef": 1.58, "vat": 20, "vat_reno": 20},
    "US": {"coef": 1.74, "vat": 0, "vat_reno": 0},   # sales tax tratada fora do orçamento
}

# ------------------------------------------------------------------ obras em fases distintas
# phase: prospect (orçamento ainda não adjudicado) | en_cours | termine ; progress em %
SITES = [
    {"key": "martins", "name": "Moradia Martins — Cascais", "client": "martins", "country": "PT", "director": 0,
     "address": "Rua das Acácias, 14", "postal_code": "2750-310", "city": "Cascais", "lat": 38.7071, "lng": -9.4214,
     "status": "termine", "progress": 100, "type": "construction_maison_neuve", "surface": 220, "region": "Lisboa",
     "building": "maison", "condition": "neuf", "reno": False, "started_days_ago": 420, "masons": 8,
     "scope": "moradia_nova", "plans": "moradia",
     "description": "Moradia unifamiliar T4 com piscina, 2 pisos, estrutura em betão armado."},
    {"key": "aurora", "name": "Reabilitação Edifício Aurora — Porto", "client": "aurora", "country": "PT", "director": 1,
     "address": "Rua de Santa Catarina, 820", "postal_code": "4000-446", "city": "Porto", "lat": 41.1530, "lng": -8.6062,
     "status": "en_cours", "progress": 75, "type": "renovation_complete", "surface": 960, "region": "Porto",
     "building": "immeuble", "condition": "a_renover", "reno": True, "started_days_ago": 210, "masons": 9,
     "scope": "reabilitacao", "plans": "edificio",
     "description": "Reabilitação de edifício de 8 frações: fachada ETICS, coberturas, partes comuns e 4 frações interiores."},
    {"key": "atlantico", "name": "Hotel Atlântico — Remodelação 40 quartos", "client": "atlantico", "country": "PT", "director": 0,
     "address": "Avenida Marginal, 3000", "postal_code": "2750-642", "city": "Cascais", "lat": 38.6979, "lng": -9.4060,
     "status": "en_cours", "progress": 45, "type": "renovation_complete", "surface": 1450, "region": "Lisboa",
     "building": "immeuble", "condition": "bon", "reno": False, "started_days_ago": 120, "masons": 7,
     "scope": "hotel", "plans": "hotel",
     "description": "Remodelação de 40 quartos e casas de banho, por fases, com o hotel em funcionamento."},
    {"key": "jardins", "name": "Résidence Les Jardins — Lyon (12 logements)", "client": "jardins", "country": "FR", "director": 2,
     "address": "52, avenue Jean Jaurès", "postal_code": "69007", "city": "Lyon", "lat": 45.7406, "lng": 4.8414,
     "status": "en_cours", "progress": 20, "type": "construction_maison_neuve", "surface": 980, "region": "Auvergne-Rhône-Alpes",
     "building": "immeuble", "condition": "neuf", "reno": False, "started_days_ago": 75, "masons": 7,
     "scope": "residencia_nova", "plans": "edificio",
     "description": "Construction d'une résidence R+3 de 12 logements — phase gros œuvre."},
    {"key": "dubois", "name": "Appartement Dubois — Paris 9e", "client": "dubois", "country": "FR", "director": 2,
     "address": "27, boulevard Haussmann", "postal_code": "75009", "city": "Paris", "lat": 48.8738, "lng": 2.3320,
     "status": "termine", "progress": 100, "type": "renovation_appartement", "surface": 110, "region": "Île-de-France",
     "building": "appartement", "condition": "a_renover", "reno": True, "started_days_ago": 190, "masons": 5,
     "scope": "apartamento", "plans": "apartamento",
     "description": "Rénovation complète d'un appartement haussmannien de 110 m²."},
    {"key": "kensington", "name": "Kensington Townhouse — London", "client": "kensington", "country": "GB", "director": 3,
     "address": "12 Pembroke Gardens", "postal_code": "W8 6HS", "city": "London", "lat": 51.4975, "lng": -0.1986,
     "status": "en_cours", "progress": 60, "type": "renovation_complete", "surface": 320, "region": "Île-de-France",
     "building": "maison", "condition": "a_renover", "reno": True, "started_days_ago": 160, "masons": 6,
     "scope": "townhouse", "plans": "moradia",
     "description": "Full refurbishment of a 4-storey Victorian townhouse, new MEP and finishes."},
    {"key": "hughes", "name": "Hughes Extension — Manchester", "client": "hughes", "country": "GB", "director": 3,
     "address": "8 Didsbury Park", "postal_code": "M20 5LJ", "city": "Manchester", "lat": 53.4159, "lng": -2.2313,
     "status": "prospect", "progress": 0, "type": "extension", "surface": 45, "region": "Hauts-de-France",
     "building": "maison", "condition": "bon", "reno": False, "started_days_ago": 0, "masons": 0,
     "scope": "extensao", "plans": None,
     "description": "Rear single-storey extension + loft conversion — quote sent, awaiting client decision."},
    {"key": "hudson", "name": "Hudson Lofts — New York fit-out", "client": "hudson", "country": "US", "director": 4,
     "address": "455 West 19th Street", "postal_code": "NY 10011", "city": "New York", "lat": 40.7448, "lng": -74.0056,
     "status": "en_cours", "progress": 10, "type": "renovation_complete", "surface": 1100, "region": "Île-de-France",
     "building": "immeuble", "condition": "bon", "reno": False, "started_days_ago": 21, "masons": 8,
     "scope": "loft", "plans": "hotel",
     "description": "Office-to-loft conversion on 2 floors — strip-out completed, framing starting."},
    {"key": "miami", "name": "Miami Bay Villa — Florida", "client": "miami", "country": "US", "director": 4,
     "address": "1200 Brickell Bay Drive", "postal_code": "FL 33131", "city": "Miami", "lat": 25.7617, "lng": -80.1918,
     "status": "prospect", "progress": 0, "type": "construction_maison_neuve", "surface": 410, "region": "Provence-Alpes-Côte d'Azur",
     "building": "maison", "condition": "neuf", "reno": False, "started_days_ago": 0, "masons": 0,
     "scope": "moradia_nova", "plans": "moradia",
     "description": "Waterfront villa design & build — first quote refused (budget), revised option in draft."},
]

# composição dos orçamentos: (ref, quantidade por m² de área útil  OU  quantidade fixa se "fix")
SCOPES = {
    "moradia_nova": [
        ("EST-01", 1, "fix"), ("TER-01", 0.9, None), ("TER-02", 0.3, None), ("EST-10", 0.6, None),
        ("EST-11", 0.12, None), ("EST-12", 0.05, None), ("EST-13", 0.07, None), ("EST-15", 0.95, None),
        ("EST-16", 12, "fix"), ("ALV-01", 1.1, None), ("ALV-02", 0.9, None), ("ALV-03", 1.1, None),
        ("COB-01", 0.6, None), ("COB-03", 0.25, None), ("ISO-01", 1.1, None), ("ISO-02", 0.6, None),
        ("CXE-01", 0.16, None), ("CXE-02", 1, "fix"), ("CXE-03", 0.12, None),
        ("CAN-01", 1, "fix"), ("CAN-02", 1, "fix"), ("CAN-03", 3, "fix"), ("CAN-04", 4, "fix"), ("CAN-05", 1, "fix"),
        ("ELE-01", 1.0, None), ("ELE-02", 1, "fix"), ("ELE-03", 0.18, None), ("ELE-04", 1, "fix"), ("ELE-05", 1, "fix"),
        ("AVC-01", 1, "fix"), ("AVC-02", 0.85, None), ("AVC-04", 1, "fix"),
        ("PLA-02", 0.4, None), ("PLA-03", 2.2, None), ("CER-01", 0.35, None), ("CER-02", 0.3, None),
        ("PAV-01", 0.55, None), ("PAV-03", 0.8, None), ("CIN-01", 11, "fix"), ("CIN-02", 9, "fix"), ("CIN-03", 1, "fix"),
        ("PIN-01", 2.6, None), ("PIN-02", 1.0, None), ("EXT-01", 0.4, None), ("EXT-02", 1, "fix"), ("LIM-01", 1.0, None),
    ],
    "reabilitacao": [
        ("EST-01", 1, "fix"), ("EST-02", 1.1, None), ("DEM-01", 0.12, None), ("DEM-02", 0.2, None), ("DEM-03", 0.06, None),
        ("ALV-03", 0.3, None), ("COB-01", 0.18, None), ("COB-02", 0.08, None), ("COB-03", 0.08, None),
        ("ISO-01", 0.9, None), ("ISO-02", 0.18, None), ("CXE-01", 0.1, None), ("CXE-02", 1, "fix"),
        ("CAN-01", 4, "fix"), ("CAN-02", 4, "fix"), ("CAN-03", 4, "fix"), ("ELE-01", 0.45, None), ("ELE-02", 4, "fix"),
        ("ELE-04", 4, "fix"), ("PLA-01", 0.25, None), ("PLA-02", 0.2, None), ("CER-01", 0.15, None), ("CER-02", 0.12, None),
        ("PAV-01", 0.25, None), ("CIN-01", 24, "fix"), ("PIN-01", 1.3, None), ("PIN-02", 0.9, None), ("LIM-01", 1.0, None),
    ],
    "hotel": [
        ("EST-01", 1, "fix"), ("DEM-01", 0.08, None), ("DEM-02", 0.3, None), ("DEM-03", 0.05, None),
        ("PLA-01", 0.35, None), ("PLA-02", 0.6, None), ("ISO-03", 0.35, None),
        ("CAN-03", 40, "fix"), ("CAN-04", 40, "fix"), ("ELE-01", 0.6, None), ("ELE-03", 0.3, None),
        ("AVC-03", 40, "fix"), ("CER-01", 0.2, None), ("CER-02", 0.25, None), ("PAV-01", 0.55, None), ("PAV-03", 0.6, None),
        ("CIN-01", 44, "fix"), ("CIN-02", 40, "fix"), ("PIN-01", 2.4, None), ("LIM-01", 1.0, None),
    ],
    "residencia_nova": [
        ("EST-01", 1, "fix"), ("TER-01", 1.1, None), ("TER-02", 0.25, None), ("EST-10", 0.35, None),
        ("EST-11", 0.1, None), ("EST-12", 0.045, None), ("EST-13", 0.06, None), ("EST-14", 1.0, None),
        ("EST-16", 40, "fix"), ("ALV-01", 0.75, None), ("ALV-02", 0.6, None), ("ALV-03", 0.75, None),
        ("COB-02", 0.27, None), ("ISO-01", 0.75, None), ("CXE-01", 0.13, None),
        ("CAN-01", 12, "fix"), ("CAN-02", 12, "fix"), ("ELE-01", 1.0, None), ("ELE-02", 12, "fix"), ("ELE-04", 12, "fix"),
        ("AVC-04", 12, "fix"), ("PLA-01", 0.5, None), ("CER-01", 0.25, None), ("PAV-01", 0.6, None),
        ("CIN-01", 72, "fix"), ("PIN-01", 2.4, None), ("LIM-01", 1.0, None),
    ],
    "apartamento": [
        ("DEM-01", 0.4, None), ("DEM-02", 0.5, None), ("DEM-03", 0.12, None), ("PLA-01", 0.6, None), ("PLA-02", 0.5, None),
        ("ISO-03", 0.6, None), ("CAN-01", 1, "fix"), ("CAN-02", 1, "fix"), ("CAN-03", 2, "fix"), ("CAN-04", 2, "fix"),
        ("ELE-01", 1.0, None), ("ELE-02", 1, "fix"), ("ELE-03", 0.25, None), ("AVC-03", 4, "fix"),
        ("CER-02", 0.35, None), ("PAV-01", 0.85, None), ("PAV-03", 1.0, None), ("CIN-01", 8, "fix"), ("CIN-03", 1, "fix"),
        ("PIN-01", 3.0, None), ("LIM-01", 1.0, None),
    ],
    "townhouse": [
        ("EST-01", 1, "fix"), ("DEM-01", 0.3, None), ("DEM-02", 0.35, None), ("DEM-03", 0.1, None), ("EST-13", 0.02, None),
        ("COB-01", 0.3, None), ("ISO-02", 0.3, None), ("CXE-01", 0.12, None), ("PLA-01", 0.4, None), ("PLA-02", 0.4, None),
        ("CAN-01", 1, "fix"), ("CAN-02", 1, "fix"), ("CAN-03", 4, "fix"), ("CAN-04", 5, "fix"), ("ELE-01", 1.0, None),
        ("ELE-02", 1, "fix"), ("AVC-01", 1, "fix"), ("AVC-02", 0.7, None), ("CER-02", 0.3, None), ("PAV-01", 0.7, None),
        ("CIN-01", 16, "fix"), ("CIN-03", 1, "fix"), ("PIN-01", 2.8, None), ("LIM-01", 1.0, None),
    ],
    "extensao": [
        ("EST-01", 1, "fix"), ("TER-01", 1.2, None), ("EST-11", 0.25, None), ("EST-14", 1.0, None), ("ALV-01", 1.4, None),
        ("COB-02", 1.0, None), ("ISO-02", 1.0, None), ("CXE-01", 0.35, None), ("ELE-01", 1.0, None), ("AVC-02", 1.0, None),
        ("PLA-03", 2.0, None), ("CER-01", 1.0, None), ("PIN-01", 2.6, None), ("LIM-01", 1.0, None),
    ],
    "loft": [
        ("EST-01", 1, "fix"), ("DEM-01", 0.25, None), ("DEM-03", 0.08, None), ("PLA-01", 0.5, None), ("PLA-02", 0.7, None),
        ("ISO-03", 0.5, None), ("CAN-01", 8, "fix"), ("CAN-02", 8, "fix"), ("CAN-03", 8, "fix"), ("CAN-04", 10, "fix"),
        ("ELE-01", 1.0, None), ("ELE-03", 0.25, None), ("AVC-04", 2, "fix"), ("AVC-03", 16, "fix"), ("PAV-02", 1.0, None),
        ("PAV-01", 0.8, None), ("CIN-03", 8, "fix"), ("PIN-01", 2.4, None), ("LIM-01", 1.0, None),
    ],
}

# Ordem de execução dos lotes (planeamento) e duração-base em dias úteis por 100 m²
LOT_ORDER = [
    ("Estaleiro", 0.4), ("Demolição", 1.2), ("Movimentação de terras", 1.0), ("Obra grossa / Estrutura", 4.5),
    ("Alvenarias", 2.2), ("Cobertura", 1.4), ("Caixilharia exterior", 0.8), ("Isolamento", 1.2),
    ("Canalização", 1.6), ("Eletricidade", 1.6), ("AVAC", 1.2), ("Estuques / Divisórias (placo)", 1.8),
    ("Revestimento cerâmico", 1.4), ("Pavimentos", 1.0), ("Carpintarias interiores", 1.0), ("Pintura", 1.2),
    ("Arranjos exteriores", 1.2), ("Limpeza / Receção", 0.3),
]
