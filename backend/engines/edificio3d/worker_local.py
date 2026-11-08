"""
ConstruPilot — Posto de trabalho «Edifício 3D» (Blender + ArcGIS Pro instalados no PC).

Só usa a biblioteca padrão do Python. Fica a correr no PC, vai buscar trabalhos ao ConstruPilot,
executa os programas instalados e devolve GLB, renders e cenas ArcGIS para a interface.

Configuração (variáveis de ambiente ou iniciar_worker.bat):
  CONSTRUPILOT_API         ex.: https://construpilot.pt/api
  EDIFICIO3D_WORKER_TOKEN  o mesmo valor definido no servidor
  BLENDER_EXE              ex.: C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe
  ARCGIS_PROPY             ex.: C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\Scripts\\propy.bat  (opcional)
  ARCGIS_APRX              projeto .aprx base (opcional)
  POSTO_NOME               nome deste posto (opcional)
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
API = os.environ.get("CONSTRUPILOT_API", "").rstrip("/")
TOKEN = os.environ.get("EDIFICIO3D_WORKER_TOKEN", "")
BLENDER = os.environ.get("BLENDER_EXE") or shutil.which("blender") or ""
PROPY = os.environ.get("ARCGIS_PROPY", "")
APRX = os.environ.get("ARCGIS_APRX", "")
NOME = os.environ.get("POSTO_NOME") or socket.gethostname()


def pedido(metodo, caminho, dados=None, json_body=None, timeout=120):
    h = {"X-Worker-Token": TOKEN}
    corpo = None
    if json_body is not None:
        corpo = json.dumps(json_body).encode("utf-8")
        h["Content-Type"] = "application/json"
    elif dados is not None:
        corpo = dados
        h["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(API + caminho, data=corpo, headers=h, method=metodo)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def etapa(job, texto):
    print(f"[{job}] {texto}", flush=True)
    try:
        pedido("POST", f"/edificio3d/worker/{job}/etapa", json_body={"texto": texto})
    except Exception:
        pass


def enviar_pasta(job, pasta, filtro=None):
    for nome in sorted(os.listdir(pasta)):
        p = os.path.join(pasta, nome)
        if os.path.isfile(p) and (filtro is None or filtro(nome)):
            with open(p, "rb") as f:
                pedido("POST", f"/edificio3d/worker/{job}/ficheiros/{nome}", dados=f.read(), timeout=600)


def processar(t):
    job = t["job_id"]
    params = dict(t["params"])
    tmp = tempfile.mkdtemp(prefix="cp_ed3d_")
    try:
        try:
            orto = pedido("GET", f"/edificio3d/worker/{job}/ficheiros/ortofoto.png")
            op = os.path.join(tmp, "ortofoto.png")
            with open(op, "wb") as f:
                f.write(orto)
            params["ortofoto_path"] = op
        except urllib.error.HTTPError:
            pass
        pp = os.path.join(tmp, "parametros.json")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False)

        # 1) Blender
        etapa(job, f"Blender ({NOME}) a modelar e a renderizar…")
        out_b = os.path.join(tmp, "blender")
        cmd = [BLENDER, "-b", "--factory-startup", "-P", os.path.join(AQUI, "blender_edificio.py"), "--", pp, out_b]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        man_p = os.path.join(out_b, "manifesto.json")
        if r.returncode != 0 or not os.path.exists(man_p):
            raise RuntimeError("Blender falhou: " + (r.stderr or r.stdout)[-1500:])
        with open(man_p, encoding="utf-8") as f:
            manifesto = json.load(f)
        enviar_pasta(job, out_b)
        g = manifesto.get("geometria", {})
        etapa(job, f"Blender concluído: {g.get('vertices')} vértices, {len(manifesto.get('imagens', {}))} renders, GLB enviado")

        # 2) ArcGIS Pro
        arc = {}
        if t.get("usar_arcgis") and PROPY:
            etapa(job, "ArcGIS Pro: implantação, importação do GLB e cena 3D com terreno…")
            out_a = os.path.join(tmp, "arcgis")
            os.makedirs(out_a, exist_ok=True)
            pa = dict(params, glb_path=os.path.join(out_b, "edificio.glb"),
                      altura_cumeeira_m=manifesto.get("dimensoes", {}).get("altura_cumeeira_m"))
            pap = os.path.join(tmp, "parametros_arcgis.json")
            with open(pap, "w", encoding="utf-8") as f:
                json.dump(pa, f, ensure_ascii=False)
            cmd = [PROPY, os.path.join(AQUI, "arcgis_implantacao.py"), pap, out_a] + ([APRX] if APRX else [])
            subprocess.run(cmd, capture_output=True, text=True, timeout=3600, shell=PROPY.lower().endswith(".bat"))
            am = os.path.join(out_a, "arcgis_manifesto.json")
            if os.path.exists(am):
                with open(am, encoding="utf-8") as f:
                    arc = json.load(f)
            gdb = os.path.join(out_a, "construpilot.gdb")
            if os.path.isdir(gdb):
                zp = os.path.join(out_a, "construpilot_gdb.zip")
                with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                    for raiz, _d, fs in os.walk(gdb):
                        for fn in fs:
                            if not fn.endswith(".lock"):
                                full = os.path.join(raiz, fn)
                                z.write(full, os.path.relpath(full, out_a))
            enviar_pasta(job, out_a, lambda n: n.endswith((".jpg", ".png", ".slpk", ".aprx", ".json", ".zip")))
            etapa(job, "ArcGIS Pro concluído" if arc.get("ok") else f"ArcGIS Pro com erro: {arc.get('erro', 'sem manifesto')}")
        elif t.get("usar_arcgis"):
            arc = {"ok": False, "erro": "ArcGIS Pro não configurado neste posto (ARCGIS_PROPY)"}

        pedido("POST", f"/edificio3d/worker/{job}/concluir",
               json_body={"ok": True, "manifesto": manifesto, "arcgis": arc})
    except Exception as e:
        traceback.print_exc()
        try:
            pedido("POST", f"/edificio3d/worker/{job}/concluir", json_body={"ok": False, "erro": str(e)[:3500]})
        except Exception:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if not API or not TOKEN or not BLENDER:
        sys.exit("Defina CONSTRUPILOT_API, EDIFICIO3D_WORKER_TOKEN e BLENDER_EXE.")
    print(f"Posto «{NOME}» ligado a {API} — Blender: {BLENDER} — ArcGIS Pro: {PROPY or 'não'}", flush=True)
    while True:
        try:
            r = json.loads(pedido("POST", "/edificio3d/worker/proximo",
                                  json_body={"nome": NOME, "blender": True, "arcgis": bool(PROPY)}))
            t = r.get("trabalho")
            if t:
                processar(t)
                continue
        except Exception as e:
            print("ligação:", e, flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
