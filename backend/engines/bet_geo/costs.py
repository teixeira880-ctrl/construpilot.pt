"""Preços de referência (Portugal, 2026, sem IVA) e linhas do orçamento a partir das QUANTIDADES medidas na geometria real.

Os preços são de referência (marcados «estimate» no orçamento): a empresa substitui-os pela sua biblioteca. Cada linha
diz de onde vem a quantidade (medida na planta, calculada pelo motor ou hipótese).
"""
from __future__ import annotations

import math

PRICES = {   # chave: (preço unitário €, unidade)
    "betao_c30_laje": (125.0, "m³"), "betao_c30_vigas": (135.0, "m³"), "betao_c30_pilares": (145.0, "m³"),
    "betao_sapatas": (115.0, "m³"), "betao_limpeza": (95.0, "m³"), "betao_vigas_fundacao": (125.0, "m³"),
    "betao_muro": (150.0, "m³"), "laje_terrea": (120.0, "m³"), "aco_a500": (1.35, "kg"),
    "cofragem_laje": (22.0, "m²"), "cofragem_vigas": (28.0, "m²"), "cofragem_pilares": (30.0, "m²"),
    "escavacao": (12.0, "m³"), "tout_venant": (30.0, "m³"), "impermeab_muro": (28.0, "m²"),
    "cobertura_invertida": (58.0, "m²"),
    "alvenaria_11": (22.0, "m²"), "alvenaria_15": (26.0, "m²"), "alvenaria_20": (30.0, "m²"), "alvenaria_25": (34.0, "m²"),
    "reboco_interior": (14.0, "m²"), "pintura": (7.5, "m²"), "teto_gesso": (28.0, "m²"),
    "pav_flutuante": (36.0, "m²"), "pav_ceramico": (46.0, "m²"), "pav_betonilha": (16.0, "m²"), "rodape": (9.0, "m"),
    "betonilha_regularizacao": (14.0, "m²"), "revest_ceramico_parede": (42.0, "m²"),
    "porta_entrada": (1800.0, "u"), "porta_interior": (450.0, "u"), "porta_garagem": (360.0, "m²"),
    "loicas_is": (1250.0, "u"), "cozinha_ligacoes": (650.0, "u"),
    "quadro_eletrico": (950.0, "u"), "ponto_tomada": (58.0, "u"), "ponto_luz": (52.0, "u"), "circuito_dedicado": (140.0, "u"),
    "ited": (1500.0, "vg"), "terra_protecao": (450.0, "vg"),
    "agua_aparelho": (230.0, "u"), "esgoto_aparelho": (190.0, "u"), "ramal_agua": (650.0, "vg"), "ramal_esgoto": (900.0, "vg"),
    "piso_radiante": (46.0, "m²"), "coletor_piso": (520.0, "u"), "bc_kw": (850.0, "kW"), "bc_instalacao": (1600.0, "vg"),
    "aqs_bc_200": (2400.0, "u"), "termoacumulador_200": (650.0, "u"), "caldeira_condensacao": (3300.0, "u"),
    "radiador_eletrico_kw": (160.0, "kW"), "pv_kwp": (1450.0, "kWp"),
    "grelha_admissao": (45.0, "u"), "extrator_is": (190.0, "u"), "exaustor_cozinha_conduta": (380.0, "u"),
    "vmc_dupla_fluxo": (5200.0, "vg"),
    "estaleiro_pct": (0.03, "%"), "seguranca_pct": (0.015, "%"),
}


def etics_price(mm: int) -> float:          # EPS λ 0,036 com acabamento — sobe com a espessura
    return round(38.0 + 0.25 * mm, 2)


def window_price(uw: float) -> float:        # alumínio: Uw 2,4 sem corte térmico; 1,6 com RPT; ≤ 1,1 vidro triplo
    return 270.0 if uw >= 2.2 else 390.0 if uw >= 1.4 else 540.0


def floor_ins_price(mm: int) -> float:       # XPS sob o pavimento
    return round(6.0 + 0.20 * mm, 2)


def roof_ins_price(mm: int) -> float:        # acréscimo de XPS na cobertura invertida
    return round(0.22 * mm, 2)


def line(lot, label, qty, key, note="", pu=None, unit=None, vat=23):
    p, u = PRICES.get(key, (0.0, "u"))
    return {"lot": lot, "label": label, "qty": round(float(qty), 2), "unit": unit or u, "pu": round(float(pu if pu is not None else p), 2),
            "note": note, "vat": vat}


def structure_lines(R) -> list[dict]:
    """Quantidades do motor de estrutura (R.quantities) → linhas com preço."""
    out = []
    keymap = [("Cofragem de laje", "cofragem_laje"), ("Cofragem de vigas", "cofragem_vigas"), ("Cofragem de pilares", "cofragem_pilares"),
              ("Laje maciça", "betao_c30_laje"), ("Vigas de cobertura", "betao_c30_vigas"), ("Pilares", "betao_c30_pilares"),
              ("Sapatas", "betao_sapatas"), ("Betão de limpeza", "betao_limpeza"), ("Vigas de fundação", "betao_vigas_fundacao"),
              ("Muro de suporte", "betao_muro"), ("Impermeabilização + drenagem", "impermeab_muro"), ("Escavação", "escavacao"),
              ("Laje térrea", "laje_terrea"), ("Enrocamento", "tout_venant"), ("cobertura invertida", "cobertura_invertida")]
    steel = 0.0
    for q in R.quantities:
        if q["lote"] in ("Alvenarias", "Revestimentos"):
            continue                                   # medidos de novo com a envolvente/divisões (paredes e acabamentos)
        key = next((k for s, k in keymap if s.lower() in q["item"].lower()), None)
        if key is None:
            continue
        out.append(line(q["lote"], q["item"], q["qtd"], key, q.get("nota") or "quantidade calculada sobre a geometria real"))
        steel += q.get("aco_kg") or 0.0
    if steel:
        out.append(line("Estrutura", "Aço A500 NR em varão (todas as peças, incl. sobreposições)", steel, "aco_a500",
                        "soma das armaduras calculadas por peça"))
    return out


def with_site(lines: list[dict]) -> list[dict]:
    base = sum(l["qty"] * l["pu"] for l in lines)
    return [line("Estaleiro e segurança", "Montagem, manutenção e desmontagem do estaleiro", 1, "", pu=round(base * PRICES["estaleiro_pct"][0], 2),
                 unit="vg", note="3 % dos trabalhos"),
            line("Estaleiro e segurança", "Plano de segurança e saúde, proteções coletivas", 1, "", pu=round(base * PRICES["seguranca_pct"][0], 2),
                 unit="vg", note="1,5 % dos trabalhos")] + lines


def total(lines: list[dict]) -> float:
    return round(sum(l["qty"] * l["pu"] for l in lines), 2)


def _interior_wall_len(b, lay) -> tuple[float, str]:
    read = sum(w.length for w in b.walls if not w.exterior and w.retained_height <= 0)
    rooms = [r for r in lay.rooms if r.type != "exterior" and r.area > 0]
    est = max(0.0, 0.5 * sum(4 * (r.area ** 0.5) for r in rooms) - 0.5 * b.footprint.exterior.length)
    if est > read * 1.15:
        return est, f"comprimento estimado pelas divisões do quadro ({est:.0f} m; lidas {read:.0f} m)".replace(".", ",")
    return read, "comprimento das paredes interiores lidas na planta"


def quote_lines(b, R, lay, esp) -> list[dict]:
    """Orçamento completo: estrutura (motor) + arquitetura e acabamentos (divisões, envolvente, mapa de vãos) + especialidades."""
    from .rooms import _room_of
    env, sol = esp["env"], esp["solution"]
    L = structure_lines(R)
    H, hsp = env.H, env.hsp
    glaz_all = sum(w.area for w in lay.windows) if lay.windows else env.glazing_total
    ext_gross = b.footprint.exterior.length * H + sum(h.length for h in b.footprint.interiors) * H
    ext_opaque = max(0.25 * ext_gross, ext_gross - glaz_all - 2.2)
    L.append(line("Alvenarias", "Alvenaria exterior em tijolo térmico 20 cm (fachada medida − vãos)", ext_opaque, "alvenaria_20",
                  f"contorno real {b.footprint.exterior.length:.1f} m × {H:.2f} m, vãos {glaz_all:.1f} m² deduzidos".replace(".", ",")))
    ilen, isrc = _interior_wall_len(b, lay)
    L.append(line("Alvenarias", "Paredes divisórias em tijolo 11 cm", ilen * hsp, "alvenaria_11", isrc))
    L.append(line("Isolamento térmico", f"ETICS — EPS {sol.etics} mm (λ 0,036), rede e acabamento areado", env.wall_ext + env.wall_enu * 0.0,
                  "", pu=etics_price(sol.etics), unit="m²", note=f"espessura escolhida pela análise custo-benefício REH (U = {sol.U['parede']:.2f})".replace(".", ",")))
    if env.wall_enu > 0.5:
        L.append(line("Isolamento térmico", "Isolamento 80 mm nas paredes para a garagem / zona técnica", env.wall_enu, "", pu=round(etics_price(80) * 0.8, 2),
                      unit="m²", note="paredes entre espaço aquecido e não útil"))
    L.append(line("Isolamento térmico", f"Reforço de XPS na cobertura invertida — {sol.roof} mm", R.slab["area"], "", pu=roof_ins_price(sol.roof), unit="m²",
                  note=f"U cobertura = {sol.U['cobertura']:.2f}".replace(".", ",")))
    L.append(line("Isolamento térmico", f"XPS {sol.floor} mm sob o pavimento térreo aquecido", env.floor, "", pu=floor_ins_price(sol.floor), unit="m²",
                  note=f"U pavimento = {sol.U['pavimento']:.2f}".replace(".", ",")))
    # acabamentos por divisão
    rooms = [r for r in lay.rooms if r.type != "exterior" and r.area > 0]
    wet = [r for r in rooms if r.type in ("casa_de_banho", "cozinha", "lavandaria")]
    raw_fl = [r for r in rooms if r.type in ("garagem", "tecnico")]
    dry = [r for r in rooms if r not in wet and r not in raw_fl]
    a_all = sum(r.area for r in rooms)
    L.append(line("Pavimentos", "Betonilha de regularização (sobre o piso radiante / isolamento)", a_all, "betonilha_regularizacao", "área útil do quadro de áreas"))
    if dry:
        L.append(line("Pavimentos", "Pavimento flutuante de carvalho (salas, quartos, circulações)", sum(r.area for r in dry), "pav_flutuante",
                      ", ".join(sorted({r.name for r in dry}))[:300]))
        L.append(line("Pavimentos", "Rodapé em MDF", sum(4 * r.area ** 0.5 for r in dry) * 0.9, "rodape", "perímetro das divisões secas − portas"))
    if wet:
        L.append(line("Pavimentos", "Pavimento cerâmico 60×60 (zonas húmidas)", sum(r.area for r in wet), "pav_ceramico",
                      ", ".join(sorted({r.name for r in wet}))[:300]))
        L.append(line("Revestimentos", "Revestimento cerâmico de paredes (IS a toda a altura, cozinha/lavandaria 1,20 m)",
                      sum(4 * r.area ** 0.5 * (hsp if r.type == "casa_de_banho" else 1.2) for r in wet), "revest_ceramico_parede"))
    if raw_fl:
        L.append(line("Pavimentos", "Betonilha afagada (garagem, zona técnica)", sum(r.area for r in raw_fl), "pav_betonilha"))
    wall_int = (2 * ilen + b.footprint.exterior.length) * hsp - glaz_all
    L.append(line("Revestimentos", "Reboco interior areado fino", wall_int, "reboco_interior", "faces interiores das paredes"))
    L.append(line("Revestimentos", "Pintura de paredes e tetos (tinta plástica, 2 demãos)", wall_int + a_all, "pintura"))
    L.append(line("Tetos", "Teto em gesso cartonado (hidrófugo nas zonas húmidas)", sum(r.area for r in rooms if r.heated), "teto_gesso"))
    # vãos
    if lay.windows:
        g_extra = 40.0 if sol.g < 0.4 else 0.0
        for w in lay.windows:
            r = _room_of(w.room, lay.rooms)
            if r is not None and r.type == "garagem":
                L.append(line("Caixilharias", f"{w.name} — porta seccionada de garagem {w.w:.2f} × {w.h:.2f} m".replace(".", ","), w.area, "porta_garagem",
                              w.room))
            else:
                L.append(line("Caixilharias", f"{w.name} — alumínio c/ corte térmico, Uw {sol.uw:g}, vidro g {sol.g:g} — {w.w:.2f} × {w.h:.2f} m".replace(".", ","),
                              w.area, "", pu=window_price(sol.uw) + g_extra, unit="m²", note=w.room))
    elif env.glazing_total:
        L.append(line("Caixilharias", f"Caixilharia alumínio Uw {sol.uw:g}, vidro g {sol.g:g} (vãos medidos na fachada)".replace(".", ","), env.glazing_total,
                      "", pu=window_price(sol.uw), unit="m²", note="sem mapa de vãos: área dos troços de fachada sem parede (hipótese)"))
    L.append(line("Carpintarias", "Porta de entrada de segurança", 1, "porta_entrada"))
    n_int = max(1, len([r for r in rooms if r.type not in ("sala", "corredor")]))
    L.append(line("Carpintarias", "Portas interiores em MDF folheado, com aros e guarnições", n_int, "porta_interior", "uma por divisão fechada"))
    # sanitários e cozinha
    n_is = sum(1 for r in rooms if r.type == "casa_de_banho")
    if n_is:
        L.append(line("Equipamento sanitário", "Loiças sanitárias, base de duche e torneiras (por instalação sanitária)", n_is, "loicas_is"))
    if any(r.type == "cozinha" for r in rooms):
        L.append(line("Equipamento sanitário", "Ligações de cozinha (lava-loiça, máquinas)", 1, "cozinha_ligacoes"))
    # especialidades (motores calc_lots)
    mep = esp.get("mep") or {}
    el = mep.get("eletricidade") or {}
    if el:
        L += [line("Eletricidade (RTIEBT)", f"Quadro elétrico (alimentação {el.get('alimentacao', '')}), {len(el.get('circuitos') or [])} circuitos, "
                   f"{el.get('diferenciais', 0)} diferenciais 30 mA", 1, "quadro_eletrico", f"potência a contratar {el.get('potencia_contratada_kva', 0):.1f} kVA".replace(".", ",")),
              line("Eletricidade (RTIEBT)", "Pontos de tomada 16 A (incl. tubagem e cablagem)", el.get("tomadas", 0), "ponto_tomada", "por divisão — nota das especialidades"),
              line("Eletricidade (RTIEBT)", "Pontos de luz e comandos", el.get("pontos_luz", 0), "ponto_luz"),
              line("Eletricidade (RTIEBT)", "Circuitos dedicados (placa, forno, máquinas, bomba de calor)",
                   sum(1 for c in el.get("circuitos") or [] if c.get("familia") not in ("iluminacao", "tomadas")), "circuito_dedicado"),
              line("Eletricidade (RTIEBT)", "Elétrodo de terra e ligações equipotenciais", 1, "terra_protecao"),
              line("Telecomunicações", "Infraestrutura ITED (ATI, tubagem, tomadas)", 1, "ited")]
    can = mep.get("canalizacao") or {}
    if can:
        n = sum(int(d.get("n") or 0) for d in can.get("dispositivos") or [])
        L += [line("Águas e esgotos (DR 23/95)", f"Rede de água fria e quente (tubo AF {can.get('tubo_af', '')}, AQ {can.get('tubo_aq', '')})", n, "agua_aparelho",
                   "por dispositivo, incl. coletores e válvulas"),
              line("Águas e esgotos (DR 23/95)", f"Rede de drenagem (tubo de queda Ø{can.get('tubo_queda_mm', 110)}, coletor Ø{can.get('coletor_mm', 110)})", n,
                   "esgoto_aparelho", "por dispositivo, incl. caixas de visita"),
              line("Águas e esgotos (DR 23/95)", "Ramal de ligação de água e contador", 1, "ramal_agua"),
              line("Águas e esgotos (DR 23/95)", "Ramal de ligação de esgotos", 1, "ramal_esgoto")]
    pr, bc = mep.get("piso_radiante") or {}, mep.get("bomba_calor") or {}
    if sol.system == "bc":
        if pr:
            L.append(line("Aquecimento (EN 12831 / EN 1264)", f"Piso radiante — {pr.get('circuitos', 0)} circuitos, {pr.get('tubo_total_m', 0):.0f} m de tubo PE-RT 16×2",
                          sum(d["area_m2"] for d in pr.get("divisoes") or []), "piso_radiante", f"ida {pr.get('theta_ida', 0):.1f} °C".replace(".", ",")))
            L.append(line("Aquecimento (EN 12831 / EN 1264)", "Coletores de piso radiante com caixa e atuadores", pr.get("coletores", 1), "coletor_piso"))
        if bc:
            L.append(line("Aquecimento (EN 12831 / EN 1264)", f"Bomba de calor ar-água {bc.get('p_nominal_kw', 0):g} kW (classe {bc.get('classe_erp', '')})",
                          bc.get("p_nominal_kw", 0), "bc_kw", f"perdas de projeto {bc.get('perdas_kw', 0):.1f} kW a {bc.get('theta_e', 0):g} °C".replace(".", ",")))
            L.append(line("Aquecimento (EN 12831 / EN 1264)", "Instalação da bomba de calor, vaso de expansão, ligações", 1, "bc_instalacao"))
        L.append(line("AQS", "Bomba de calor de AQS 200 L", 1, "aqs_bc_200", "RenHab ≥ 0,50 (REH)"))
    elif sol.system == "caldeira":
        L.append(line("Aquecimento", "Caldeira a gás de condensação + radiadores", 1, "caldeira_condensacao"))
    else:
        L.append(line("Aquecimento", "Radiadores elétricos", round((mep.get("aquecimento") or {}).get("phi_total", 6000) / 1000, 1), "radiador_eletrico_kw"))
        L.append(line("AQS", "Termoacumulador 200 L", 1, "termoacumulador_200"))
    v = (esp.get("vent") or {}).get("ventilacao") or {}
    if v:
        L.append(line("Ventilação (Portaria 138-I)", "Grelhas de admissão autorreguláveis nos caixilhos (módulos 25 m³/h)",
                      sum(math.ceil(q / 25) for _, q in v.get("grelhas") or []), "grelha_admissao", f"caudal {v.get('caudal_m3h', 0):.0f} m³/h".replace(".", ",")))
        n_is = sum(1 for r in rooms if r.type in ("casa_de_banho", "lavandaria"))
        L.append(line("Ventilação (Portaria 138-I)", "Extração nas instalações sanitárias e lavandaria (conduta à cobertura)", n_is, "extrator_is"))
        L.append(line("Ventilação (Portaria 138-I)", "Exaustão da cozinha com conduta individual à cobertura", 1, "exaustor_cozinha_conduta"))
    return with_site([l for l in L if l["qty"] > 0])
