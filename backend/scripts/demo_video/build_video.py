"""Montage des vidéos de démonstration ConstruPilot : captures réelles + voix off (OpenAI TTS) + ffmpeg."""
import asyncio, json, os, subprocess, sys, textwrap
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

SHOTS = "/app/backend/scripts/demo_video/work/shots"
CLIPS = "/app/backend/scripts/demo_video/work/clips"
META: dict = {}


def use_clips(lang: str) -> None:
    """Clips enregistrés avec l'interface dans la langue de la vidéo (clips_pt si dispo)."""
    global CLIPS, META
    cand = f"/app/backend/scripts/demo_video/work/clips_{lang}"
    CLIPS = cand if lang != "fr" and os.path.exists(f"{cand}/meta.json") else "/app/backend/scripts/demo_video/work/clips"
    META = json.load(open(f"{CLIPS}/meta.json")) if os.path.exists(f"{CLIPS}/meta.json") else {}
WORK = "/app/backend/scripts/demo_video/work"
OUT = "/app/frontend/public/docs"
FONT_B = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
LOGO = "/app/frontend/public/construpilot-logo.png"
VOICE = "onyx"

# (slug image, titre à l'écran, narration)
FULL = [
    ("landing", "ConstruPilot — Estimez. Comparez. Construisez.",
     "Bienvenue sur ConstruPilot, la plateforme tout-en-un du bâtiment. Estimation de travaux par intelligence artificielle, lecture de plans, devis, factures, approvisionnement et prospection : une seule application pour les particuliers comme pour les professionnels."),
    ("estimation_form", "Estimateur de travaux",
     "Tout commence par l'estimateur. Choisissez le type de projet — rénovation, construction, extension ou piscine — la surface, la région et l'état du bien."),
    ("estimation_result", "Chiffrage en 30 secondes",
     "En trente secondes, vous obtenez une fourchette de prix, le détail par corps de métier, la répartition matériaux et main-d'œuvre, la durée du chantier et le planning des phases, en trois gammes : économique, standard et premium."),
    ("piscine_result", "Piscines : bordereau automatique",
     "Pour une piscine, ConstruPilot propose automatiquement les ouvrages de sa bibliothèque : terrassement, radier, blocs à bancher, liner, margelles, filtration et local technique, dimensionnés à partir de la surface du bassin. Les professionnels créent le devis en un clic."),
    ("smart_project", "Smart Project — décrivez, l'IA chiffre",
     "Avec Smart Project, décrivez simplement votre chantier, à l'écrit ou à la voix. L'intelligence artificielle identifie les lots, les matériaux et le budget."),
    ("calculateurs", "Calculateurs de matériaux",
     "Les calculateurs de matériaux donnent les quantités exactes : peinture, carrelage, béton, parpaings, mortier ou enduit, avec la liste d'achats correspondante."),
    ("prix", "Bibliothèque de prix : 322 ouvrages",
     "La bibliothèque ConstruPilot regroupe plus de trois cents ouvrages chiffrés, avec un prix bas, médian et haut, mis à jour depuis les référentiels du marché."),
    ("photo", "Analyse photo par IA",
     "Envoyez une photo d'une pièce ou d'un désordre : l'intelligence artificielle identifie les travaux à prévoir et les points de vigilance."),
    ("devis_editeur", "Éditeur de devis professionnel",
     "Côté professionnels, l'éditeur de devis est le cœur de l'application. Les lignes se chiffrent automatiquement depuis la bibliothèque ConstruPilot ou celle de votre entreprise. Dictez votre chantier, filmez-le, importez un CCTP ou un plan : le devis se construit tout seul."),
    ("bibliotheque", "Votre bibliothèque d'entreprise",
     "Chaque entreprise dispose de sa propre bibliothèque de prix, alimentée depuis Excel, depuis d'anciens devis PDF ou directement depuis l'éditeur, avec le coût de revient de chaque ouvrage."),
    ("devis_suivi", "Suivi des devis et signature en ligne",
     "Le suivi des devis indique les envois, les ouvertures et les signatures. Vos clients signent en ligne et peuvent régler un acompte par carte au moment de la signature."),
    ("factures", "Factures, situations, Factur-X",
     "Transformez le devis en facture d'acompte, en situation de travaux ou en facture de solde, avec le décompte général et la facturation électronique Factur-X."),
    ("clients", "CRM clients et projets",
     "Le CRM centralise vos clients, leurs projets, leurs devis et leurs factures, ainsi que les demandes reçues de particuliers."),
    ("plan", "Lecture de plans DWG, DXF et PDF",
     "Importez un plan au format DWG, DXF, PDF ou photo. ConstruPilot le rend fidèlement, détecte les pièces, les murs, les poteaux et les poutres, calcule le métré béton et génère le devis correspondant."),
    ("etudes_pc", "Étude permis de construire",
     "L'étude permis de construire estime le gros œuvre niveau par niveau, produit le planning Gantt, compare les négoces et prépare les bons de commande."),
    ("appro", "Approvisionnement et fournisseurs",
     "Le module approvisionnement lit les plans de ferraillage, d'étanchéité, de toiture et de réseaux pour produire des bordereaux commandables, exportables et envoyés à vos fournisseurs."),
    ("radar", "Radar Chantiers : prospection",
     "Le Radar Chantiers affiche les permis de construire autour de votre entreprise. Générez un courrier de prospection avec QR code, rédigé par l'IA, et envoyez-le par la poste directement depuis l'application. Les réponses arrivent dans votre CRM."),
    ("rentabilite", "Rapport de rentabilité",
     "Le rapport de rentabilité compare, chantier par chantier et mois par mois, le prix vendu, le coût prévu au devis et les achats réels, pour connaître votre marge réelle."),
    ("suivi_chantier", "Suivi de chantier et équipes",
     "Avec Pro Business, suivez l'avancement des chantiers avec photos et coûts réels, gérez vos équipes, les ressources humaines et le pointage des ouvriers sur mobile."),
    ("rendu_ia", "Rendus 3D par IA",
     "Transformez un plan en rendu photoréaliste, en vidéo 3D ou en maquette interactive à partager avec vos clients."),
    ("blog", "Blog, SEO et newsletter",
     "Le blog ConstruPilot publie automatiquement des articles conseils travaux, en français et en portugais, avec une newsletter pour vos lecteurs."),
    ("tarifs", "Offres : gratuit, Premium, Pro, Pro Business",
     "ConstruPilot est gratuit pour les particuliers, dix-neuf euros par mois en Premium, cent quarante-neuf euros pour les professionnels et deux cent quarante-neuf euros pour les entreprises, avec sept jours d'essai."),
    ("fonctionnalites", "construpilot.fr",
     "Estimez, comparez, construisez. Rendez-vous sur construpilot point fr pour créer votre compte gratuitement."),
]

FULL_PT = [
    ("landing", "ConstruPilot — Estime. Compare. Constrói.",
     "Bem-vindo ao ConstruPilot, a plataforma tudo-em-um da construção. Estimativa de obras por inteligência artificial, leitura de plantas, orçamentos, faturas, aprovisionamento e prospeção: uma única aplicação para particulares e profissionais."),
    ("estimation_form", "Estimador de obras",
     "Tudo começa no estimador. Escolha o tipo de projeto — remodelação, construção, ampliação ou piscina — a área, o distrito e o estado do imóvel."),
    ("estimation_result", "Orçamento em 30 segundos",
     "Em trinta segundos obtém um intervalo de preços, o detalhe por especialidade, a repartição entre materiais e mão de obra, a duração da obra e o planeamento das fases, em três gamas: económica, standard e premium."),
    ("piscine_result", "Piscinas: mapa de trabalhos automático",
     "Para uma piscina, o ConstruPilot propõe automaticamente os trabalhos da sua biblioteca: escavação, laje de fundo, blocos de cofragem, liner, bordaduras, filtração e casa das máquinas, dimensionados a partir da área do tanque. Os profissionais criam o orçamento com um clique."),
    ("smart_project", "Smart Project — descreva, a IA orça",
     "Com o Smart Project, descreva simplesmente a sua obra, por escrito ou por voz. A inteligência artificial identifica as especialidades, os materiais e o orçamento."),
    ("calculateurs", "Calculadoras de materiais",
     "As calculadoras de materiais dão as quantidades exatas: pintura, azulejo, betão, blocos, argamassa ou reboco, com a lista de compras correspondente."),
    ("prix", "Biblioteca de preços: 322 trabalhos",
     "A biblioteca ConstruPilot reúne mais de trezentos trabalhos orçamentados, com preço baixo, mediano e alto, atualizados a partir dos referenciais do mercado."),
    ("photo", "Análise de fotografia por IA",
     "Envie a fotografia de uma divisão ou de uma patologia: a inteligência artificial identifica os trabalhos a prever e os pontos de atenção."),
    ("devis_editeur", "Editor de orçamentos profissional",
     "Para os profissionais, o editor de orçamentos é o coração da aplicação. As linhas são orçamentadas automaticamente a partir da biblioteca ConstruPilot ou da biblioteca da sua empresa. Dite a obra, filme-a, importe um caderno de encargos ou uma planta: o orçamento constrói-se sozinho."),
    ("bibliotheque", "A biblioteca da sua empresa",
     "Cada empresa tem a sua própria biblioteca de preços, alimentada a partir de Excel, de antigos orçamentos em PDF ou diretamente do editor, com o custo de cada trabalho."),
    ("devis_suivi", "Acompanhamento e assinatura online",
     "O acompanhamento dos orçamentos indica os envios, as aberturas e as assinaturas. Os seus clientes assinam online e podem pagar um sinal por cartão no momento da assinatura."),
    ("factures", "Faturas, autos de medição, fatura eletrónica",
     "Transforme o orçamento em fatura de sinal, em auto de medição ou em fatura final, com o resumo geral e a faturação eletrónica."),
    ("clients", "CRM de clientes e projetos",
     "O CRM centraliza os seus clientes, os seus projetos, orçamentos e faturas, bem como os pedidos recebidos de particulares."),
    ("plan", "Leitura de plantas DWG, DXF e PDF",
     "Importe uma planta em DWG, DXF, PDF ou fotografia. O ConstruPilot reproduz-a fielmente, deteta as divisões, paredes, pilares e vigas, calcula as medições de betão e gera o orçamento correspondente."),
    ("etudes_pc", "Estudo de licenciamento",
     "O estudo de licenciamento estima a estrutura piso a piso, produz o cronograma de Gantt, compara fornecedores e prepara as notas de encomenda."),
    ("appro", "Aprovisionamento e fornecedores",
     "O módulo de aprovisionamento lê as plantas de armaduras, impermeabilização, cobertura e redes para produzir mapas de quantidades encomendáveis, exportáveis e enviados aos seus fornecedores."),
    ("radar", "Radar de Obras: prospeção",
     "O Radar de Obras mostra as licenças de construção à volta da sua empresa. Gere uma carta de prospeção com código QR, redigida pela IA, e envie-a pelo correio diretamente a partir da aplicação. As respostas chegam ao seu CRM."),
    ("rentabilite", "Relatório de rentabilidade",
     "O relatório de rentabilidade compara, obra a obra e mês a mês, o preço vendido, o custo previsto no orçamento e as compras reais, para conhecer a sua margem real."),
    ("suivi_chantier", "Acompanhamento de obra e equipas",
     "Com o Pro Business, acompanhe o avanço das obras com fotografias e custos reais, gira as suas equipas, os recursos humanos e o registo de ponto dos trabalhadores no telemóvel."),
    ("rendu_ia", "Renderizações 3D por IA",
     "Transforme uma planta numa renderização fotorrealista, num vídeo 3D ou numa maquete interativa para partilhar com os seus clientes."),
    ("blog", "Blog, SEO e newsletter",
     "O blog ConstruPilot publica automaticamente artigos de conselhos sobre obras, em francês e em português, com uma newsletter para os seus leitores."),
    ("tarifs", "Planos: grátis, Premium, Pro, Pro Business",
     "O ConstruPilot é gratuito para particulares, dezanove euros por mês no Premium, cento e quarenta e nove euros para profissionais e duzentos e quarenta e nove euros para empresas, com sete dias de teste."),
    ("fonctionnalites", "construpilot.pt",
     "Estime, compare, construa. Visite construpilot ponto pt e crie a sua conta gratuitamente."),
]

SHORT_KEYS = ["landing", "estimation_result", "smart_project", "devis_editeur", "plan", "devis_suivi",
              "factures", "appro", "radar", "rentabilite", "fonctionnalites"]
SHORT = [s for s in FULL if s[0] in SHORT_KEYS]
SHORT_PT = [s for s in FULL_PT if s[0] in SHORT_KEYS]
LANG = "fr"
TXT = {"fr": ("Toutes les fonctionnalités en images — démonstration", "Estimez. Comparez. Construisez. — Essai gratuit 7 jours", "Démonstration complète", "Démonstration", "construpilot.fr"),
       "pt": ("Todas as funcionalidades em imagens — demonstração", "Estime. Compare. Construa. — 7 dias grátis", "Demonstração completa", "Demonstração", "construpilot.pt")}


def sh(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out)


ELEVEN_VOICES = {"pt": os.environ.get("DEMO_VOICE_PT_ID", "ejarTsrf33xoVlH9hMuy"),   # Luis — European Portuguese
                 "fr": os.environ.get("DEMO_VOICE_FR_ID", "aQROLel5sQbj1vuIVi6B")}   # Nicolas — Narrator (parisien)


def tts_elevenlabs(text: str) -> bytes:
    from elevenlabs import ElevenLabs, VoiceSettings
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    if LANG == "pt":  # voix plus vivante : Eleven v3 (expressif)
        gen = client.text_to_speech.convert(text=text, voice_id=ELEVEN_VOICES[LANG], model_id="eleven_v3",
                                            output_format="mp3_44100_128",
                                            voice_settings=VoiceSettings(stability=0.3, similarity_boost=0.8, style=0.6, use_speaker_boost=True))
    else:
        gen = client.text_to_speech.convert(text=text, voice_id=ELEVEN_VOICES[LANG], model_id="eleven_multilingual_v2",
                                            output_format="mp3_44100_128",
                                            voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.8, style=0.2, use_speaker_boost=True))
    return b"".join(gen)


async def tts_all(scenes):
    from emergentintegrations.llm.openai import OpenAITextToSpeech
    tts = OpenAITextToSpeech(api_key=os.environ["EMERGENT_LLM_KEY"])
    os.makedirs(f"{WORK}/tts_{LANG}", exist_ok=True)
    for slug, _, text in scenes:
        path = f"{WORK}/tts_{LANG}/{slug}.mp3"
        if os.path.exists(path):
            continue
        if os.environ.get("ELEVENLABS_API_KEY"):
            data = tts_elevenlabs(text)  # voix natives ElevenLabs (FR / PT)
        else:
            audio = await tts.generate_speech(text=text, model="tts-1", voice=VOICE, response_format="mp3", speed=1.0)
            data = audio if isinstance(audio, (bytes, bytearray)) else getattr(audio, "content", None)
        open(path, "wb").write(data)
        print("tts", slug, round(duration(path), 1), "s")


def card(path, title, subtitle, size):
    w, h = size
    im = Image.new("RGB", size, "#04120a")
    d = ImageDraw.Draw(im)
    d.ellipse([w * 0.72, -h * 0.25, w * 1.25, h * 0.55], fill="#16211c")
    d.rectangle([0, h * 0.62, w, h * 0.62 + 4], fill="#a3e635")
    logo = Image.open(LOGO).convert("RGBA")
    lw = int(w * (0.28 if w > h else 0.5))
    logo = logo.resize((lw, int(logo.height * lw / logo.width)))
    im.paste(logo, (int(w * 0.07), int(h * 0.12)), logo)
    f1 = ImageFont.truetype(FONT_B, int(w * (0.05 if w > h else 0.075)))
    f2 = ImageFont.truetype(FONT_R, int(w * (0.022 if w > h else 0.036)))
    d.text((w * 0.07, h * 0.66), title, font=f1, fill="white")
    y = h * 0.66 + f1.size * 1.4
    for line in textwrap.wrap(subtitle, 60 if w > h else 34):
        d.text((w * 0.07, y), line, font=f2, fill="#a3e635")
        y += f2.size * 1.5
    im.save(path)


def frame_portrait(src, dst):
    """Écran 16:9 posé sur un fond flou 9:16 (1080x1920)."""
    im = Image.open(src).convert("RGB")
    bg = im.resize((1080, int(1080 * im.height / im.width)))
    bg = bg.resize((1080, 1920)).resize((54, 96)).resize((1080, 1920))  # flou grossier
    bg = Image.eval(bg, lambda v: int(v * 0.45))
    fg_w = 1020
    fg = im.resize((fg_w, int(im.height * fg_w / im.width)))
    canvas = bg.copy()
    canvas.paste(fg, ((1080 - fg_w) // 2, 520))
    canvas.save(dst)


def _caption(w, h, tf):
    fs = int(w * 0.026) if w > h else int(w * 0.042)
    box_y = int(h * 0.055) if w > h else int(h * 0.14)
    return (f"drawtext=fontfile={FONT_B}:textfile={tf}:fontsize={fs}:fontcolor=white:x={int(w*0.04)}:y={box_y}:"
            f"box=1:boxcolor=0x04120a@0.78:boxborderw={int(fs*0.6)}")


def clip(img, audio, title, out, size, video=None, offset=0.0):
    """Scène = image fixe (zoom lent) ou enregistrement d'écran animé, ajusté à la durée de la voix off."""
    w, h = size
    dur = duration(audio) + 0.8
    tf = out + ".txt"
    open(tf, "w").write(title)
    draw = _caption(w, h, tf)
    fades = f"fade=t=in:st=0:d=0.4,fade=t=out:st={dur-0.4:.2f}:d=0.4,format=yuv420p"
    if video:
        avail = duration(video) - offset
        speed = f"setpts=PTS/{avail / dur:.4f}," if avail > dur + 0.5 else ""  # accélère légèrement si trop long
        if w > h:
            vsrc = f"[0:v]trim=start={offset:.2f},setpts=PTS-STARTPTS,{speed}scale={w}:{h},tpad=stop_mode=clone:stop_duration=60,trim=0:{dur:.2f},setpts=PTS-STARTPTS,{draw},{fades}[v]"
        else:
            vsrc = (f"[0:v]trim=start={offset:.2f},setpts=PTS-STARTPTS,{speed}tpad=stop_mode=clone:stop_duration=60,trim=0:{dur:.2f},setpts=PTS-STARTPTS,split[a][b];"
                    f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=24:2,eq=brightness=-0.25[bg];"
                    f"[b]scale=1020:-2[fg];[bg][fg]overlay=(W-w)/2:520,{draw},{fades}[v]")
        sh(["ffmpeg", "-y", "-i", video, "-i", audio, "-filter_complex", f"{vsrc};[1:a]adelay=300|300,apad[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-r", "30", out])
        return dur
    zoom = f"zoompan=z='min(zoom+0.0006,1.09)':d={int(dur * 30) + 1}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=30"
    vf = f"{zoom},{draw},{fades}"
    sh(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", img, "-i", audio,
        "-filter_complex", f"[0:v]{vf}[v];[1:a]adelay=300|300,apad[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", "-r", "30", out])
    return dur


def build(scenes, name, portrait=False):
    size = (1080, 1920) if portrait else (1920, 1080)
    tag = "9x16" if portrait else "16x9"
    d = f"{WORK}/{name}_{tag}"
    os.makedirs(d, exist_ok=True)
    parts, total = [], 0.0
    intro_img, outro_img = f"{d}/intro.png", f"{d}/outro.png"
    t_intro, t_outro, t_full, t_short, site = TXT[LANG]
    card(intro_img, "ConstruPilot", t_intro, size)
    card(outro_img, site, t_outro, size)
    silence = f"{WORK}/silence.mp3"
    if not os.path.exists(silence):
        sh(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "2.2", "-q:a", "9", silence])
    total += clip(intro_img, silence, t_full if len(scenes) > 12 else t_short, f"{d}/00_intro.mp4", size)
    parts.append(f"{d}/00_intro.mp4")
    for i, (slug, title, _) in enumerate(scenes, 1):
        out = f"{d}/{i:02d}_{slug}.mp4"
        vid = f"{CLIPS}/{slug}.webm"
        if os.path.exists(vid):
            total += clip(None, f"{WORK}/tts_{LANG}/{slug}.mp3", title, out, size, video=vid, offset=META.get(slug, 2.0))
            parts.append(out)
            continue
        src = f"{SHOTS}/{slug}.png"
        if portrait:
            src2 = f"{d}/{slug}_p.png"
            frame_portrait(src, src2)
            src = src2
        total += clip(src, f"{WORK}/tts_{LANG}/{slug}.mp3", title, out, size)
        parts.append(out)
    total += clip(outro_img, silence, site, f"{d}/99_outro.mp4", size)
    parts.append(f"{d}/99_outro.mp4")
    lst = f"{d}/list.txt"
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    final = f"{OUT}/{name}_{tag}.mp4"
    sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", final])
    print("built", final, round(total), "s", round(os.path.getsize(final) / 1e6, 1), "MB")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    use_clips("fr")
    if which == "pt":
        LANG = "pt"
        use_clips("pt")
        asyncio.run(tts_all(FULL_PT))
        build(SHORT_PT, "ConstruPilot_Demo_Curta_PT")
        build(SHORT_PT, "ConstruPilot_Demo_Curta_PT", portrait=True)
        build(FULL_PT, "ConstruPilot_Demo_Completa_PT")
        sys.exit(0)
    asyncio.run(tts_all(FULL))
    if which in ("all", "short"):
        build(SHORT, "ConstruPilot_Demo_Courte")
        build(SHORT, "ConstruPilot_Demo_Courte", portrait=True)
    if which in ("all", "full"):
        build(FULL, "ConstruPilot_Demo_Complete")
        build(FULL, "ConstruPilot_Demo_Complete", portrait=True)
