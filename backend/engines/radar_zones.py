"""French department reference and consistent Radar filtering."""
from fastapi import HTTPException

_NAMES = "Ain;Aisne;Allier;Alpes-de-Haute-Provence;Hautes-Alpes;Alpes-Maritimes;Ardèche;Ardennes;Ariège;Aube;Aude;Aveyron;Bouches-du-Rhône;Calvados;Cantal;Charente;Charente-Maritime;Cher;Corrèze;Côte-d'Or;Côtes-d'Armor;Creuse;Dordogne;Doubs;Drôme;Eure;Eure-et-Loir;Finistère;Gard;Haute-Garonne;Gers;Gironde;Hérault;Ille-et-Vilaine;Indre;Indre-et-Loire;Isère;Jura;Landes;Loir-et-Cher;Loire;Haute-Loire;Loire-Atlantique;Loiret;Lot;Lot-et-Garonne;Lozère;Maine-et-Loire;Manche;Marne;Haute-Marne;Mayenne;Meurthe-et-Moselle;Meuse;Morbihan;Moselle;Nièvre;Nord;Oise;Orne;Pas-de-Calais;Puy-de-Dôme;Pyrénées-Atlantiques;Hautes-Pyrénées;Pyrénées-Orientales;Bas-Rhin;Haut-Rhin;Rhône;Haute-Saône;Saône-et-Loire;Sarthe;Savoie;Haute-Savoie;Paris;Seine-Maritime;Seine-et-Marne;Yvelines;Deux-Sèvres;Somme;Tarn;Tarn-et-Garonne;Var;Vaucluse;Vendée;Vienne;Haute-Vienne;Vosges;Yonne;Territoire de Belfort;Essonne;Hauts-de-Seine;Seine-Saint-Denis;Val-de-Marne;Val-d'Oise".split(";")
DEPARTMENTS = dict(zip((f"{n:02d}" for n in range(1, 96) if n != 20), _NAMES))
DEPARTMENTS.update({"2A": "Corse-du-Sud", "2B": "Haute-Corse", "971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"})


def normalize_departments(values):
    codes = [str(v).strip().upper() for v in values if str(v).strip()]
    result = list(dict.fromkeys(str(int(v)).zfill(2) if v.isdigit() else v for v in codes))
    if any(v not in DEPARTMENTS for v in result):
        raise HTTPException(422, "Code département invalide. Corse : 2A ou 2B ; outre-mer : 971 à 974, 976.")
    return result


def department_of(permit):
    dep = str(permit.get("dep") or "").strip().upper().zfill(2)
    if dep in DEPARTMENTS:
        return dep
    cp = str(permit.get("cp") or "").strip()
    if cp[:3] in DEPARTMENTS:
        return cp[:3]
    if cp.startswith("20") and len(cp) == 5 and cp.isdigit():
        return "2A" if int(cp) < 20200 else "2B"
    return cp[:2] if cp[:2] in DEPARTMENTS else ""


def filter_zone(items, profile, km=None, zone_mode=None, departments=None):
    mode = zone_mode or profile["zone_mode"]
    deps = normalize_departments(departments.split(",")) if departments is not None else profile["departments"]
    radius = km if km is not None else profile["km"]
    filtered = [o for o in items if department_of(o) in deps] if mode == "departments" else [o for o in items if o["distance_km"] is not None and o["distance_km"] <= radius]
    return filtered, {"zone_mode": mode, "departments": deps, "radius_km": radius}