#!/usr/bin/env python3
"""Final pass: hand-crafted mapping for residual FR strings."""
import re
import sys
from pathlib import Path

# EXACT string mapping (no regex needed since these are unique full-string matches)
EXACT = {
    "Activer": "Ativar",
    "Assistant indisponível": "Assistente indisponível",
    "Ce plan ressemble à un plan de structure/béton (aciers, cotes, hachures). La détection de paredes y est peu fiable — utilisez plutôt le Medição béton.":
        "Este plano assemelha-se a um plano de estrutura/betão (aços, cotas, tramas). A deteção de paredes é pouco fiável — use antes a Medição de betão.",
    "Chargement impossible": "Carregamento impossível",
    "Definições réinitialisés aux valeurs par défaut": "Definições reinicializadas para os valores por omissão",
    "Demande assignée — le pro est notifié": "Pedido atribuído — o profissional foi notificado",
    "Détection auto": "Deteção automática",
    "Détection paredes impossible": "Deteção de paredes impossível",
    "Email não enviado (cliente sem email ou serviço indisponível)": "Email não enviado (cliente sem email ou serviço indisponível)",
    "Estudo acceptée — merci !": "Estudo aceite — obrigado!",
    "Importer des PDF": "Importar PDF",
    "Installation chantier (base vie, clôture, benne)": "Instalação de obra (contentor social, vedação, contentor de resíduos)",
    "Maquette interactive indisponível": "Maqueta interativa indisponível",
    "Paiement indisponível (réessayez)": "Pagamento indisponível (tente novamente)",
    "Paiement indisponível — réessayez plus tard": "Pagamento indisponível — tente novamente mais tarde",
    "Photos indisponibles": "Fotografias indisponíveis",
    "Poteau ajouté — glissez ses coins pour l'ajuster": "Pilar adicionado — arraste os cantos para ajustar",
    "Poutre ajoutée — glissez ses extremidades pour la placer": "Viga adicionada — arraste as extremidades para a posicionar",
    "Pris en charge": "Assumido",
    "Projet sans nom": "Projeto sem nome",
    "Pré-visualização indisponível": "Pré-visualização indisponível",
    "Quitter le plein écran (Échap)": "Sair do ecrã inteiro (Esc)",
    "Redirection vers le paiement…": "A redirecionar para o pagamento…",
    "Refuser la facture": "Rejeitar a fatura",
    "Relâchez pour importer": "Solte para importar",
    "Render 3D généré !": "Render 3D gerado!",
    "Render généré !": "Render gerado!",
    "Renseignez l'email du client": "Indique o email do cliente",
    "Régler le contraste et la luminosité du plan": "Ajustar o contraste e a luminosidade do plano",
    "Réseau indisponível ou fichier trop lourd — verifique votre connexion et réessayez":
        "Rede indisponível ou ficheiro demasiado pesado — verifique a sua ligação e tente novamente",
    "Sans titre": "Sem título",
    "Sauvegarde de la structure impossible": "Gravação da estrutura impossível",
    "Selecionar un chantier…": "Selecionar uma obra…",
    "Selecionar une commande…": "Selecionar uma encomenda…",
    "Semelle ajoutée — glissez ses coins pour l'ajuster": "Sapata adicionada — arraste os cantos para ajustar",
    "Signature du client": "Assinatura do cliente",
    "Sélectionnez au moins 1 plan": "Selecione pelo menos 1 plano",
    "Textes analysés — rien à modifier": "Textos analisados — nada a alterar",
    "Tour vidéo 3D généré !": "Visita em vídeo 3D gerada!",
    "Toutes les mesures ont été effacées — pronto pour un nouveau devis":
        "Todas as medições foram apagadas — pronto para um novo orçamento",
    "Type de plan pour l'análise IA": "Tipo de plano para a análise IA",
    "Téléchargement impossible": "Descarga impossível",
    "Téléchargements pitch deck (VC)": "Descargas do pitch deck (VC)",
    "Une compartimento nécessite au moins 3 points": "Um compartimento necessita de pelo menos 3 pontos",
    "Une surface nécessite au moins 3 points": "Uma superfície necessita de pelo menos 3 pontos",
    "Verrouiller le plan (bloquer zoom + déplacement pour des clics précis)":
        "Bloquear o plano (bloquear zoom + deslocação para cliques precisos)",
    "Votre commande…": "A sua encomenda…",
    "Votre consigne pour l'IA…": "A sua instrução para a IA…",
    "Votre interlocuteur": "O seu interlocutor",
    "Votre nom complet": "O seu nome completo",
    "Vue 3D jointe — elle sera ajoutée au próximo devis généré desde ce plan":
        "Vista 3D anexada — será adicionada ao próximo orçamento gerado a partir deste plano",
    "\\n(laisser vide = e-mail du compte)": "\\n(deixe vazio = email da conta)",
    "aucun": "nenhum",
    "nouveau": "novo",
    "votre projet": "o seu projeto",
    "Écrivez d'abord un message à enregistrer": "Escreva primeiro uma mensagem a gravar",
    # Additional common leftovers
    "Poteau": "Pilar",
    "Poutre": "Viga",
    "Semelle": "Sapata",
    "Récupération": "Recuperação",
    "Impossible": "Impossível",
    "impossible": "impossível",
    "Aciers": "Aços",
    "aciers": "aços",
    "Hachures": "Tramas",
    "hachures": "tramas",
    "Réessayez": "Tente novamente",
    "réessayez": "tente novamente",
    "Réinitialiser": "Reinicializar",
    "Réinitialisé": "Reinicializado",
    "Réinitialisée": "Reinicializada",
    "Notifié": "Notificado",
    "notifié": "notificado",
    "Verrouiller": "Bloquear",
    "Déverrouiller": "Desbloquear",
    "Plein écran": "Ecrã inteiro",
    "plein écran": "ecrã inteiro",
    "Contraste": "Contraste",
    "Luminosité": "Luminosidade",
    "Interlocuteur": "Interlocutor",
    "interlocuteur": "interlocutor",
    "Consigne": "Instrução",
    "consigne": "instrução",
    "Commande": "Encomenda",
    "commande": "encomenda",
    "Sauvegarde": "Gravação",
    "sauvegarde": "gravação",
    "Rejoindre": "Aceder",
    "rejoindre": "aceder",
    "Réseau": "Rede",
    "réseau": "rede",
}


def apply(path: Path) -> int:
    if not path.is_file():
        return 0
    s = path.read_text(encoding="utf-8")
    orig = s
    # Sort by length desc so longer phrases first
    for fr in sorted(EXACT.keys(), key=len, reverse=True):
        pt = EXACT[fr]
        if fr[0].isalpha() and fr[-1].isalpha():
            pattern = re.compile(r"(?<![\w])" + re.escape(fr) + r"(?![\w])")
            s = pattern.sub(pt, s)
        else:
            s = s.replace(fr, pt)
    if s != orig:
        path.write_text(s, encoding="utf-8")
        # Count roughly by diffing lines
        return sum(1 for a, b in zip(orig.splitlines(), s.splitlines()) if a != b)
    return 0


def main():
    total = 0
    for arg in sys.argv[1:]:
        n = apply(Path(arg))
        total += n
        print(f"{arg}: {n} lines changed")
    print(f"TOTAL lines changed: {total}")


if __name__ == "__main__":
    main()
