"""BET.3b — Muros de cave: K0 por camada + sobrecarga de confinantes.

Entradas:
  pc  — dicionário do Pedido de Construção (deve conter `neighbors`).
  g2  — relatório geotécnico G2 (deve conter `soil_layers` com `k0`).

Saída:
  dict com:
    layers_K0: lista das camadas com `k0` definido (nome, top, bottom, k0).
    neighbor_surcharge_kN_m: estimativa de sobrecarga linear devida aos
      vizinhos encostados cuja profundidade de cave é desconhecida.
    warnings: lista de alertas estruturados.
"""
from typing import Any


def _parse_floors(building_type: str) -> int:
    """Converte "R+2", "R+3", "RDC" num nº de pisos (RDC=1)."""
    bt = (building_type or "").strip().upper()
    if not bt or bt == "RDC":
        return 1
    if "R+" in bt:
        tail = bt.split("R+", 1)[1]
        digits = ""
        for ch in tail:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            return int(digits) + 1
    return 1


def compute(pc: dict[str, Any], g2: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "layers_K0": [],
        "neighbor_surcharge_kN_m": 0.0,
        "warnings": [],
    }

    # 1) Camadas com K0 explícito no G2
    for lay in g2.get("soil_layers") or []:
        if lay.get("k0") is not None:
            out["layers_K0"].append({
                "name": lay.get("name"),
                "top_m": lay.get("top_m"),
                "bottom_m": lay.get("bottom_m"),
                "k0": lay.get("k0"),
            })

    # 2) Sobrecarga de confinantes com cave desconhecida
    neighbors = pc.get("neighbors") or []
    attached_unknown = [
        n for n in neighbors
        if n.get("attached") and not n.get("cave_known", False)
    ]
    if attached_unknown:
        # Estimativa prudente: 10 kN/m² por piso projetado linearmente.
        total_surcharge = 0.0
        for n in attached_unknown:
            n_floors = _parse_floors(n.get("building_type", ""))
            total_surcharge += 10.0 * n_floors
        out["neighbor_surcharge_kN_m"] = round(total_surcharge, 3)
        out["warnings"].append({
            "code": "neighbors_attached_unknown_cave",
            "severity": "high",
            "detail": (
                f"{len(attached_unknown)} vizinho(s) encostado(s) com "
                "profundidade de cave desconhecida."
            ),
            "remediation": (
                "Recalçamento (soutènement) obrigatório antes de escavação. "
                "Solicitar à MOA sondagens complementares para verificar "
                "cotas de fundação dos edifícios confinantes."
            ),
            "action": "require_moa_input",
        })

    return out
