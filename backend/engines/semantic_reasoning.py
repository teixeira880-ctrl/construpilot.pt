"""SemanticReasoningEngine — le « cerveau métier » du moteur de métré Construpilot.

Entrée  : données géométriques brutes du pipeline Vision (polygones, textes OCR,
          cotes) regroupées en JSON.
Sortie  : éléments de structure typés et chiffrés (Pydantic strict), prêts à exporter.

Principe : couplage RÈGLES DURES (déductions mathématiques déterministes) + LLM
(classification sémantique OCR↔géométrie). Zéro hallucination : toute donnée manquante
pour un calcul déclenche une exception contrôlée (`MissingDataError`) portant des
`MissingDataRequest` — questions claires posées à l'utilisateur, JAMAIS une valeur devinée.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field

# ──────────────────────────────────────────────────────────────────────────────
# 1) STRUCTURATION STRICTE (Pydantic) — verrouille les I/O du LLM (extra interdit)
# ──────────────────────────────────────────────────────────────────────────────


class Armature(BaseModel):
    """Ferraillage d'un élément béton armé."""
    model_config = ConfigDict(extra="forbid")

    repere: str | None = None
    nuance: str | None = None                       # ex. "HA500"
    ratio_kg_m3: float | None = Field(None, ge=0)   # ratio de ferraillage (kg/m³)
    total_kg: float | None = Field(None, ge=0)      # tonnage déduit (ratio × volume)
    detail: str | None = None                       # ex. "4 HA12 + cadres HA6 e=20"
    confidence: float = Field(0.0, ge=0, le=1)


class FondationElement(BaseModel):
    """Élément de fondation / gros œuvre enterré (semelle, longrine, chaînage, poteau)."""
    model_config = ConfigDict(extra="forbid")

    type: str                                       # semelle_isolee|semelle_filante|longrine|chainage|poteau
    repere: str | None = None
    longueur_m: float | None = Field(None, ge=0)
    largeur_m: float | None = Field(None, ge=0)
    hauteur_m: float | None = Field(None, ge=0)     # hauteur/épaisseur coffrée
    nombre: int = Field(1, ge=1)
    volume_beton_m3: float | None = Field(None, ge=0)
    armature: Armature | None = None
    source_cotes: str | None = None                 # trace OCR ayant fourni les cotes
    confidence: float = Field(0.0, ge=0, le=1)
    a_verifier: bool = True


class MurSoubassement(BaseModel):
    """Mur de soubassement (parpaing/agglo ou voile béton) reposant sur fondation."""
    model_config = ConfigDict(extra="forbid")

    repere: str | None = None
    materiau: str                                   # ex. "Parpaing 20cm", "Voile béton 20cm"
    epaisseur_m: float | None = Field(None, ge=0)
    longueur_m: float | None = Field(None, ge=0)
    hauteur_m: float | None = Field(None, ge=0)
    niveau_assise_m: float | None = None            # ex. -1.30 (m / TN)
    surface_m2: float | None = Field(None, ge=0)
    volume_m3: float | None = Field(None, ge=0)
    hauteur_deduite: bool = False                   # True si hauteur calculée par règle dure
    confidence: float = Field(0.0, ge=0, le=1)
    a_verifier: bool = True


class MissingDataRequest(BaseModel):
    """Donnée indispensable absente du JSON d'entrée → question posée à l'UI.

    Le LLM (et le moteur) ont INTERDICTION de deviner ou de renvoyer 0 : on émet
    plutôt cette requête pour que l'humain fournisse la valeur manquante."""
    model_config = ConfigDict(extra="forbid")

    champ: str                                      # ex. "ratio_acier"
    element_repere: str | None = None
    question: str                                   # question claire pour l'utilisateur
    unite: str | None = None                        # ex. "kg/m³"
    raison: str | None = None


class ReasoningResult(BaseModel):
    """Sortie complète du raisonnement métier."""
    model_config = ConfigDict(extra="forbid")

    fondations: list[FondationElement] = Field(default_factory=list)
    murs: list[MurSoubassement] = Field(default_factory=list)
    missing_data: list[MissingDataRequest] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)   # trace lisible des règles appliquées
    notes: str | None = None


class MissingDataError(Exception):
    """Exception contrôlée : des données indispensables manquent pour un métré fiable.

    Porte la liste des `MissingDataRequest` ET le résultat PARTIEL déjà déduit
    (les déductions déterministes restent valides et consultables par l'UI)."""

    def __init__(self, requests: list[MissingDataRequest], partial: ReasoningResult):
        self.requests = requests
        self.partial = partial
        super().__init__(f'{len(requests)} dado(s) em falta para uma medição fiável.')


# ──────────────────────────────────────────────────────────────────────────────
# 2) MOTEUR DE RÈGLES HEURISTIQUES PRÉ-LLM (hardcodé, déterministe)
# ──────────────────────────────────────────────────────────────────────────────


class CivilEngineeringRules:
    """Déductions mathématiques du génie civil appliquées AVANT le LLM.

    Ces règles sont déterministes et traçables : elles ne devinent jamais, elles
    calculent à partir de données présentes (cotes de niveau, épaisseurs lues)."""

    # "Assise à -1.30m TN", "assise -1,30 m", "fond de fouille -1.30"
    _ASSISE_RE = re.compile(
        r"(?:assise|fond\s+de\s+fouille|arase\s+inf[ée]rieure)[^\-\d]*(-?\d+(?:[.,]\d+)?)\s*m",
        re.IGNORECASE)
    # "PP e=20", "PP s=20", "parpaing 20", "agglo 20" → épaisseur en cm
    _PARPAING_RE = re.compile(
        r"(?:\bPP\b|parpaing|agglo|bloc\s*b[ée]ton)[^0-9]*(?:[es]\s*=\s*)?(\d{2,3})",
        re.IGNORECASE)
    # "voile 20", "mur béton ep 20", "BA 18"
    _VOILE_RE = re.compile(
        r"(?:voile|mur\s+b[ée]ton|\bBA\b)[^0-9]*(?:ep\.?\s*=?\s*)?(\d{2,3})",
        re.IGNORECASE)

    @staticmethod
    def parse_assise_level(text: str) -> float | None:
        """Extrait le niveau d'assise signé (m) depuis l'OCR. Ex. 'Assise -1.30m' → -1.30."""
        if not text:
            return None
        m = CivilEngineeringRules._ASSISE_RE.search(text)
        if not m:
            return None
        return float(m.group(1).replace(",", "."))

    @staticmethod
    def parse_parpaing_thickness_m(text: str) -> float | None:
        """'PP e=20' / 'parpaing 20' → 0.20 m. Valeurs plausibles 10..40 cm."""
        if not text:
            return None
        m = CivilEngineeringRules._PARPAING_RE.search(text)
        if not m:
            return None
        cm = int(m.group(1))
        return round(cm / 100.0, 3) if 10 <= cm <= 40 else None

    @staticmethod
    def parse_voile_thickness_m(text: str) -> float | None:
        if not text:
            return None
        m = CivilEngineeringRules._VOILE_RE.search(text)
        if not m:
            return None
        cm = int(m.group(1))
        return round(cm / 100.0, 3) if 10 <= cm <= 40 else None

    @staticmethod
    def deduce_wall_height_m(niveau_assise_m: float, semelle_epaisseur_m: float,
                             niveau_reference_m: float = 0.0) -> float:
        """RÈGLE OBLIGATOIRE — hauteur du mur sus-jacent déduite des niveaux.

        hauteur_mur = (niveau_ref − niveau_assise) − épaisseur_semelle
        Ex. assise −1.30 m (TN=0), semelle 0.30 m → (0−(−1.30))−0.30 = 1.00 m."""
        h = abs(niveau_reference_m - niveau_assise_m) - semelle_epaisseur_m
        return round(h, 3)

    # ── métrés béton déterministes ────────────────────────────────────────────
    @staticmethod
    def volume_semelle_m3(longueur_m: float, largeur_m: float, hauteur_m: float,
                          nombre: int = 1) -> float:
        return round(longueur_m * largeur_m * hauteur_m * nombre, 4)

    @staticmethod
    def volume_poteau_m3(a_m: float, b_m: float, hauteur_m: float, nombre: int = 1) -> float:
        return round(a_m * b_m * hauteur_m * nombre, 4)

    @staticmethod
    def volume_lineaire_m3(longueur_m: float, largeur_m: float, hauteur_m: float) -> float:
        """Longrine / chaînage : section × longueur."""
        return round(longueur_m * largeur_m * hauteur_m, 4)


# ──────────────────────────────────────────────────────────────────────────────
# 3) SYSTEM PROMPT — conditionne le LLM au rôle de MÉTREUR-VÉRIFICATEUR
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = "És um MEDIDOR-VERIFICADOR de betão armado especialista (fundações e estrutura, Eurocódigos com Anexos Nacionais portugueses). Trabalhas para o ConstruPilot. A tua missão: a partir de dados geométricos BRUTOS (polígonos, cotas) e de textos OCR extraídos de uma planta de estrutura, IDENTIFICAR e QUALIFICAR os elementos e DEPOIS preparar a sua medição.\n\nDEVES:\n1. CRUZAR a semântica OCR com a geometria para atribuir o material certo à coordenada espacial certa. Exemplos imperativos:\n   - um texto «PP e=20» (ou «bloco 20», «tijolo 20») situado perto de um traçado de parede → material «Bloco 20cm», espessura 0.20 m, NESSA parede precisa.\n   - «parede 20» / «BA 18» → parede de betão com a espessura lida.\n   - um retângulo cotado «60x30» com a marca «3» → sapata isolada marca 3, 0.60 × 0.30 m.\n2. UTILIZAR as deduções determinísticas já fornecidas no bloco HEURÍSTICAS (níveis, alturas de parede deduzidas, espessuras lidas): não as recalcules, retoma-as tal como estão.\n3. Atribuir a CADA elemento um nível de confiança (0..1) e a marca a_verifier=true assim que subsista uma dúvida.\n\nPROIBIÇÕES ABSOLUTAS (ZERO ALUCINAÇÕES):\n- NUNCA inventar uma cota, uma espessura, um rácio de armaduras, uma tonelagem de aço ou uma altura ausentes dos dados.\n- NUNCA devolver 0 nem um valor «por omissão» para preencher uma lacuna.\n- Se faltar um dado INDISPENSÁVEL a um cálculo (ex.: nenhum rácio de aço, nenhum corte, nenhuma secção), NÃO calculas: acrescentas um objeto em \"missing_data\" com uma pergunta clara e precisa destinada ao utilizador, em português europeu.\n\nSAÍDA: responde APENAS com um objeto JSON válido, sem nenhum texto à volta, ESTRITAMENTE segundo este esquema (nenhuma chave adicional; mantém os valores enumerados):\n{\n  \"fondations\": [ { \"type\": \"semelle_isolee|semelle_filante|longrine|chainage|poteau\",\n     \"repere\": string|null, \"longueur_m\": number|null, \"largeur_m\": number|null,\n     \"hauteur_m\": number|null, \"nombre\": integer, \"volume_beton_m3\": number|null,\n     \"armature\": { \"repere\": string|null, \"nuance\": string|null, \"ratio_kg_m3\": number|null,\n                   \"total_kg\": number|null, \"detail\": string|null, \"confidence\": number } | null,\n     \"source_cotes\": string|null, \"confidence\": number, \"a_verifier\": boolean } ],\n  \"murs\": [ { \"repere\": string|null, \"materiau\": string, \"epaisseur_m\": number|null,\n     \"longueur_m\": number|null, \"hauteur_m\": number|null, \"niveau_assise_m\": number|null,\n     \"surface_m2\": number|null, \"volume_m3\": number|null, \"hauteur_deduite\": boolean,\n     \"confidence\": number, \"a_verifier\": boolean } ],\n  \"missing_data\": [ { \"champ\": string, \"element_repere\": string|null, \"question\": string,\n     \"unite\": string|null, \"raison\": string|null } ],\n  \"notes\": string|null\n}"


# ──────────────────────────────────────────────────────────────────────────────
# 4) ORCHESTRATION — SemanticReasoningEngine (règles dures + LLM + zéro hallucination)
# ──────────────────────────────────────────────────────────────────────────────


class SemanticReasoningEngine:
    """Couple les règles de génie civil (déterministes) et un LLM (classification
    sémantique) pour produire un métré fiable, ou s'arrêter proprement en réclamant
    les données manquantes."""

    def __init__(self, llm_feature: str = "structuro_reasoning"):
        self.rules = CivilEngineeringRules()
        self._feature = llm_feature

    # ---- utilitaires --------------------------------------------------------
    @staticmethod
    def _gather_ocr_text(geometry: dict) -> str:
        """Concatène tous les textes OCR du JSON d'entrée (positions ignorées ici)."""
        chunks: list[str] = []
        for key in ("ocr", "texts", "textes", "annotations", "labels"):
            for item in geometry.get(key) or []:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    t = item.get("text") or item.get("value") or item.get("contenu")
                    if t:
                        chunks.append(str(t))
        if geometry.get("raw_text"):
            chunks.append(str(geometry["raw_text"]))
        return "\n".join(chunks)

    # ---- règles dures pré-LLM ----------------------------------------------
    def _apply_hard_rules(self, geometry: dict, result: ReasoningResult) -> None:
        """Déductions déterministes : niveau d'assise → hauteur des murs de soubassement."""
        ocr = self._gather_ocr_text(geometry)
        assise = self.rules.parse_assise_level(ocr)
        if assise is None:
            return
        # épaisseur de semelle de référence : la plus représentée parmi les semelles connues
        semelle_h = next(
            (f.hauteur_m for f in result.fondations
             if f.type.startswith("semelle") and f.hauteur_m), None)
        if semelle_h is None:
            semelle_h = geometry.get("semelle_epaisseur_m")
        if semelle_h is None:
            # on NE devine pas l'épaisseur : on signale, mais on garde le niveau d'assise.
            for mur in result.murs:
                mur.niveau_assise_m = assise
            result.missing_data.append(MissingDataRequest(
                champ="epaisseur_semelle",
                question=("Cota de assentamento lida (" + f"{assise} m" + ") mas espessura da sapata desconhecida: introduza a espessura da sapata (m) para deduzir a altura do muro de embasamento."),
                unite="m",
                raison="Dedução da altura impossível sem a espessura da sapata."))
            return
        height = self.rules.deduce_wall_height_m(assise, semelle_h)
        result.deductions.append(
            f'Hauteur mur de soubassement déduite = |0 − ({assise})| − {semelle_h} = {height} m (assentamento {assise} m / terreno natural, sapata {semelle_h} m).')
        if not result.murs:
            result.murs.append(MurSoubassement(
                materiau="Muro de embasamento (a qualificar)", niveau_assise_m=assise,
                hauteur_m=height, hauteur_deduite=True, confidence=0.6, a_verifier=True))
        else:
            for mur in result.murs:
                if mur.hauteur_m is None:
                    mur.hauteur_m = height
                    mur.hauteur_deduite = True
                mur.niveau_assise_m = assise

    # ---- passe LLM ----------------------------------------------------------
    async def _llm_pass(self, geometry: dict, hard_result: ReasoningResult) -> ReasoningResult:
        """Classification sémantique par le LLM (JSON strict) ; repli silencieux sur
        les éléments déjà déduits/fournis si le LLM est indisponible."""
        from engines.ai import _complete, _json  # réutilise la clé LLM Emergent

        payload = {
            "geometrie": geometry,
            "heuristiques_deja_calculees": json.loads(hard_result.model_dump_json()),
        }
        prompt = (
            "Dados de entrada (geometria bruta + OCR + heurísticas determinísticas já calculadas a REUTILIZAR tal como estão):\n"
            + json.dumps(payload, ensure_ascii=False)
            + "\n\nIdentifica e qualifica os elementos. Respeita o esquema JSON imposto."
        )
        raw = await _complete(SYSTEM_PROMPT, prompt, feature=self._feature)
        data = _json(raw, {})
        if not isinstance(data, dict) or not (data.get("fondations") or data.get("murs")):
            return hard_result
        try:
            return ReasoningResult.model_validate({
                "fondations": data.get("fondations") or [],
                "murs": data.get("murs") or [],
                "missing_data": data.get("missing_data") or [],
                "deductions": hard_result.deductions,
                "notes": data.get("notes"),
            })
        except Exception:
            return hard_result

    # ---- métré béton déterministe ------------------------------------------
    def _fill_concrete_volumes(self, result: ReasoningResult) -> None:
        for f in result.fondations:
            if f.volume_beton_m3 is not None:
                continue
            if f.type == "poteau" and f.largeur_m and f.hauteur_m and f.longueur_m:
                f.volume_beton_m3 = self.rules.volume_poteau_m3(
                    f.longueur_m, f.largeur_m, f.hauteur_m, f.nombre)
            elif f.longueur_m and f.largeur_m and f.hauteur_m:
                f.volume_beton_m3 = self.rules.volume_semelle_m3(
                    f.longueur_m, f.largeur_m, f.hauteur_m, f.nombre)
        for mur in result.murs:
            if mur.surface_m2 is None and mur.longueur_m and mur.hauteur_m:
                mur.surface_m2 = round(mur.longueur_m * mur.hauteur_m, 3)
            if (mur.volume_m3 is None and mur.surface_m2 and mur.epaisseur_m):
                mur.volume_m3 = round(mur.surface_m2 * mur.epaisseur_m, 4)

    # ---- contrôle des dimensions (zéro hallucination) -----------------------
    _REQUIRED_DIMS = {
        "semelle_isolee": [("longueur_m", "longueur"), ("largeur_m", "largeur"), ("hauteur_m", "hauteur/épaisseur")],
        "semelle_filante": [("longueur_m", "longueur cumulée"), ("largeur_m", "largeur"), ("hauteur_m", "hauteur/épaisseur")],
        "longrine": [("longueur_m", "longueur"), ("largeur_m", "largeur de section"), ("hauteur_m", "hauteur de section")],
        "chainage": [("longueur_m", "longueur"), ("largeur_m", "largeur de section"), ("hauteur_m", "hauteur de section")],
        "poteau": [("longueur_m", "côté a"), ("largeur_m", "côté b"), ("hauteur_m", "hauteur")],
    }

    def _check_dimensions(self, result: ReasoningResult) -> None:
        """Si une cote indispensable au volume manque, on la réclame (jamais 0 ni devinette)."""
        for f in result.fondations:
            for field, label in self._REQUIRED_DIMS.get(f.type, []):
                if getattr(f, field, None) in (None, 0):
                    result.missing_data.append(MissingDataRequest(
                        champ=field,
                        element_repere=f.repere or f.type,
                        question=(f"Cota em falta para «{f.repere or f.type} » ({f.type.replace('_', ' ')}) : introduza a {label} (m)."),
                        unite="m",
                        raison="Volume de betão não calculável sem esta cota."))

    # ---- contrôle d'incertitude (zéro hallucination) ------------------------
    def _check_steel(self, result: ReasoningResult, steel_ratios: dict | None) -> None:
        """Pour chaque élément béton, exige un ratio d'acier (kg/m³) OU un tonnage explicite.
        À défaut → MissingDataRequest (jamais de valeur devinée)."""
        steel_ratios = steel_ratios or {}
        for f in result.fondations:
            if f.volume_beton_m3 is None:
                continue
            arm = f.armature
            if arm and (arm.total_kg is not None):
                continue
            ratio = (arm.ratio_kg_m3 if arm else None) or steel_ratios.get(f.type)
            if ratio is None:
                result.missing_data.append(MissingDataRequest(
                    champ="ratio_acier",
                    element_repere=f.repere or f.type,
                    question=(f'Rácio de aço em falta para «{f.repere or f.type}» (nenhuma lista nem corte de armaduras legível). Introduza o valor em kg/m³.'),
                    unite="kg/m³",
                    raison="Tonelagem de aço não calculável sem rácio nem corte."))
            else:
                # ratio fourni par l'utilisateur/config → calcul déterministe autorisé.
                f.armature = arm or Armature()
                f.armature.ratio_kg_m3 = ratio
                f.armature.total_kg = round(ratio * f.volume_beton_m3, 2)

    # ---- point d'entrée -----------------------------------------------------
    async def reason(self, geometry: dict, steel_ratios: dict | None = None,
                     use_llm: bool = True) -> ReasoningResult:
        """Raisonne sur la géométrie brute et renvoie un métré fiable.

        `steel_ratios` : {type_element: ratio_kg_m3} fourni par l'utilisateur (optionnel).
        Lève `MissingDataError` (avec résultat partiel) si une donnée indispensable manque."""
        # 0) éléments pré-existants fournis par le pipeline CV (optionnels)
        seed = ReasoningResult()
        for raw in geometry.get("elements") or []:
            try:
                seed.fondations.append(FondationElement.model_validate(raw))
            except Exception:
                pass
        for raw in geometry.get("murs") or []:
            try:
                seed.murs.append(MurSoubassement.model_validate(raw))
            except Exception:
                pass

        # 1) RÈGLES DURES (déductions déterministes) AVANT le LLM
        self._apply_hard_rules(geometry, seed)

        # 2) LLM (classification sémantique OCR ↔ géométrie)
        result = await self._llm_pass(geometry, seed) if use_llm else seed
        # garder la trace des déductions dures même après la passe LLM
        for d in seed.deductions:
            if d not in result.deductions:
                result.deductions.append(d)
        for md in seed.missing_data:
            result.missing_data.append(md)

        # 3) MÉTRÉ BÉTON déterministe
        self._fill_concrete_volumes(result)

        # 4) CONTRÔLE D'INCERTITUDE → zéro hallucination (cotes puis acier)
        self._check_dimensions(result)
        self._check_steel(result, steel_ratios)

        # 5) arrêt poli si données indispensables manquantes
        if result.missing_data:
            raise MissingDataError(result.missing_data, partial=result)
        return result
