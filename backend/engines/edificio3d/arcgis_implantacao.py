"""
ConstruPilot — Componente geográfica em ArcGIS Pro (ArcPy).

Corre no Python do ArcGIS Pro (arcgispro-py3), num PC Windows com ArcGIS Pro licenciado.
É chamado pelo worker ConstruPilot depois de o Blender gerar o edifício:

    "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\Scripts\\propy.bat" arcgis_implantacao.py ^
        parametros.json pasta_resultados [modelo.aprx]

O que faz (tudo com dados e ferramentas reais do ArcGIS Pro):
  1. Importa as coordenadas WGS84 do utilizador e projeta-as (PT-TM06 / EPSG:3763 em Portugal,
     UTM fora de Portugal).
  2. Obtém a altitude do terreno (serviço World Elevation da Esri ou valor fornecido).
  3. Cria a implantação: ponto 3D + polígono do edifício (largura × profundidade, rodado
     para o azimute da fachada).
  4. Importa o GLB do Blender (Import 3D Files) e coloca-o georreferenciado no ponto (multipatch).
  5. Cria uma cena local com ortofotomapa (Imagery) + terreno real e adiciona as camadas.
  6. Exporta imagens da cena (antes/depois, aérea, 4 fachadas no contexto real) e um
     Scene Layer Package (.slpk) para publicação web.
  7. Escreve arcgis_manifesto.json com tudo o que foi produzido.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
import traceback

import arcpy  # disponível apenas no Python do ArcGIS Pro

WGS84 = arcpy.SpatialReference(4326)
ELEV_URL = "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer"


def log(msg):
    print(f"[ArcGIS] {msg}", flush=True)


def sr_projetado(lat, lon):
    if 36.8 <= lat <= 42.2 and -9.6 <= lon <= -6.1:
        return arcpy.SpatialReference(3763)                # ETRS89 / PT-TM06 (Portugal continental)
    zona = int((lon + 180) // 6) + 1
    return arcpy.SpatialReference((32600 if lat >= 0 else 32700) + zona)


def altitude_terreno(lat, lon, fornecida):
    if fornecida is not None:
        return float(fornecida), "fornecida pelo utilizador"
    try:
        pt = arcpy.PointGeometry(arcpy.Point(lon, lat), WGS84).projectAs(arcpy.SpatialReference(3857))
        r = arcpy.management.GetCellValue(ELEV_URL, f"{pt.firstPoint.X} {pt.firstPoint.Y}")
        return float(str(r.getOutput(0)).replace(",", ".")), "Esri World Elevation (Terrain3D)"
    except Exception as e:  # sem sessão ArcGIS Online / sem rede
        log(f"altitude não obtida do serviço ({e}); usar 0")
        return 0.0, "indisponível (0 m)"


def retangulo(cx, cy, w, d, az_graus):
    """Polígono da implantação: frente com largura w a olhar para o azimute az."""
    a = math.radians(az_graus)
    fx, fy = math.sin(a), math.cos(a)          # direção da fachada (para fora)
    lx, ly = fy, -fx                           # ao longo da fachada
    pts = []
    for su, sv in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        pts.append((cx + su * w / 2 * lx + sv * d / 2 * fx, cy + su * w / 2 * ly + sv * d / 2 * fy))
    return pts


def aprx_base(caminho_modelo):
    if caminho_modelo and os.path.exists(caminho_modelo):
        return arcpy.mp.ArcGISProject(caminho_modelo)
    try:
        return arcpy.mp.ArcGISProject("CURRENT")
    except Exception:
        pass
    inst = arcpy.GetInstallInfo().get("InstallDir", "")
    for padrao in (r"Resources\**\*Blank*.aprx", r"Resources\**\*.aprx"):
        cands = glob.glob(os.path.join(inst, padrao), recursive=True)
        if cands:
            return arcpy.mp.ArcGISProject(cands[0])
    raise RuntimeError("Nenhum projeto .aprx base encontrado: indique um modelo.aprx como 3.º argumento.")


def main():
    params_path, out = sys.argv[1], sys.argv[2]
    modelo = sys.argv[3] if len(sys.argv) > 3 else None
    with open(params_path, encoding="utf-8") as f:
        p = json.load(f)
    os.makedirs(out, exist_ok=True)
    arcpy.env.overwriteOutput = True
    res = {"ok": False, "imagens": {}, "ficheiros": {}, "avisos": []}

    lat, lon = float(p["latitude"]), float(p["longitude"])
    W, D = float(p.get("largura_m", 12)), float(p.get("profundidade_m", 9))
    az = float(p.get("azimute_fachada_graus", 180))
    alt_cume = float(p.get("altura_cumeeira_m", 8.6))
    glb = p["glb_path"]

    sr = sr_projetado(lat, lon)
    z, fonte_z = altitude_terreno(lat, lon, p.get("altitude_m"))
    ptp = arcpy.PointGeometry(arcpy.Point(lon, lat, z), WGS84, True).projectAs(sr)
    X, Y = ptp.firstPoint.X, ptp.firstPoint.Y
    log(f"implantação {sr.name}: X={X:.2f} Y={Y:.2f} Z={z:.2f} ({fonte_z})")
    res["implantacao"] = {"sr": sr.factoryCode, "sr_nome": sr.name, "x": X, "y": Y, "z": z,
                          "fonte_altitude": fonte_z, "azimute_graus": az}

    # 1) Geodatabase + camadas de implantação
    gdb = os.path.join(out, "construpilot.gdb")
    if not arcpy.Exists(gdb):
        arcpy.management.CreateFileGDB(out, "construpilot.gdb")
    fc_pt = os.path.join(gdb, "implantacao_ponto")
    arcpy.management.CreateFeatureclass(gdb, "implantacao_ponto", "POINT", has_z="ENABLED", spatial_reference=sr)
    arcpy.management.AddField(fc_pt, "nome", "TEXT", field_length=120)
    with arcpy.da.InsertCursor(fc_pt, ["SHAPE@", "nome"]) as cur:
        cur.insertRow([arcpy.PointGeometry(arcpy.Point(X, Y, z), sr, True), p.get("nome", "Edifício ConstruPilot")])

    fc_poly = os.path.join(gdb, "implantacao_edificio")
    arcpy.management.CreateFeatureclass(gdb, "implantacao_edificio", "POLYGON", has_z="ENABLED", spatial_reference=sr)
    for campo, tipo in (("largura_m", "DOUBLE"), ("profund_m", "DOUBLE"), ("pisos", "SHORT"),
                        ("altura_m", "DOUBLE"), ("azimute", "DOUBLE"), ("area_m2", "DOUBLE")):
        arcpy.management.AddField(fc_poly, campo, tipo)
    anel = arcpy.Array([arcpy.Point(x, y, z) for x, y in retangulo(X, Y, W, D, az)])
    poly = arcpy.Polygon(anel, sr, True)
    with arcpy.da.InsertCursor(fc_poly, ["SHAPE@", "largura_m", "profund_m", "pisos", "altura_m", "azimute", "area_m2"]) as cur:
        cur.insertRow([poly, W, D, int(p.get("pisos", 2)), alt_cume, az, W * D])

    # 2) Importar o GLB do Blender, georreferenciado no ponto de implantação
    fc_3d = os.path.join(gdb, "edificio_3d")
    arcpy.CheckOutExtension("3D")
    arcpy.ddd.Import3DFiles(in_files=glb, out_featureClass=fc_3d, root_per_feature="ONE_FILE_ONE_FEATURE",
                            spatial_reference=sr, y_is_up="Y_IS_UP", file_suffix="*", in_featureClass=fc_pt)
    log("GLB importado como multipatch georreferenciado")
    res["ficheiros"]["gdb"] = gdb

    # Verificação: o multipatch tem de estar sobre a implantação
    with arcpy.da.SearchCursor(fc_3d, ["SHAPE@"]) as cur:
        for (g,) in cur:
            e = g.extent
            res["verificacao"] = {"extent": [e.XMin, e.YMin, e.ZMin, e.XMax, e.YMax, e.ZMax],
                                  "centro_desvio_m": round(math.hypot((e.XMin + e.XMax) / 2 - X, (e.YMin + e.YMax) / 2 - Y), 3),
                                  "altura_modelo_m": round(e.ZMax - e.ZMin, 2)}

    # 3) Cena local com ortofoto + terreno, e exportação de vistas
    aprx = aprx_base(modelo)
    cena = aprx.createMap(f"ConstruPilot {p.get('nome', 'Edifício')}", "LOCAL_SCENE")
    try:
        cena.addBasemap("Imagery")
    except Exception as e:
        res["avisos"].append(f"basemap Imagery: {e}")
    try:
        cena.spatialReference = sr
    except Exception:
        pass
    lyr_poly = cena.addDataFromPath(fc_poly)
    lyr_3d = cena.addDataFromPath(fc_3d)

    lay = aprx.createLayout(12, 8, "INCH", "ConstruPilot vistas")
    ext = arcpy.Extent(X - 60, Y - 40, X + 60, Y + 40)
    mf = lay.createMapFrame(arcpy.Polygon(arcpy.Array([arcpy.Point(0, 0), arcpy.Point(12, 0), arcpy.Point(12, 8),
                                                       arcpy.Point(0, 8)])), cena, "Vista 3D")
    mf.camera.setExtent(ext)

    def vista(nome, ox, oy, oz, heading, pitch, mostrar=True):
        lyr_3d.visible = mostrar
        cam = mf.camera
        cam.X, cam.Y, cam.Z = ox, oy, oz
        cam.heading, cam.pitch, cam.roll = heading, pitch, 0
        f = os.path.join(out, f"arcgis_{nome}.jpg")
        lay.exportToJPEG(f, resolution=150, jpeg_quality=90)
        res["imagens"][nome] = os.path.basename(f)

    dist = max(W, D) * 2.2 + 8
    a = math.radians(az)
    cx = lambda ang: (X + dist * math.sin(ang), Y + dist * math.cos(ang))
    vistas = [("aerea_depois", X, Y, z + 160, 0, -90, True), ("aerea_antes", X, Y, z + 160, 0, -90, False)]
    for nome, desv in (("frente", 0), ("direita", 90), ("tardoz", 180), ("esquerda", 270)):
        ang = a + math.radians(desv)
        px, py = cx(ang)
        vistas.append((f"contexto_{nome}", px, py, z + 6, (math.degrees(ang) + 180) % 360, -8, True))
    px, py = cx(a - math.radians(40))
    vistas += [("perspetiva_depois", px, py, z + 25, (math.degrees(a - math.radians(40)) + 180) % 360, -22, True),
               ("perspetiva_antes", px, py, z + 25, (math.degrees(a - math.radians(40)) + 180) % 360, -22, False)]
    for v in vistas:
        try:
            vista(*v)
        except Exception as e:
            res["avisos"].append(f"vista {v[0]}: {e}")
    lyr_3d.visible = True

    # 4) Scene Layer Package para publicação web (ArcGIS Online / visualizador ConstruPilot)
    try:
        slpk = os.path.join(out, "edificio.slpk")
        arcpy.management.Create3DObjectSceneLayerPackage(fc_3d, slpk, WGS84)
        res["ficheiros"]["slpk"] = os.path.basename(slpk)
    except Exception as e:
        res["avisos"].append(f"slpk: {e}")

    aprx_out = os.path.join(out, "construpilot_cena.aprx")
    aprx.saveACopy(aprx_out)
    res["ficheiros"]["aprx"] = os.path.basename(aprx_out)
    res["ok"] = True
    return res


if __name__ == "__main__":
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    try:
        r = main()
    except Exception as exc:
        r = {"ok": False, "erro": str(exc), "trace": traceback.format_exc()}
    with open(os.path.join(out_dir, "arcgis_manifesto.json"), "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2, default=str)
    print("CONSTRUPILOT_ARCGIS", json.dumps({"ok": r.get("ok"), "erro": r.get("erro")}, ensure_ascii=False))
    sys.exit(0 if r.get("ok") else 1)
