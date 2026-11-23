"""Monta o vídeo de demonstração a partir das capturas do navegador (um ficheiro por cena, depois concat)."""
import glob
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

SRC = sys.argv[1]            # pasta das capturas
OUT = sys.argv[2]            # pasta de trabalho
W, H, FPS = 1280, 720, 30
BG = (11, 20, 17)
GREEN = (52, 168, 110)
CREAM = (244, 236, 222)
MUTED = (150, 168, 160)
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ENC = ["-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS)]

# (sufixo do ficheiro, secção, legenda, duração em segundos)
SCENES = [
    ("3wqgza-07713c61", "A conta", "Atlântico Construções (DEMO): uma empresa fictícia criada para mostrar o ConstruPilot", 5.5),
    ("vk5nhd-344332b8", "Contactos", "Clientes e subempreiteiros ficam na mesma lista de contactos", 5.5),
    ("662ibc-e1adb1aa", "Contactos", "Criar um cliente: basta preencher a ficha", 5.5),
    ("omcc78-75cad6c9", "Contactos", "O cliente fica logo disponível para orçamentos e obras", 5.0),
    ("5asza2-b1c640bc", "Obras", "Processos de obra: cada obra com as suas plantas, orçamentos e documentos", 5.5),
    ("c8lnnk-ae2bcaba", "Obras", "Criar uma obra: nome, cliente, morada e estado", 5.5),
    ("2j42ek-32fa0c30", "Obras", "A obra nasce com o seu percurso: plantas, medição, orçamento, assinatura e faturação", 6.0),
    ("tbfp07-a1e68643", "Obras", "Cinco obras em fases diferentes, de prospeção a obra em curso", 5.5),
    ("zxs4j0-b0a1d4b9", "Uma obra em curso", "Remodelação no Porto: medição feita, orçamento assinado pelo cliente", 5.5),
    ("fiu7xa-cf40c59d", "Uma obra em curso", "69 500 € assinados e seis marcos de avanço, com a equipa e os subempreiteiros", 6.5),
    ("cp26i8-0f03f2c0", "Orçamento", "Orçamento artigo a artigo: 8 linhas, 56 504,00 € sem IVA, 69 499,92 € com IVA", 6.5),
    ("7xpx7h-09fbbec3", "Equipa", "Seis trabalhadores com função e valor por hora, para o registo de ponto em obra", 5.5),
    ("j4w91j-5df8a6dc", "Obra colaborativa", "Quatro perfis por obra: dono de obra, fiscalização, arquiteto e empresas", 6.5),
    ("tlm0k3-e095f1e2", "Obra colaborativa", "Caixa de planos: os planos de execução precisam do visto da fiscalização ou do arquiteto", 6.5),
    ("v8jjdi-f02edae2", "Obra colaborativa", "Subempreiteiros: cada pedido é confrontado com o regulamento do dono de obra", 6.5),
    ("c9y14a-c2b6dc70", "Obra colaborativa", "Falta o seguro de responsabilidade civil: aprovado com reservas, com prazo para entregar", 7.0),
    ("hu1v9q-73dff32b", "Obra colaborativa", "Auto de medição: fatura 90 % do contrato, mas o avanço registado é de 77 %", 7.0),
    ("kxe0jb-d55f9837", "Obra colaborativa", "Outro auto: 330 m² medidos para 310 m² contratados. O excesso é assinalado", 7.0),
    ("5azonu-9032068c", "Obra colaborativa", "Planeamento: cada empresa carrega o cronograma, a fiscalização regista o avanço", 6.5),
    ("54whtm-ab656de7", "Obra colaborativa", "Ata semanal em três colunas: empresa e ponto, ata de origem, estado", 6.5),
    ("slvmeh-27b58226", "Portal da empresa", "Cada empresa entra no seu portal e só vê os seus próprios autos e contratos", 6.5),
]


AUDIO = [('00_intro', 161375), ('01_conta', 157195), ('02_contactos', 115399), ('03_cliente_ficha', 108712), ('04_cliente_criado', 49362), ('05_obras', 95337), ('06_obra_ficha', 91158), ('07_obra_criada', 145910), ('08_cinco_obras', 75275), ('09_obra_porto', 130446), ('10_marcos', 143821), ('11_orcamento', 154270), ('12_equipa', 102861), ('13_perfis', 201081), ('14_planos', 200245), ('15_sub_conforme', 168898), ('16_sub_reservas', 198155), ('17_auto_avanco', 231592), ('18_auto_excesso', 157195), ('19_planeamento', 166808), ('20_ata', 154270), ('21_portal', 168898), ('22_fim', 126684)]  # mp3 ElevenLabs a 128 kbit/s constantes: bytes / 16000 = segundos
GAP, LEAD = 0.75, 0.30


def font(path, size):
    return ImageFont.truetype(path, size)


def fit(draw, text, path, size, max_w):
    while size > 14 and draw.textlength(text, font=font(path, size)) > max_w:
        size -= 1
    return font(path, size)


def frame(shot_path, section, caption, idx, total):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    shot = Image.open(shot_path).convert("RGB").resize((1120, 630), Image.LANCZOS)
    img.paste(shot, (80, 8))
    d.rectangle([79, 7, 1200, 638], outline=(34, 58, 48), width=1)
    d.rectangle([0, 646, W, H], fill=(7, 14, 12))
    d.rectangle([0, 646, 8, H], fill=GREEN)
    d.text((28, 655), section.upper(), font=font(FB, 15), fill=GREEN)
    d.text((28, 678), caption, font=fit(d, caption, F, 25, W - 160), fill=CREAM)
    n = f"{idx}/{total}"
    d.text((W - 28 - d.textlength(n, font=font(F, 15)), 655), n, font=font(F, 15), fill=MUTED)
    return img


def card(title, lines, footer):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=GREEN)
    tf = fit(d, title, FB, 58, W - 200)
    d.text(((W - d.textlength(title, font=tf)) / 2, 230), title, font=tf, fill=CREAM)
    y = 330
    for l in lines:
        lf = fit(d, l, F, 28, W - 200)
        d.text(((W - d.textlength(l, font=lf)) / 2, y), l, font=lf, fill=MUTED)
        y += 44
    ff = font(F, 18)
    d.text(((W - d.textlength(footer, font=ff)) / 2, 650), footer, font=ff, fill=GREEN)
    return img


def encode(png, dur, out):
    tmp = out.replace(".mp4", ".tmp.mp4")
    fade = f"fade=t=in:st=0:d=0.3,fade=t=out:st={dur - 0.3:.2f}:d=0.3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", png, "-vf",
                    f"format=yuv420p,loop=-1:1,trim=duration={dur},{fade}", *ENC, tmp], check=True)
    os.rename(tmp, out)


def main():
    os.makedirs(f"{OUT}/frames", exist_ok=True)
    os.makedirs(f"{OUT}/scenes", exist_ok=True)
    assert len(AUDIO) == len(SCENES) + 2
    durs = [b / 16000.0 + GAP for _, b in AUDIO]
    items = []
    card("ConstruPilot", ["Como funciona, numa empresa de construção fictícia",
                          "Conta de demonstração · construpilot.pt"], "Dados fictícios · 23 de novembro de 2026").save(f"{OUT}/frames/000.png")
    items.append((f"{OUT}/frames/000.png", durs[0]))
    for i, (suffix, section, caption, _) in enumerate(SCENES, 1):
        found = glob.glob(f"{SRC}/*{suffix}.jpg")
        if len(found) != 1:
            sys.exit(f"captura em falta: {suffix}")
        p = f"{OUT}/frames/{i:03d}.png"
        frame(found[0], section, caption, i, len(SCENES)).save(p)
        items.append((p, durs[i]))
    card("Do primeiro contacto ao último auto", ["Clientes, obras, orçamentos, equipa e obra colaborativa",
                                                 "num só espaço de trabalho"], "construpilot.pt").save(f"{OUT}/frames/999.png")
    items.append((f"{OUT}/frames/999.png", durs[-1] + 1.5))
    lst, starts, t = [], [], 0.0
    for n, (png, dur) in enumerate(items):
        dur = round(dur * FPS) / FPS          # duração exata em fotogramas, para o áudio não derivar
        out = f"{OUT}/scenes/s{n:02d}.mp4"
        encode(png, dur, out)
        lst.append(f"file '{out}'")
        starts.append(int(round((t + LEAD) * 1000)))
        t += dur
    open(f"{OUT}/list.txt", "w").write("\n".join(lst) + "\n")
    final = f"{OUT}/video-sem-voz.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{OUT}/list.txt",
                    "-c", "copy", "-movflags", "+faststart", final], check=True)
    ins = " ".join(f'-i "$A/{a}.mp3"' for a, _ in AUDIO)
    fc = ";".join(f"[{k + 1}:a]adelay={ms}:all=1[a{k}]" for k, ms in enumerate(starts))
    mix = "".join(f"[a{k}]" for k in range(len(AUDIO))) + f"amix=inputs={len(AUDIO)}:normalize=0:dropout_transition=0,apad[a]"
    sh = f"""#!/bin/bash
# Junta a voz (ElevenLabs) ao vídeo já montado: o vídeo não é recodificado.
# Uso: juntar_voz.sh <video-sem-voz.mp4> <pasta dos mp3> <saida.mp4> [ffmpeg]
set -e
V="$1"; A="$2"; O="$3"; FF="${{4:-ffmpeg}}"
"$FF" -y -v error -i "$V" {ins} -filter_complex "{fc};{mix}" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 160k -ar 44100 -ac 2 -shortest -movflags +faststart "$O.tmp.mp4"
mv "$O.tmp.mp4" "$O"
"""
    open(f"{OUT}/juntar_voz.sh", "w").write(sh)
    print(final, round(t, 2), "s; inícios (ms):", starts)
    print("fim de cada faixa (s):", [round(ms / 1000 + b / 16000.0, 2) for ms, (_, b) in zip(starts, AUDIO)])


if __name__ == "__main__":
    main()
