"""Verificação de coerência entre morada do PC e morada do relatório G2.

Compara `project_address` + `project_parcel` entre PC e G2.

Resultado:
  - Match exacto (morada + parcela) → severity=none, G2 usada sem bloqueio.
  - Match aproximado (mesma cidade, rua diferente) → severity=medium,
    warn_but_allow.
  - Mismatch total (cidades diferentes) → severity=high,
    require_user_confirmation.
"""
import re
import unicodedata
from typing import Any


def _normalize(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_city(address: str) -> str:
    """Tenta extrair a cidade — tipicamente o penúltimo ou último token
    não-país. Heurística: separa por vírgulas, descarta país final,
    procura token após código postal."""
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return ""
    # Remove país final se é "France"/"Portugal"/etc.
    last = _normalize(parts[-1])
    if last in {"france", "portugal", "fr", "pt"}:
        parts = parts[:-1]
    if not parts:
        return ""
    # O último token restante contém tipicamente "CP cidade" ou só "cidade"
    tail = parts[-1]
    # Separa CP+cidade (ex. "93120 La Courneuve" ou "1200-200 Lisboa")
    m = re.match(r"^\s*(\d{4,5}(?:-\d{3})?)\s+(.+)$", tail)
    if m:
        return _normalize(m.group(2))
    return _normalize(tail)


def _extract_street(address: str) -> str:
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if not parts:
        return ""
    return _normalize(parts[0])


def verify_g2_coherence(pc: dict[str, Any], g2: dict[str, Any]) -> dict[str, Any]:
    pc_addr = pc.get("project_address") or ""
    g2_addr = g2.get("project_address") or ""
    pc_parcel = _normalize(pc.get("project_parcel") or "")
    g2_parcel = _normalize(g2.get("project_parcel") or "")

    pc_city = _extract_city(pc_addr)
    g2_city = _extract_city(g2_addr)
    pc_street = _extract_street(pc_addr)
    g2_street = _extract_street(g2_addr)

    norm_addr_pc = _normalize(pc_addr)
    norm_addr_g2 = _normalize(g2_addr)

    # Match exacto: morada normalizada igual OU (cidade + rua + parcela coincidem)
    if norm_addr_pc and norm_addr_pc == norm_addr_g2 and (
            not pc_parcel or not g2_parcel or pc_parcel == g2_parcel):
        return {
            "coherent": True, "severity": "none",
            "action": "use_g2_without_confirmation",
            "detail": "Morada e parcela coincidem.",
            "pc_city": pc_city, "g2_city": g2_city,
        }

    if pc_city and g2_city and pc_city == g2_city:
        # Mesma cidade: match aproximado (parcela ou rua pode diferir)
        if pc_parcel and g2_parcel and pc_parcel == g2_parcel:
            return {
                "coherent": True, "severity": "none",
                "action": "use_g2_without_confirmation",
                "detail": "Mesma cidade e parcela.",
            }
        return {
            "coherent": False, "severity": "medium",
            "action": "warn_but_allow",
            "detail": (
                f"Cidade coincide ({pc_city}) mas rua/parcela diferem — "
                f"PC: {pc_street} ({pc_parcel or '—'}) vs "
                f"G2: {g2_street} ({g2_parcel or '—'})."
            ),
        }

    # Mismatch total — cidades diferentes
    return {
        "coherent": False, "severity": "high",
        "action": "require_user_confirmation",
        "detail": (
            f"Moradas divergentes — PC: {pc_city or pc_addr[:60]} vs "
            f"G2: {g2_city or g2_addr[:60]}. Confirmar explicitamente "
            "antes de usar os valores G2 no dimensionamento."
        ),
    }
