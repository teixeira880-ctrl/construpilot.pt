#!/usr/bin/env python3
"""Gera a narração (ElevenLabs, voz portuguesa) do vídeo do Estúdio de Projeto. Só escreve em /tmp/narr_estudio.
Uso: python3 gerar_narracao.py narracao.json"""
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

env = {}
for l in open("/app/backend/.env"):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
KEY = os.environ.get("ELEVENLABS_API_KEY") or env.get("ELEVENLABS_API_KEY")
if not KEY:
    print("ERRO: ELEVENLABS_API_KEY em falta"); sys.exit(1)
H = {"xi-api-key": KEY, "Content-Type": "application/json", "Accept": "application/json"}

def pedir(url, corpo=None, aceitar="application/json"):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None, headers={**H, "Accept": aceitar})
    try:
        return urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        print("ERRO HTTP", e.code, e.read()[:300].decode("utf-8", "ignore")); sys.exit(1)

vozes = json.loads(pedir("https://api.elevenlabs.io/v1/voices"))["voices"]
def pontos(v):
    lab = {k: str(x).lower() for k, x in (v.get("labels") or {}).items()}
    txt = " ".join(lab.values()) + " " + (v.get("name") or "").lower() + " " + (v.get("description") or "").lower()
    linguas = " ".join(str(x.get("language", "")) + " " + str(x.get("accent", "")) + " " + str(x.get("locale", "")) for x in (v.get("verified_languages") or [])).lower()
    p = 0
    if "portug" in txt or "pt" == lab.get("language") or "pt-pt" in linguas or "pt" in linguas.split(): p += 5
    if "pt-pt" in linguas or "portugal" in txt or "european" in txt: p += 5
    if "brazil" in txt or "brasil" in txt: p -= 3
    if lab.get("gender") == "female": p += 1
    return p
ordem = sorted(vozes, key=pontos, reverse=True)
print("VOZES DA CONTA (as 8 mais adequadas):")
for v in ordem[:8]:
    print(" ", pontos(v), v["voice_id"], v.get("name"), v.get("labels"))
voz = ordem[0]
if pontos(voz) < 5:
    print("AVISO: nenhuma voz da conta está marcada como portuguesa; usada a mais adequada com o modelo multilingue.")
print("VOZ ESCOLHIDA:", voz["voice_id"], voz.get("name"), voz.get("labels"))

cenas = json.load(open(sys.argv[1], encoding="utf-8"))
out = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/narr_estudio"); out.mkdir(parents=True, exist_ok=True)
total = 0
for c in cenas:
    dados = pedir(f"https://api.elevenlabs.io/v1/text-to-speech/{voz['voice_id']}?output_format=mp3_44100_128",
                  {"text": c["texto"], "model_id": "eleven_multilingual_v2",
                   "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}}, "audio/mpeg")
    (out / f"{c['id']}.mp3").write_bytes(dados)
    total += len(c["texto"])
    print("OK", c["id"], len(dados), "bytes")
(out / "voz.json").write_text(json.dumps({"voice_id": voz["voice_id"], "nome": voz.get("name"), "labels": voz.get("labels"), "modelo": "eleven_multilingual_v2", "caracteres": total}, ensure_ascii=False))
print("FIM_OK", len(cenas), "ficheiros,", total, "caracteres")
