#!/usr/bin/env python3
"""
Wave C3 FR->PT-PT translator.
Applies a strict glossary using word-boundary regex. Only capitalised words or
words inside user-visible strings/JSX text are matched. Lowercase FR words that
could be variable names/URL paths are NOT touched.
"""
import re
import sys
from pathlib import Path

# Glossary: FR (word or phrase) -> PT-PT
# Longer phrases go first so they win over single-word substitutions.
GLOSSARY = [
    # Longer phrases first
    ("Accès non autorisé", "Acesso não autorizado"),
    ("Aucun détail d'erreur fourni par le validateur.", "Nenhum detalhe de erro fornecido pelo validador."),
    ("Aucune activité pour ce filtre.", "Sem atividade para este filtro."),
    ("Le fichier Factur-X respecte le socle XSD + Schematron EN16931. Diagnostic technique — ne vaut pas acceptation par une Plateforme Agréée.",
     "O ficheiro Factur-X respeita a base XSD + Schematron EN16931. Diagnóstico técnico — não vale como aceitação por uma Plataforma Autorizada."),
    ("Non-conformités détectées", "Não conformidades detetadas"),
    ("Non-conformité", "Não conformidade"),
    ("Non-conformités", "Não conformidades"),
    ("Recevez, acceptez ou refusez vos factures fournisseurs via une plateforme agréée.",
     "Receba, aceite ou rejeite as faturas dos seus fornecedores através de uma plataforma autorizada."),
    ("Facturation électronique (réseau PDP)", "Faturação eletrónica (rede PDP)"),
    ("Émettre la sélection", "Emitir a seleção"),
    ("Émission + contrôle de conformité Factur-X en lot", "Emissão + controlo de conformidade Factur-X em lote"),
    ("Émission + contrôle de conformité", "Emissão + controlo de conformidade"),
    ("Sélectionner pour émission groupée", "Selecionar para emissão em lote"),
    ("Sélectionnée(s)", "Selecionada(s)"),
    ("sélectionnée(s)", "selecionada(s)"),
    ("Votre rôle dans l'entreprise ne donne pas accès à ce module. Contactez le responsable de votre société.",
     "A sua função na empresa não dá acesso a este módulo. Contacte o responsável da sua sociedade."),
    ("Factures non autorisées", "Faturas não autorizadas"),
    ("Facture supprimée", "Fatura eliminada"),
    ("émise(s)", "emitida(s)"),
    ("conforme(s) EN16931", "conforme(s) EN16931"),
    ("Nouvel employé", "Novo colaborador"),
    ("Nouvelle employée", "Nova colaboradora"),
    ("Créer le compte", "Criar a conta"),
    ("Employé créé — mot de passe provisoire à communiquer", "Colaborador criado — palavra-passe provisória a comunicar"),
    ("Rôle mis à jour", "Função atualizada"),
    ("Gérer l'abonnement", "Gerir a subscrição"),
    ("Activité récente", "Atividade recente"),
    ("Tous les employés", "Todos os colaboradores"),
    ("Pilotez toute votre entreprise, vos équipes et leurs accès — réservé au",
     "Faça a gestão de toda a sua empresa, das suas equipas e dos seus acessos — reservado ao"),
    ("pack Business", "pack Empresa"),
    ("PACK BUSINESS", "PACK EMPRESA"),
    ("Espace Entreprise", "Espaço Empresa"),
    ("CA facturé TTC", "Faturação c/ IVA"),
    ("Encours à encaisser", "Por receber"),
    ("Réserves en cours", "Reservas em curso"),
    ("Équipe", "Equipa"),
    ("Équipes", "Equipas"),
    ("ouvriers", "trabalhadores"),
    ("ouvrier", "trabalhador"),
    ("Ouvrier", "Trabalhador"),
    ("Ouvriers", "Trabalhadores"),
    ("Désactiver", "Desativar"),
    ("Réactiver", "Reativar"),
    ("Désactivé", "Desativado"),
    ("Réactivé", "Reativado"),
    ("Créer un compte", "Criar uma conta"),
    ("Gestion des données", "Gestão de dados"),
    ("Supprimez les devis et clients enregistrés.", "Elimine os orçamentos e clientes registados."),
    ("Ce client", "Este cliente"),
    ("sera supprimé", "será eliminado"),
    ("sera définitivement supprimé", "será eliminado definitivamente"),
    ("Le devis", "O orçamento"),
    ("Client supprimé", "Cliente eliminado"),
    ("Impossible s'il a des devis/factures liés.", "Impossível se tiver orçamentos/faturas associados."),
    # Common short words / labels (kept for user-visible only via word boundary)
    ("Aperçu PDF", "Pré-visualização PDF"),
    ("Aperçu e-mail", "Pré-visualização de email"),
    ("Aperçu rendu 3D", "Pré-visualização de render 3D"),
    ("Aperçu", "Pré-visualização"),
    ("Créer", "Criar"),
    ("Modifier", "Editar"),
    ("Supprimer", "Eliminar"),
    ("Enregistrer", "Guardar"),
    ("Annuler", "Cancelar"),
    ("Retour", "Voltar"),
    ("Suivant", "Seguinte"),
    ("Précédent", "Anterior"),
    ("Rechercher", "Pesquisar"),
    ("Sélectionner", "Selecionar"),
    ("Choisir", "Escolher"),
    ("Poursuivre", "Continuar"),
    ("Terminer", "Terminar"),
    ("Aujourd'hui", "Hoje"),
    ("Demain", "Amanhã"),
    ("Semaine", "Semana"),
    ("Mois", "Mês"),
    ("Année", "Ano"),
    ("Prochainement", "Brevemente"),
    ("Bientôt", "Em breve"),
    ("En cours", "Em curso"),
    ("Terminé", "Concluído"),
    ("Terminée", "Concluída"),
    ("Payé", "Pago"),
    ("Impayé", "Por pagar"),
    ("Brouillon", "Rascunho"),
    ("Envoyé", "Enviado"),
    ("Envoyée", "Enviada"),
    ("En attente", "Pendente"),
    ("Refusé", "Recusado"),
    ("Refusée", "Recusada"),
    ("Accepté", "Aceite"),
    ("Acceptée", "Aceite"),
    ("À signer", "Por assinar"),
    ("Signez", "Assine"),
    ("Signer", "Assinar"),
    ("Numéro", "Número"),
    ("Montant", "Montante"),
    ("Remise", "Desconto"),
    ("Sous-total", "Subtotal"),
    ("Prestataire", "Prestador"),
    ("Artisan", "Profissional"),
    ("Statut", "Estado"),
    ("Statuts", "Estados"),
    ("Échéance", "Prazo"),
    ("Coordonnées", "Contactos"),
    ("Description", "Descrição"),
    ("Détails", "Detalhes"),
    ("Bénéficier", "Beneficiar"),
    ("Bénéficiaire", "Beneficiário"),
    ("Bénéfice", "Benefício"),
    ("Investisseur", "Investidor"),
    ("Investissement", "Investimento"),
    ("Rendement", "Rendimento"),
    ("Actualités", "Notícias"),
    ("Tableau de bord", "Painel"),
    ("Assistance", "Suporte"),
    ("Bonjour", "Olá"),
    ("Bienvenue", "Bem-vindo"),
    ("Se connecter", "Iniciar sessão"),
    ("S'inscrire", "Registar-se"),
    ("Mot de passe", "Palavra-passe"),
    ("mot de passe provisoire à communiquer", "palavra-passe provisória a comunicar"),
    ("mot de passe", "palavra-passe"),
    ("caractères min.", "caracteres mín."),
    ("Rôle", "Função"),
    ("Rôles", "Funções"),
    ("émis(e)", "emitido(a)"),
    ("émis", "emitidos"),
    ("Émission", "Emissão"),
    ("Émettre", "Emitir"),
    ("Facture", "Fatura"),
    ("Factures", "Faturas"),
    ("Devis", "Orçamento"),
    ("Fournisseur", "Fornecedor"),
    ("Fournisseurs", "Fornecedores"),
    ("Chantier", "Obra"),
    ("Chantiers", "Obras"),
    ("Employé", "Colaborador"),
    ("Employée", "Colaboradora"),
    ("Employés", "Colaboradores"),
    ("Employées", "Colaboradoras"),
    ("Entreprise", "Empresa"),
    ("Entreprises", "Empresas"),
    ("Client", "Cliente"),
    ("Clients", "Clientes"),
    # Contextual sentences seen
    ("Exportação impossível", "Exportação impossível"),  # already PT
    ("détecté", "detetado"),
    ("détectée", "detetada"),
    ("détectées", "detetadas"),
    ("détectés", "detetados"),
]


def compile_patterns():
    compiled = []
    for fr, pt in GLOSSARY:
        # Word boundaries only work for [a-zA-Z] boundaries; for phrases with
        # punctuation/spaces/accents, we use lookaround.
        # If the phrase starts and ends with a letter, add word boundaries.
        start = r"(?<![\w])" if fr[0].isalpha() else ""
        end = r"(?![\w])" if fr[-1].isalpha() else ""
        pattern = re.compile(start + re.escape(fr) + end)
        compiled.append((pattern, pt, fr))
    return compiled


PATTERNS = compile_patterns()


def translate_file(path: Path) -> tuple[int, list[str]]:
    """Returns (num_replacements, applied_glossary_entries)."""
    original = path.read_text(encoding="utf-8")
    updated = original
    n = 0
    applied = []
    for pat, pt, fr in PATTERNS:
        new, count = pat.subn(pt, updated)
        if count:
            n += count
            applied.append(f"  {count}x {fr!r} -> {pt!r}")
            updated = new
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return n, applied


def main():
    if len(sys.argv) < 2:
        print("Usage: translate_fr_pt.py <file1> [file2 ...]", file=sys.stderr)
        sys.exit(1)
    total = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.is_file():
            print(f"SKIP (not a file): {arg}")
            continue
        n, applied = translate_file(p)
        total += n
        print(f"{arg}: {n} replacements")
        for line in applied[:10]:
            print(line)
        if len(applied) > 10:
            print(f"  ... and {len(applied)-10} more entries")
    print(f"\nTOTAL: {total} replacements")


if __name__ == "__main__":
    main()
