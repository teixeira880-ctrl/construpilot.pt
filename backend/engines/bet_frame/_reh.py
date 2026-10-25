# Copie embarquée de engines/calc_lots (site .pt) pour que le moteur ossature soit identique sur .fr et .pt.
"""Pré-certificado energético INDICATIVO de habitação (REH / SCE — DL 101-D/2020, Portaria 138-I/2021, Despachos 6476-E e 6476-H/2021).

Calcula, para uma habitação nova, em grande renovação ou existente:
  - clima (NUTS III + correção de altitude) → zonas I1/I2/I3 e V1/V2/V3 ;
  - Nic (aquecimento) e Ni (referência), Nvc (arrefecimento) e Nv, Qa (AQS) ;
  - Ntc e Nt (energia primária, Fpu eletricidade 2,5 / combustíveis 1,0), RNt = Ntc/Nt → classe A+ … F ;
  - requisitos: Umáx e Uw,máx (Portaria 138-I), Nic/Ni, Nvc/Nv, classe mínima, RNt, Rph ≥ 0,5 h⁻¹.
Metodologia de 2013 (Despacho 15793-I), retomada no Manual SCE 2021; eficiências de referência e alguns valores por defeito
aproximados (assinalados nas hipóteses). Não substitui o certificado emitido por um Perito Qualificado (ADENE).
"""
from __future__ import annotations

import math
import unicodedata

# NUTS III : z_ref (m), M (meses), a_M (mês/km), GD (°C.dia), a_GD, θext,i, a_θi, Gsul (kWh/m².mês) ; θext,v, a_θv, Isol (H, N, NE, E, SE, S, SO, O, NO)
NUTS = {
    "Minho-Lima": (268, 7.2, 1, 1629, 1500, 8.2, -5, 130, 20.5, -4, (785, 220, 345, 475, 485, 425, 485, 475, 345)),
    "Cávado": (171, 6.8, 1, 1491, 1300, 9.0, -6, 125, 20.7, -3, (795, 220, 345, 485, 490, 425, 490, 485, 345)),
    "Ave": (426, 7.2, 0, 1653, 1500, 7.8, -6, 125, 20.8, -3, (795, 220, 350, 490, 490, 425, 490, 490, 350)),
    "Grande Porto": (94, 6.2, 2, 1250, 1600, 9.9, -7, 130, 20.9, 0, (800, 220, 350, 490, 490, 425, 490, 490, 350)),
    "Tâmega": (320, 6.7, 0, 1570, 1600, 7.8, -5, 135, 21.4, -3, (800, 220, 350, 490, 490, 425, 490, 490, 350)),
    "Entre Douro e Vouga": (298, 6.9, 1, 1544, 1400, 8.4, -5, 135, 20.6, -3, (805, 220, 350, 490, 490, 425, 490, 490, 350)),
    "Douro": (579, 6.9, 0, 1764, 1400, 6.3, -4, 135, 22.7, -6, (805, 220, 350, 490, 490, 420, 490, 490, 350)),
    "Alto Trás-os-Montes": (680, 7.3, 0, 2015, 1400, 5.5, -4, 125, 21.5, -7, (790, 220, 345, 480, 485, 425, 485, 480, 345)),
    "Baixo Vouga": (50, 6.3, 2, 1337, 1100, 9.5, -5, 140, 20.6, -2, (810, 220, 355, 490, 490, 420, 490, 490, 355)),
    "Baixo Mondego": (67, 6.3, 0, 1304, 1000, 9.7, -5, 140, 20.9, 0, (825, 225, 360, 495, 495, 420, 495, 495, 360)),
    "Pinhal Litoral": (126, 6.6, 0, 1323, 1900, 9.6, -5, 140, 20.1, -2, (830, 225, 360, 500, 495, 415, 495, 500, 360)),
    "Pinhal Interior Norte": (361, 6.8, 0, 1555, 1600, 8.3, -5, 140, 21.2, -2, (825, 220, 357, 500, 495, 420, 495, 500, 357)),
    "Dão-Lafões": (497, 7.3, 0, 1702, 1900, 7.5, -6, 135, 21.2, -3, (815, 220, 355, 495, 490, 415, 490, 495, 355)),
    "Pinhal Interior Sul": (361, 6.7, 1, 1511, 1500, 8.4, -4, 145, 22.4, -3, (830, 225, 360, 500, 500, 420, 500, 500, 360)),
    "Serra da Estrela": (553, 7.5, 0, 1851, 1600, 7.0, -5, 135, 21.0, -4, (820, 225, 355, 495, 495, 420, 495, 495, 355)),
    "Beira Interior Norte": (717, 7.5, 0, 1924, 1000, 6.3, -3, 135, 21.7, -5, (820, 220, 355, 495, 500, 425, 500, 495, 355)),
    "Beira Interior Sul": (328, 5.4, 1, 1274, 1800, 9.1, -6, 140, 25.3, -7, (830, 220, 360, 500, 495, 420, 495, 500, 360)),
    "Cova da Beira": (507, 7.1, 0, 1687, 1400, 7.5, -5, 140, 22.5, -6, (825, 225, 360, 495, 495, 425, 495, 495, 360)),
    "Oeste": (99, 5.6, 0, 1165, 2200, 10.3, -8, 145, 21.0, 0, (830, 225, 360, 500, 495, 415, 495, 500, 360)),
    "Médio Tejo": (168, 5.9, 0, 1330, 1300, 9.5, -4, 145, 22.1, -7, (835, 220, 360, 500, 495, 415, 495, 500, 360)),
    "Grande Lisboa": (109, 5.3, 3, 1071, 1700, 10.8, -4, 150, 21.7, -10, (840, 225, 365, 500, 495, 410, 495, 500, 365)),
    "Península de Setúbal": (47, 4.7, 0, 1045, 1500, 10.7, -4, 145, 22.8, -5, (845, 225, 365, 505, 495, 410, 495, 505, 365)),
    "Lezíria do Tejo": (73, 5.2, 3, 1135, 2700, 10.2, -7, 145, 23.1, -6, (835, 225, 365, 500, 495, 410, 495, 500, 365)),
    "Alentejo Litoral": (88, 5.3, 2, 1089, 1100, 10.8, -2, 150, 22.2, 0, (850, 225, 365, 510, 495, 405, 495, 510, 365)),
    "Alto Alentejo": (246, 5.3, 2, 1221, 1200, 9.6, -3, 145, 24.5, 0, (845, 225, 365, 505, 500, 415, 500, 505, 365)),
    "Alentejo Central": (221, 5.3, 2, 1150, 1100, 10.0, -4, 150, 24.3, 0, (850, 225, 370, 510, 500, 415, 500, 510, 370)),
    "Baixo Alentejo": (178, 5.0, 0, 1068, 1000, 10.7, -2, 155, 24.7, 0, (855, 225, 370, 510, 495, 405, 495, 510, 370)),
    "Algarve": (145, 4.8, 0, 987, 1800, 11.3, -6, 155, 23.1, 0, (865, 225, 375, 515, 500, 405, 500, 515, 375)),
    "RA Açores": (10, 2.9, 3, 604, 1500, 14.4, -7, 110, 21.3, -6, (640, 195, 285, 375, 375, 235, 375, 375, 285)),
    "RA Madeira": (380, 3.2, 3, 818, 1500, 14.8, -7, 105, 20.2, -6, (580, 195, 260, 325, 320, 280, 320, 325, 260)),
}
_MUN = {
    "Minho-Lima": "Arcos de Valdevez, Caminha, Melgaço, Monção, Paredes de Coura, Ponte da Barca, Ponte de Lima, Valença, Viana do Castelo, Vila Nova de Cerveira",
    "Alto Trás-os-Montes": "Alfândega da Fé, Boticas, Bragança, Chaves, Macedo de Cavaleiros, Miranda do Douro, Mirandela, Mogadouro, Montalegre, Ribeira de Pena, Valpaços, Vila Flor, Vila Pouca de Aguiar, Vimioso, Vinhais",
    "Cávado": "Amares, Barcelos, Braga, Esposende, Terras de Bouro, Vila Verde",
    "Ave": "Cabeceiras de Basto, Fafe, Guimarães, Mondim de Basto, Póvoa de Lanhoso, Vieira do Minho, Vila Nova de Famalicão, Vizela",
    "Grande Porto": "Espinho, Gondomar, Maia, Matosinhos, Porto, Póvoa de Varzim, Santo Tirso, Trofa, Valongo, Vila do Conde, Vila Nova de Gaia",
    "Tâmega": "Amarante, Baião, Castelo de Paiva, Celorico de Basto, Cinfães, Felgueiras, Lousada, Marco de Canaveses, Paços de Ferreira, Paredes, Penafiel, Resende",
    "Douro": "Alijó, Armamar, Carrazeda de Ansiães, Freixo de Espada à Cinta, Lamego, Mesão Frio, Moimenta da Beira, Murça, Penedono, Peso da Régua, Sabrosa, Santa Marta de Penaguião, São João da Pesqueira, Sernancelhe, Tabuaço, Tarouca, Torre de Moncorvo, Vila Nova de Foz Côa, Vila Real",
    "Entre Douro e Vouga": "Arouca, Oliveira de Azeméis, Santa Maria da Feira, São João da Madeira, Vale de Cambra",
    "Baixo Vouga": "Águeda, Albergaria-a-Velha, Anadia, Aveiro, Estarreja, Ílhavo, Murtosa, Oliveira do Bairro, Ovar, Sever do Vouga, Vagos",
    "Baixo Mondego": "Cantanhede, Coimbra, Condeixa-a-Nova, Figueira da Foz, Mealhada, Mira, Montemor-o-Velho, Mortágua, Penacova, Soure",
    "Beira Interior Norte": "Almeida, Celorico da Beira, Figueira de Castelo Rodrigo, Guarda, Manteigas, Mêda, Pinhel, Sabugal, Trancoso",
    "Beira Interior Sul": "Castelo Branco, Idanha-a-Nova, Penamacor, Vila Velha de Ródão",
    "Cova da Beira": "Belmonte, Covilhã, Fundão",
    "Serra da Estrela": "Fornos de Algodres, Gouveia, Seia",
    "Dão-Lafões": "Aguiar da Beira, Carregal do Sal, Castro Daire, Mangualde, Nelas, Oliveira de Frades, Penalva do Castelo, Santa Comba Dão, São Pedro do Sul, Sátão, Tondela, Vila Nova de Paiva, Viseu, Vouzela",
    "Pinhal Interior Norte": "Alvaiázere, Ansião, Arganil, Castanheira de Pera, Figueiró dos Vinhos, Góis, Lousã, Miranda do Corvo, Oliveira do Hospital, Pampilhosa da Serra, Pedrógão Grande, Penela, Tábua, Vila Nova de Poiares",
    "Pinhal Interior Sul": "Oleiros, Proença-a-Nova, Sertã, Vila de Rei",
    "Pinhal Litoral": "Batalha, Leiria, Marinha Grande, Pombal, Porto de Mós",
    "Oeste": "Alcobaça, Alenquer, Arruda dos Vinhos, Bombarral, Cadaval, Caldas da Rainha, Lourinhã, Nazaré, Óbidos, Peniche, Sobral de Monte Agraço, Torres Vedras",
    "Médio Tejo": "Abrantes, Alcanena, Constância, Entroncamento, Ferreira do Zêzere, Mação, Ourém, Sardoal, Tomar, Torres Novas, Vila Nova da Barquinha",
    "Lezíria do Tejo": "Almeirim, Alpiarça, Azambuja, Benavente, Cartaxo, Chamusca, Coruche, Golegã, Rio Maior, Salvaterra de Magos, Santarém",
    "Grande Lisboa": "Amadora, Cascais, Lisboa, Loures, Mafra, Odivelas, Oeiras, Sintra, Vila Franca de Xira",
    "Península de Setúbal": "Alcochete, Almada, Barreiro, Moita, Montijo, Palmela, Seixal, Sesimbra, Setúbal",
    "Alto Alentejo": "Alter do Chão, Arronches, Avis, Campo Maior, Castelo de Vide, Crato, Elvas, Fronteira, Gavião, Marvão, Monforte, Mora, Nisa, Ponte de Sor, Portalegre",
    "Alentejo Central": "Alandroal, Arraiolos, Borba, Estremoz, Évora, Montemor-o-Novo, Mourão, Portel, Redondo, Reguengos de Monsaraz, Sousel, Vendas Novas, Viana do Alentejo, Vila Viçosa",
    "Alentejo Litoral": "Alcácer do Sal, Grândola, Odemira, Santiago do Cacém, Sines",
    "Baixo Alentejo": "Aljustrel, Almodôvar, Alvito, Barrancos, Beja, Castro Verde, Cuba, Ferreira do Alentejo, Mértola, Moura, Ourique, Serpa, Vidigueira",
    "Algarve": "Albufeira, Alcoutim, Aljezur, Castro Marim, Faro, Lagoa, Lagos, Loulé, Monchique, Olhão, Portimão, São Brás de Alportel, Silves, Tavira, Vila do Bispo, Vila Real de Santo António",
    "RA Açores": "Angra do Heroísmo, Calheta (Açores), Corvo, Horta, Lagoa (Açores), Lajes das Flores, Lajes do Pico, Madalena, Nordeste, Ponta Delgada, Povoação, Ribeira Grande, Santa Cruz da Graciosa, Santa Cruz das Flores, São Roque do Pico, Velas, Vila do Porto, Vila Franca do Campo, Praia da Vitória",
    "RA Madeira": "Calheta (Madeira), Câmara de Lobos, Funchal, Machico, Ponta do Sol, Porto Moniz, Porto Santo, Ribeira Brava, Santa Cruz, Santana, São Vicente",
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


CONCELHOS = {_norm(m): n for n, ms in _MUN.items() for m in ms.split(", ")}
CONCELHOS.update({"lagoa": "Algarve", "calheta": "RA Madeira"})       # homónimos : por defeito continente / Madeira
ORIENT = ["H", "N", "NE", "E", "SE", "S", "SO", "O", "NO"]
XJ = {"N": 0.27, "NE": 0.33, "NO": 0.33, "E": 0.56, "O": 0.56, "SE": 0.84, "SO": 0.84, "S": 1.0, "H": 0.89}
A_INERCIA = {"fraca": 1.8, "media": 2.6, "forte": 4.2}
FPU = {"eletricidade": 2.5, "gas_natural": 1.0, "gpl": 1.0, "gasoleo": 1.0, "biomassa": 1.0}
# sistemas : (vetor, eficiência por defeito, eficiência de referência para Nt)
AQUEC = {"resistencia_eletrica": ("eletricidade", 1.0, 1.0), "bomba_calor": ("eletricidade", 3.5, 3.0), "split_ar_ar": ("eletricidade", 3.5, 3.0),
         "caldeira_gas": ("gas_natural", 0.92, 0.92), "caldeira_gas_condensacao": ("gas_natural", 1.0, 0.92), "caldeira_gasoleo": ("gasoleo", 0.86, 0.89),
         "recuperador_biomassa": ("biomassa", 0.75, 0.75), "caldeira_biomassa": ("biomassa", 0.86, 0.86)}
AQS = {"termoacumulador": ("eletricidade", 0.95, 0.95), "bomba_calor": ("eletricidade", 2.8, 2.8), "esquentador_gas": ("gas_natural", 0.86, 0.86),
       "caldeira_gas": ("gas_natural", 0.89, 0.89), "caldeira_gas_condensacao": ("gas_natural", 0.97, 0.89)}
CLASSES = [(0.25, "A+"), (0.50, "A"), (0.75, "B"), (1.00, "B-"), (1.50, "C"), (2.00, "D"), (2.50, "E"), (math.inf, "F")]
UMAX = {"parede": (0.50, 0.40, 0.35), "cobertura": (0.40, 0.35, 0.30), "pavimento": (0.40, 0.35, 0.30)}
UMAX_INT = {"parede": (2.00, 2.00, 1.90), "cobertura": (1.65, 1.30, 1.20), "pavimento": (1.65, 1.30, 1.20)}
UW_MAX = (2.80, 2.40, 2.20)
UMAX_ACORES = {"parede": (1.75, 1.60, 1.45), "cobertura": (1.25, 1.00, 0.90), "pavimento": (1.25, 1.00, 0.90)}
UW_MAX_ACORES = (2.90, 2.60, 2.40)
UREF_RA = {"parede": (0.70, 0.60, 0.45), "cobertura": (0.45, 0.40, 0.35), "pavimento": (0.45, 0.40, 0.35), "envidracado": (2.80, 2.40, 2.20)}
UREF_INT_RA = {"parede": (0.90, 0.80, 0.70), "cobertura": (0.70, 0.70, 0.60), "pavimento": (0.70, 0.70, 0.60)}
UREF = {"parede": (0.50, 0.40, 0.35), "cobertura": (0.40, 0.35, 0.30), "pavimento": (0.40, 0.35, 0.30), "envidracado": (2.80, 2.40, 2.20)}
UREF_INT = {"parede": (0.80, 0.70, 0.60), "cobertura": (0.60, 0.60, 0.50), "pavimento": (0.60, 0.60, 0.50)}
BTR = {"exterior": 1.0, "enu": 0.8, "enu_ventilado": 1.0, "adjacente": 0.6, "solo": 1.0}
OCUPANTES = {0: 2, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8}
U_DEFEITO = {   # existentes sem caracterização (ordens de grandeza por época), W/(m².°C)
    "antes_1960": {"parede": 1.8, "cobertura": 2.5, "pavimento": 1.6, "envidracado": 5.1},
    "1960_1990": {"parede": 1.3, "cobertura": 1.9, "pavimento": 1.4, "envidracado": 4.1},
    "1991_2006": {"parede": 0.9, "cobertura": 1.0, "pavimento": 1.0, "envidracado": 3.6},
    "2007_2013": {"parede": 0.6, "cobertura": 0.5, "pavimento": 0.6, "envidracado": 3.0},
    "depois_2013": {"parede": 0.4, "cobertura": 0.35, "pavimento": 0.4, "envidracado": 2.5},
}


def clima(concelho: str | None = None, nuts: str | None = None, altitude_m: float | None = None) -> dict:
    nuts_n = {_norm(k): k for k in NUTS}
    n = nuts if nuts in NUTS else nuts_n.get(_norm(nuts or "")) or CONCELHOS.get(_norm(concelho or ""))
    aviso = None
    if not nuts and _norm(concelho or "") in ("lagoa", "calheta"):
        aviso = f"concelho homónimo « {concelho} »: considerado {n}; indicar « {concelho} (Açores) » ou a NUTS III se for outro"
    if not n:
        raise ValueError("concelho (ou NUTS III) desconhecido — indique o concelho, p. ex. 'Porto', 'Évora'")
    zr, M, aM, GD, aGD, ti, ati, gsul, tv, atv, isol = NUTS[n]
    z = float(altitude_m) if altitude_m is not None else zr
    dz = (z - zr) / 1000
    M, GD, tv = M + aM * dz, GD + aGD * dz, tv + atv * dz
    zi = "I1" if GD <= 1300 else "I2" if GD <= 1800 else "I3"
    zv = "V1" if tv <= 20 else "V2" if tv <= 22 else "V3"
    return {"nuts": n, "altitude_m": z, "M": M, "GD": GD, "theta_i": ti + ati * dz, "Gsul": gsul, "theta_v": tv, "Isol": dict(zip(ORIENT, isol)),
            "zona_i": zi, "zona_v": zv, "aviso": aviso, "ri": int(zi[1]) - 1,
            "regiao": "acores" if n == "RA Açores" else "madeira" if n == "RA Madeira" else "continente"}


def _eta(gamma: float, a: float) -> float:
    if gamma < 0:
        return 1 / gamma if gamma else 1.0
    if gamma == 0:
        return 1.0
    if abs(gamma - 1) < 1e-9:
        return a / (a + 1)
    return (1 - gamma ** a) / (1 - gamma ** (a + 1))


def _epoca(ano: int) -> str:
    return "antes_1960" if ano < 1960 else "1960_1990" if ano <= 1990 else "1991_2006" if ano <= 2006 else "2007_2013" if ano <= 2013 else "depois_2013"


def _envolvente_tipo(p: dict, hyp: list) -> list:
    ap = float(p["area_util_m2"])
    pd = float(p.get("pe_direito_m") or 2.6)
    tipo = p.get("tipo") or "moradia"
    obra = p.get("obra") or "existente"
    ano = int(p.get("ano_construcao") or (2026 if obra == "nova" else 1980))
    if obra == "existente":
        U = U_DEFEITO[_epoca(ano)]
    else:   # obra nova / grande renovação : soluções correntes que cumprem a Portaria 138-I (≈ 85 % do Umáx)
        ri = clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))["ri"]
        cl = clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))
        um, uw = (UMAX_ACORES, UW_MAX_ACORES) if cl["regiao"] == "acores" else (UMAX, UW_MAX)
        U = {k: round(0.85 * v[ri], 2) for k, v in um.items()}
        U["envidracado"] = round(0.85 * uw[ri], 2)
    piso = int(p.get("pisos") or (2 if (tipo == "moradia" and ap > 120) else 1))
    impl = ap / piso
    per = 4 * math.sqrt(impl)
    aw = float(p.get("area_envidracada_m2") or 0.17 * ap)
    if tipo == "moradia":
        env = [{"tipo": "parede", "area_m2": per * pd * piso - aw - 2, "U": U["parede"]}, {"tipo": "cobertura", "area_m2": impl, "U": U["cobertura"]},
               {"tipo": "pavimento", "area_m2": impl, "U": U["pavimento"], "fronteira": "solo"}, {"tipo": "porta", "area_m2": 2.0, "U": 2.5}]
    else:
        env = [{"tipo": "parede", "area_m2": per * pd / 2 - aw, "U": U["parede"]}, {"tipo": "parede", "area_m2": per * pd / 4, "U": U["parede"], "fronteira": "enu"},
               {"tipo": "porta", "area_m2": 2.0, "U": 2.5, "fronteira": "enu"}]
        if p.get("posicao") in ("ultimo", "unico"):
            env.append({"tipo": "cobertura", "area_m2": impl, "U": U["cobertura"]})
        if p.get("posicao") in ("res_do_chao", "unico"):
            env.append({"tipo": "pavimento", "area_m2": impl, "U": U["pavimento"], "fronteira": "enu"})
    for o, f in (("S", 0.35), ("E", 0.2), ("O", 0.25), ("N", 0.2)):
        env.append({"tipo": "envidracado", "area_m2": aw * f, "U": U["envidracado"], "orientacao": o, "g": 0.75 if obra != "existente" or ano > 1990 else 0.85})
    hyp.append(f"envolvente-tipo ({tipo}, {ap:.0f} m², {piso} piso(s), envidraçados {aw:.1f} m² a S 35 % / E 20 % / O 25 % / N 20 %, U {'≈ 85 % do Umáx da Portaria 138-I' if obra != 'existente' else 'por defeito da época ' + _epoca(ano)})")
    return env


def calcular(p: dict) -> dict:
    p = dict(p or {})
    hyp: list[str] = ["pré-certificado indicativo (metodologia REH): não substitui o certificado energético emitido por Perito Qualificado (ADENE)"]
    hyp += [str(h) for h in p.get("hipoteses_entrada") or []]      # origem dos dados indicada por quem chama (p. ex. leitura da planta)
    ap = float(p.get("area_util_m2") or 0)
    if ap <= 0:
        raise ValueError("area_util_m2 obrigatória")
    pd = float(p.get("pe_direito_m") or 2.6)
    tipo = p.get("tipo") or "moradia"
    obra = p.get("obra") or "existente"
    if obra not in ("nova", "grande_renovacao", "existente"):
        raise ValueError("obra: nova, grande_renovacao ou existente")
    ano = int(p.get("ano_construcao") or (2026 if obra == "nova" else 1980))
    c = clima(p.get("concelho"), p.get("nuts"), p.get("altitude_m"))
    ri = c["ri"]
    ra = c["regiao"] != "continente"
    umax_t, uw_max = (UMAX_ACORES, UW_MAX_ACORES) if c["regiao"] == "acores" else (UMAX, UW_MAX)
    uref_t, uref_int_t = (UREF_RA, UREF_INT_RA) if ra else (UREF, UREF_INT)
    if c.get("aviso"):
        hyp.append(c["aviso"])
    env = p.get("envolvente") or _envolvente_tipo(p, hyp)
    inercia = p.get("inercia") or ("media" if tipo == "moradia" or ano < 1990 else "forte")
    a = A_INERCIA[inercia]
    # ---- transmissão
    Htr = Htr_ref = Htr_opaco = 0.0
    aw_tot = sum(float(e["area_m2"]) for e in env if e["tipo"] == "envidracado")
    f_ref_vidro = min(1.0, 0.20 * ap / aw_tot) if aw_tot else 1.0      # referência : envidraçados limitados a 20 % de Ap
    ctl = []
    for e in env:
        t = e["tipo"]
        A = float(e["area_m2"])
        fr = e.get("fronteira") or "exterior"
        btr = float(e["btr"]) if e.get("btr") is not None else BTR.get(fr, 1.0)
        U = float(e["U"]) if e.get("U") is not None else U_DEFEITO[_epoca(ano)].get(t, 2.5)
        if A < 0:
            raise ValueError(f"área negativa no elemento {t}: reduzir a área envidraçada ou indicar a envolvente")
        Htr += btr * U * A
        if t not in ("envidracado", "porta"):
            Htr_opaco += btr * U * A
        # referência
        if t == "envidracado":
            uref = uref_t["envidracado"][ri]
        elif t in uref_t:
            uref = (uref_int_t if (fr in ("enu", "adjacente") and btr <= 0.7) else uref_t)[t][ri]
        else:
            uref = U
        if t == "envidracado":
            A_ref = A * f_ref_vidro
            Htr_ref += btr * uref * A_ref + btr * uref_t["parede"][ri] * (A - A_ref)
        else:
            Htr_ref += btr * uref * A
        # requisitos (obra nova / grande renovação, elementos novos ou renovados)
        if obra != "existente":
            if t == "envidracado":
                ctl.append({"ref": f"Uw,máx vão envidraçado {e.get('orientacao') or ''} (Portaria 138-I)", "exigencia": f"Uw ≤ {uw_max[ri]:.2f}",
                            "valor": f"{U:.2f}", "ok": U <= uw_max[ri] + 1e-9, "taux": U / uw_max[ri], "lib": f"Uw envidraçado {e.get('orientacao') or ''}".strip()})
            elif t in umax_t:
                lim = (UMAX_INT if (fr in ("enu", "adjacente") and btr <= 0.7) else umax_t)[t][ri]
                ctl.append({"ref": f"Umáx {t} ({fr}) — Portaria 138-I", "exigencia": f"U ≤ {lim:.2f} W/(m².°C)", "valor": f"{U:.2f}", "ok": U <= lim + 1e-9, "taux": U / lim,
                            "lib": f"U {t}" + (f" ({fr})" if fr != "exterior" else "")})
    # pontes térmicas lineares
    if p.get("pontes_termicas_w_c") is not None:
        hp = float(p["pontes_termicas_w_c"])
    else:
        hp = (0.35 if obra != "existente" else 0.0) * ap      # existentes : majoração de 35 % do U (aplicada abaixo)
        if obra == "existente":
            if not p.get("envolvente"):
                Htr += 0.35 * Htr_opaco
            hyp.append("existente: pontes térmicas planas e lineares consideradas por majoração de 35 % do U (Despacho 12935-B/2023)" if not p.get("envolvente")
                       else "pontes térmicas lineares não indicadas (desprezadas)")
        else:
            hyp.append("pontes térmicas lineares: Σψ·B ≈ 0,35 W/°C por m² de área útil (soluções correntes com isolamento contínuo)")
    Htr += hp
    Htr_ref += 0.50 * 4 * math.sqrt(ap) * 1.5 + 0.20 * 4.5 * min(aw_tot, 0.2 * ap) / 1.8      # ψref fachada/pavimentos/cobertura 0,50 + caixilharia 0,20
    # ---- ventilação
    rph = float(p.get("rph") or (0.6 if obra != "existente" else (1.0 if ano < 1990 else 0.7)))
    if not p.get("rph"):
        hyp.append(f"taxa de renovação de ar Rph = {rph:g} h⁻¹ (valor por defeito)")
    eta_rc = float(p.get("recuperador_eta") or 0)
    bve = 1 - eta_rc if eta_rc else 1.0
    Hve = 0.34 * rph * ap * pd * bve
    rph_ref = min(0.6, max(0.5, rph))
    Hve_ref = 0.34 * rph_ref * ap * pd
    # ---- inverno
    GD, M = c["GD"], c["M"]
    Qtr = 0.024 * GD * Htr
    Qve = 0.024 * GD * Hve
    Qint = 0.72 * 4 * M * ap
    Qsol = 0.0
    for e in env:
        if e["tipo"] != "envidracado":
            continue
        o = (e.get("orientacao") or "S").upper().replace("W", "O")
        fs = float(e.get("Fs") or 0.9)
        fg = float(e.get("Fg") or 0.65)
        g = float(e.get("g") or 0.75) * 0.9
        Qsol += c["Gsul"] * max(0.27, XJ.get(o, 0.56) * fs) * float(e["area_m2"]) * fg * g * M
    gamma = (Qint + Qsol) / (Qtr + Qve)
    eta_i = _eta(gamma, a)
    Nic = max(0.0, (Qtr + Qve - eta_i * (Qint + Qsol)) / ap)
    Qtr_r = 0.024 * GD * Htr_ref
    Qve_r = 0.024 * GD * Hve_ref
    Qsol_r = c["Gsul"] * 0.146 * 0.15 * ap * M
    Ni = max(5.0, (Qtr_r + Qve_r - 0.6 * (Qint + Qsol_r)) / ap)
    # ---- verão
    dth = 25 - c["theta_v"]
    Htr_v = Htr - sum((BTR.get(e.get("fronteira") or "exterior", 1.0)) * float(e.get("U") or 0) * float(e["area_m2"]) for e in env if (e.get("fronteira") == "adjacente"))
    Qtr_v = Htr_v * dth * 2928 / 1000
    Qve_v = 0.34 * max(0.6, rph) * ap * pd * dth * 2928 / 1000
    Qint_v = 4 * ap * 2928 / 1000
    Qsol_v = 0.0
    for e in env:
        o = (e.get("orientacao") or ("H" if e["tipo"] == "cobertura" else "S")).upper().replace("W", "O")
        I = c["Isol"].get(o, c["Isol"]["S"])
        if e["tipo"] == "envidracado":
            fmv = {"N": 0.9, "NE": 0.6, "NO": 0.6, "E": 0.4, "O": 0.4, "SE": 0.6, "SO": 0.6, "S": 0.7, "H": 0.0}.get(o, 0.6)
            gt = float(e.get("g") or 0.75)
            g_disp = float(e.get("g_dispositivo") or (0.07 if e.get("estore") is not False else gt))
            gv = fmv * g_disp + (1 - fmv) * gt * 0.85
            Qsol_v += I * float(e.get("Fs_v") or 0.9) * float(e["area_m2"]) * float(e.get("Fg") or 0.65) * gv
        elif e["tipo"] in ("parede", "cobertura") and (e.get("fronteira") or "exterior") == "exterior":
            Qsol_v += I * 0.5 * float(e.get("U") or 0.5) * float(e["area_m2"]) * 0.04
    Qg_v = Qint_v + Qsol_v
    Ql_v = Qtr_v + Qve_v
    gv_ = Qg_v / Ql_v if Ql_v > 0 else -1
    if Ql_v > 0:
        eta_v = _eta(gv_, a)
        Nvc = max(0.0, (1 - eta_v) * Qg_v / ap)
    else:   # θext,v ≥ 25 °C : a envolvente também ganha calor (η = 1/γ → Nvc = (Qg − Ql)/Ap)
        eta_v = 0.0
        Nvc = max(0.0, (Qg_v - Ql_v) / ap)
    eta_vr = min(0.90, 0.52 + 0.22 * math.log(dth)) if dth > 1 else 0.45 if dth > 0 else 0.30
    Nv = max(2.0, (1 - eta_vr) * (11.712 + 0.086 * c["Isol"]["H"]))
    # ---- AQS
    tip = int(p.get("tipologia") if p.get("tipologia") is not None else max(1, round(ap / 30)))
    n_oc = OCUPANTES.get(tip, tip)
    litros = 40 if tipo == "moradia" else 30
    Qa = litros * n_oc * 4187 * 35 * 365 / 3.6e6
    # ---- energia primária
    sa = p.get("aquecimento") or {}
    sv = p.get("arrefecimento") or {}
    sq = p.get("aqs") or {}
    ka = sa.get("tipo") or "resistencia_eletrica"
    kq = sq.get("tipo") or ("termoacumulador" if not p.get("rede_gas") else "caldeira_gas")
    if ka not in AQUEC or kq not in AQS:
        raise ValueError("sistema de aquecimento ou AQS desconhecido")
    va, ea, ea_ref = AQUEC[ka]
    ea = float(sa.get("eficiencia") or ea)
    vq, eq, eq_ref = AQS[kq]
    eq = float(sq.get("eficiencia") or eq)
    ev = float(sv.get("eer") or 3.0)
    delta = 0 if eta_v > eta_vr else 1
    Wvm = (0.3 * (rph * ap * pd) * 8760 / 1000) if p.get("ventilacao_mecanica") else 0.0
    eren = float(p.get("renovavel_kwh") or 0) + (float(sq.get("solar_kwh") or 0))
    Ntc = (Nic / ea * FPU[va] + delta * Nvc / ev * 2.5 + Qa / ap / eq * FPU[vq] + Wvm / ap * 2.5 - eren / ap * (2.5 if p.get("renovavel_tipo") == "fotovoltaico" else 1.0))
    Ntc = max(0.0, Ntc)
    usos = {"aquecimento": Nic / ea * FPU[va], "arrefecimento": delta * Nvc / ev * 2.5, "aqs": Qa / ap / eq * FPU[vq], "ventilacao": Wvm / ap * 2.5,
            "renovavel": eren / ap * (2.5 if p.get("renovavel_tipo") == "fotovoltaico" else 1.0)}
    Nt = Ni / ea_ref * FPU[va] + Nv / 3.0 * 2.5 + Qa / ap / eq_ref * FPU[vq]
    R = Ntc / Nt if Nt else 0.0
    # RenHab : renovável para autoconsumo (térmico Fpu 1, fotovoltaico Fpu 2,5) + energia ambiente da bomba de calor de AQS (SPF > 2,5)
    amb = Qa * (1 - 1 / eq) if (kq == "bomba_calor" and eq > 2.5) else 0.0
    renhab = (eren * (2.5 if p.get("renovavel_tipo") == "fotovoltaico" else 1.0) + amb) / max(1e-9, Qa / eq * FPU[vq])
    classe = next(cl for lim, cl in CLASSES if R <= lim)
    if not sa.get("tipo"):
        hyp.append("sem sistema de aquecimento indicado: resistência elétrica (sistema por defeito, η = 1)")
    if not sq.get("tipo"):
        hyp.append(f"AQS por defeito: {kq}")
    hyp.append("eficiências de referência para Nt: mesmo tipo de sistema com eficiência de referência aproximada (Tab. 99 do Manual SCE não reproduzida)")
    # ---- requisitos globais
    if obra == "nova":
        lim_i = (0.75, 0.85, 0.90)[ri]
        ctl += [{"ref": "Nic/Ni (Despacho 6476-E, NZEB)", "exigencia": f"≤ {lim_i:.2f}", "valor": f"{Nic / Ni:.2f}", "ok": Nic / Ni <= lim_i + 1e-9,
                 "taux": Nic / Ni / lim_i, "lib": "Nic/Ni (aquecimento)"},
                {"ref": "Nvc/Nv", "exigencia": "≤ 1,00", "valor": f"{Nvc / Nv:.2f}", "ok": (Nvc <= Nv) if eta_vr < 0.9 else None,
                 "taux": Nvc / Nv, "lib": "Nvc/Nv (arrefecimento)"},
                {"ref": "Classe energética mínima (NZEB)", "exigencia": "≥ A (RNt ≤ 0,50)", "valor": f"{classe} (RNt {R:.2f})", "ok": R <= 0.50 + 1e-9,
                 "taux": R / 0.50, "lib": "Ntc/Nt (classe ≥ A)"},
                {"ref": "Renovável (RenHab)", "exigencia": "≥ 0,50 da energia primária para AQS", "valor": f"{renhab:.2f}", "ok": renhab >= 0.5 - 1e-9}]
    elif obra == "grande_renovacao":
        lim = None if ano < 1960 else 1.25 if ano <= 1990 else 1.15
        if lim:
            ctl += [{"ref": "Nic/Ni (grande renovação)", "exigencia": f"≤ {lim:.2f}", "valor": f"{Nic / Ni:.2f}", "ok": Nic / Ni <= lim + 1e-9,
                     "taux": Nic / Ni / lim, "lib": "Nic/Ni (aquecimento)"},
                    {"ref": "Nvc/Nv (grande renovação)", "exigencia": f"≤ {lim:.2f}", "valor": f"{Nvc / Nv:.2f}", "ok": (Nvc / Nv <= lim) if eta_vr < 0.9 else None,
                     "taux": Nvc / Nv / lim, "lib": "Nvc/Nv (arrefecimento)"}]
        ctl.append({"ref": "Classe energética mínima (grande renovação)", "exigencia": "≥ C (RNt ≤ 1,50)", "valor": f"{classe} (RNt {R:.2f})", "ok": R <= 1.50 + 1e-9,
                    "taux": R / 1.50, "lib": "Ntc/Nt (classe ≥ C)"})
    if obra != "existente":
        ctl.append({"ref": "Ventilação (Manual SCE 2023 §9.2.1)", "exigencia": "Rph ≥ 0,50 h⁻¹", "valor": f"{rph:g} h⁻¹", "ok": rph >= 0.5 - 1e-9})
    return {"clima": c, "area_util": ap, "tipo": tipo, "obra": obra, "inercia": inercia, "Htr": Htr, "Hve": Hve, "Htr_ref": Htr_ref,
            "Qtr": Qtr, "Qve": Qve, "Qint": Qint, "Qsol": Qsol, "eta_i": eta_i, "Nic": Nic, "Ni": Ni, "Nvc": Nvc, "Nv": Nv, "eta_v": eta_v,
            "Qa": Qa, "ocupantes": n_oc, "RenHab": renhab, "Ntc": Ntc, "Nt": Nt, "RNt": R, "classe": classe, "aquecimento": ka, "aqs": kq,
            "envolvente": env, "controles": ctl, "hipoteses": hyp, "rph": rph, "ntc_usos": usos}


def note(p: dict) -> dict:
    from . import notes
    r = calcular(p)
    f, W = notes._f, notes.W
    c = r["clima"]
    rows = [["Classe energética (RNt = Ntc/Nt)", f"{r['classe']} ({r['RNt']:.2f})"],
            ["Nic / Ni (aquecimento)", f"{r['Nic']:.1f} / {r['Ni']:.1f} kWh/(m².ano)"], ["Nvc / Nv (arrefecimento)", f"{r['Nvc']:.1f} / {r['Nv']:.1f} kWh/(m².ano)"],
            ["Qa (AQS)", f"{f(r['Qa'])} kWh/ano ({r['ocupantes']} ocupantes)"], ["Ntc / Nt (energia primária)", f"{r['Ntc']:.1f} / {r['Nt']:.1f} kWhEP/(m².ano)"],
            ["Htr / Hve", f"{r['Htr']:.1f} / {r['Hve']:.1f} W/°C (Rph {r['rph']:g} h⁻¹)"], ["Sistemas", f"aquecimento {r['aquecimento']} · AQS {r['aqs']}"]]
    TIPO_PT = {"parede": "Parede", "cobertura": "Cobertura", "pavimento": "Pavimento", "porta": "Porta", "envidracado": "Envidraçado"}
    env = [[TIPO_PT.get(e["tipo"], e["tipo"]) + (f" {e.get('orientacao')}" if e.get("orientacao") else ""), f(float(e["area_m2"]), 1), f"{float(e.get('U') or 0):.2f}", e.get("fronteira") or "exterior"]
           for e in r["envolvente"]]
    from . import graficos as G
    v = lambda x, d=2: f"{x:.{d}f}".replace(".", ",")
    # escala de classes energéticas (RNt) com a classe do projeto
    plages, lo = [], None
    for lim, cl in CLASSES:
        plages.append((cl, f"≤ {v(lim)}" if lo is None else (f"> {v(lo)}" if lim == math.inf else f"{v(lo + 0.01)} a {v(lim)}")))
        lo = lim
    lab = G.etiquette(plages, {r["classe"]: f"Projeto · RNt {v(r['RNt'])}"}, "Classe energética — RNt = Ntc/Nt", couleurs=G.REH_COULEURS)
    u = r["ntc_usos"]
    parts = [("Aquecimento", u["aquecimento"]), ("Arrefecimento", u["arrefecimento"]), ("AQS", u["aqs"]), ("Ventilação mecânica", u["ventilacao"])]
    don = G.donut(parts, "Energia primária por uso (antes de renováveis)", v(sum(p[1] for p in parts), 0), "kWhEP/(m².ano)")
    graf_cl = ("chart", G.cote_a_cote(lab, don), "Classe = posição de RNt na escala do SCE (Despacho 6476-H/2021)"
               + (f"; dedução de renováveis {v(u['renovavel'], 1)} kWhEP/(m².ano)." if u["renovavel"] > 0 else "."))
    import re
    num = lambda s: (re.findall(r"\d+[.,]\d+", s) or [s])[-1].replace(".", ",")
    tx = [(x["lib"], x["taux"], f"{num(x['valor'])} / {num(x['exigencia'])}") for x in r["controles"] if x.get("taux") is not None]
    if tx:
        graf_j = ("chart", G.jauges(tx, "Indicadores e coeficientes U relativos ao requisito"), "Verde ≤ 90 % do requisito, âmbar entre 90 e 100 %, vermelho acima.")
    else:
        graf_j = ("chart", G.jauges([("Nic/Ni (aquecimento)", r["Nic"] / r["Ni"] if r["Ni"] else None, f"{v(r['Nic'], 1)} / {v(r['Ni'], 1)}"),
                                     ("Nvc/Nv (arrefecimento)", r["Nvc"] / r["Nv"] if r["Nv"] else None, f"{v(r['Nvc'], 1)} / {v(r['Nv'], 1)}"),
                                     ("Ntc/Nt (energia primária)", r["RNt"], f"{v(r['Ntc'], 1)} / {v(r['Nt'], 1)}")],
                                    "Necessidades do edifício relativas ao edifício de referência"),
                  "Edifício existente: sem requisitos mínimos; 100 % = desempenho do edifício de referência REH.")
    perd = {}
    for e in r["envolvente"]:
        fr = e.get("fronteira") or "exterior"
        btr = float(e["btr"]) if e.get("btr") is not None else BTR.get(fr, 1.0)
        k = {"parede": "Paredes", "cobertura": "Cobertura", "pavimento": "Pavimento", "envidracado": "Envidraçados", "porta": "Portas"}.get(e["tipo"], e["tipo"].capitalize())
        perd[k] = perd.get(k, 0.0) + btr * float(e.get("U") or 0) * float(e["area_m2"])
    pt_ = r["Htr"] - sum(perd.values())
    if pt_ > 0.05:
        perd["Pontes térmicas"] = pt_
    perd["Renovação de ar"] = r["Hve"]
    graf_p = ("chart", G.barres_h(sorted(perd.items(), key=lambda kv: -kv[1]), "Onde se perde o calor (coeficientes de transferência)", "W/°C", couleur=G.SERIES[1]),
              "As barras mais longas indicam as intervenções de reabilitação mais eficazes.")
    kp = [{"label": "Classe energética", "value": r["classe"], "ok": (r["RNt"] <= (0.50 if r["obra"] == "nova" else 1.50) + 1e-9) if r["obra"] != "existente" else "x"},
          {"label": "Ntc / Nt (RNt)", "value": f"{v(r['Ntc'], 0)} / {v(r['Nt'], 0)}", "unit": f"({v(r['RNt'])})"},
          {"label": "Nic / Ni (kWh/(m².ano))", "value": f"{v(r['Nic'], 0)} / {v(r['Ni'], 0)}", "ok": next((x["ok"] for x in r["controles"] if x["ref"].startswith("Nic")), "x")},
          {"label": "Nvc / Nv (kWh/(m².ano))", "value": f"{v(r['Nvc'], 1)} / {v(r['Nv'], 1)}", "ok": next((x["ok"] for x in r["controles"] if x["ref"].startswith("Nvc")), "x")}]
    blocs = [("kpis", kp), ("p", "Pré-certificado INDICATIVO segundo a metodologia do REH — não substitui o certificado energético emitido por Perito Qualificado (SCE / ADENE)."),
             ("h2", "1. Clima"), ("p", f"{c['nuts']} · altitude {c['altitude_m']:.0f} m · GD {c['GD']:.0f} °C.dia · M {c['M']:.1f} meses · θext,v {c['theta_v']:.1f} °C · "
                                       f"zonas {c['zona_i']} / {c['zona_v']}"),
             ("h2", "2. Indicadores"), graf_cl, ("table", ["Indicador", "Valor"], rows, [60 * W, 110 * W]), graf_j,
             ("h2", "3. Envolvente"), ("table", ["Elemento", "A m²", "U", "Fronteira"], env, [45 * W, 25 * W, 20 * W, 40 * W]), graf_p]
    if r["controles"]:
        blocs += [("h2", "4. Requisitos (Portaria 138-I/2021, Despacho 6476-E/2021)"), ("controls", [{"ref": x["ref"], "exigence": x["exigencia"], "valeur": x["valor"], "ok": x["ok"]} for x in r["controles"]])]
    titre = "Pré-certificado energético (REH, indicativo)"
    sous = f"{'Moradia' if r['tipo'] == 'moradia' else 'Apartamento'} {r['area_util']:.0f} m² · {c['nuts']} · classe {r['classe']}"
    pdf, png = notes.pdf(titre, sous, blocs, r["hipoteses"])
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": png}
