# Intégration de `bet_core` dans l'Assistant (construpilot.fr et construpilot.pt)

`bet_core` est autonome : il ne dépend que de `reportlab`, `pypdf`, `ezdxf`, `openpyxl`, `PyMuPDF` (déjà présents) et, pour la
seule lecture des plans, de `engines/anthropic_native.py` (clé `ANTHROPIC_API_KEY`, modèle `ANTHROPIC_MODEL_OPUS`).

## 1. Fichiers à copier tels quels (branche `claude/bet-core-hybride`)

```
backend/engines/bet_core/**          (moteurs, pipeline.py, reader.py, assistant_tool.py, cases/, i18n.py, profiles.py)
backend/tests/bet_core/**
```

## 2. Patch de `backend/routes/assistant.py` (5 insertions, rien n'est supprimé)

Repères par texte (le fichier de l'espace Emergent peut différer de GitHub : appliquer chaque insertion à l'endroit indiqué).

1. Après la ligne `from engines.autodesk_md_tools import ...` :
```python
from engines.bet_core.assistant_tool import (TOOLS as BET_TOOLS, TOOL_NAMES as BET_TOOL_NAMES,  # étude BET complète
                                            INSTRUCTIONS as BET_INSTRUCTIONS, execute as execute_bet_tool)
```
2. Dans la liste `TOOLS = [...]`, après `*AUTODESK_TOOLS,` : `*BET_TOOLS,`
   (les comptes particuliers ne les reçoivent pas : ils ne sont pas dans `INDIVIDUAL_TOOL_NAMES`).
3. Dans `_exec_tool`, juste avant `if name == "estimate_budget_range":` :
```python
    if name in BET_TOOL_NAMES:
        if account_type(user) == "individual":
            return {"error": "Étude BET réservée aux comptes professionnels", "status": "échoué"}
        return await execute_bet_tool(name, args, user, conv, db)
```
4. Dans la construction des instructions, après `instructions += QUOTE_INSTRUCTIONS` : `instructions += BET_INSTRUCTIONS`
5. Dans `TOOL_STATUS`, ajouter :
```python
"generate_full_bet_study": "Lancement de l'étude BET complète (lecture des plans, calculs, plans cotés, devis)…",
"read_full_bet_study": "Lecture de l'avancement de l'étude BET…",
```

Collection MongoDB créée à la volée : `bet_study_jobs` (index conseillé : `{job_id: 1}` unique, `{user_id: 1, created_at: -1}`).
Les livrables vont dans `assistant_artifacts` (même format que `create_downloadable_file`) et se téléchargent par la route
existante `/assistant/artifacts/{artifact_id}/content`. Taille max d'un livrable : 15 Mo.

## 3. Vérifications

```bash
cd backend
python -m pytest -q tests/bet_core                       # 12+ tests, sans réseau (LLM simulé)
python -m engines.bet_core.run engines/bet_core/cases/la_courneuve.json /tmp/bet_fr     # dossier FR de référence
python -m engines.bet_core.run engines/bet_core/cases/moradia_pt_demo.json /tmp/bet_pt  # dossier PT de référence
```
Test réel (1 appel Claude Opus, ~1 à 3 €) : dans l'Assistant d'un compte pro de test, joindre le PC PDF + la G2 PDF et demander
« fais l'étude BET complète ». Attendu : 3 liens (PDF dossier, ZIP DXF, XLSX devis), statut « PRÊT POUR VISA BET » ou une liste de
questions précises si le relevé n'a pas passé les contrôles.

## 4. Fonctionnement

1. `reader.py` classe les pages (titres PCMI 02/03/05, PLAN/COUPE/FAÇADE, PLANTA/CORTE/ALÇADO, G2), envoie à Claude les
   planches + la couche texte vectorielle (cotes écrites avec leurs positions) + le texte de la G2, et reçoit un BuildingModel JSON.
2. `checks.py` contrôle le relevé (baies, niveaux, surfaces, escalier…). Anomalie bloquante → Claude corrige (2 fois max) → sinon
   l'Assistant pose des questions à l'utilisateur. Aucun dossier n'est produit sur un relevé faux.
3. `pipeline.py` : calculs Eurocodes, 22 planches (PDF à l'échelle + DXF), devis Excel à formules, note de calcul, vérificateur.
   Langue et normes selon `project.country` (FR → français / NF ; PT → português europeu / NP EN, RTIEBT, DR 23/95, EC8).

## 5. construpilot.pt (Assistente BTP)

O motor é o mesmo; `project.country = "PT"` dá o processo completo em português europeu (NP EN 1990–1998 + Anexos Nacionais,
A500NR, verificação sísmica pelo método das forças laterais EC8, RTIEBT/ITED, DR 23/95, IVA 23 %).

1. Copiar `backend/engines/bet_core/**` e `backend/tests/bet_core/**` (ramo `claude/bet-core-pt` do repositório construpilot.pt).
2. Registar no Assistente os 2 esquemas `assistant_tool.TOOLS` (só contas profissionais) e encaminhar as chamadas para
   `await assistant_tool.execute(name, args, user, conv, db, doc_loader=<carregador>)`.
   - `conv` precisa de `conversation_id` (e, se existir, `_quote_request_id` = id do pedido atual).
   - `doc_loader(db, ids, user_id) -> [(nome, bytes_pdf)]` : função que lê os PDF anexados no Assistente .pt, verificando que
     pertencem ao `user_id` (PermissionError caso contrário). Sem `doc_loader`, lê `db.assistant_docs` (formato .fr).
   - Juntar `assistant_tool.INSTRUCTIONS` às instruções do sistema (ou a sua tradução PT).
   - Os entregáveis são gravados em `db.assistant_artifacts` (`data_b64`, `mime`, `filename`, `download`
     = `/assistant/artifacts/{id}/content`) : adaptar o campo `download` se a rota de download .pt for outra.
   - `branding_loader(db, user_id) -> dict` (opcional) : identidade da empresa (company_name, logo_b64, accent_color,
     contact_line, address, postal_code, city, nif, alvara, footer_text). Por defeito usa `routes.plans_common._resolve_branding`
     se existir, senão os campos `brand_*` do utilizador. O processo sai com o logótipo e as cores da empresa.
3. Leitura dos planos : `engines/anthropic_native.py` se existir, senão SDK `anthropic` direto com `ANTHROPIC_API_KEY`
   (`pip install anthropic` se faltar ; modelo `ANTHROPIC_MODEL_OPUS`, por defeito claude-opus-5-5).
4. Testes : `python -m pytest -q tests/bet_core` (17) e `python -m engines.bet_core.run engines/bet_core/cases/moradia_pt_demo.json /tmp/bet_pt`.


## 6. Identité de l'entreprise (logo)

Le dossier (couverture, en-têtes, cartouche de chaque planche, Excel) est édité au nom de l'entreprise de l'utilisateur :
logo `brand_logo_b64`, nom, coordonnées, SIRET/TVA, couleur `brand_accent_color` (Ma page & mes documents). Sans logo, le nom est
composé en lettrage. Réservé aux offres **Pro** (identité du compte) et **Pro Business** (identité de l'organisation,
partagée par l'équipe) via `engines.access.compute_level` ; les autres comptes reçoivent le dossier aux couleurs ConstruPilot. Polices embarquées : Inter + Barlow Semi Condensed (SIL OFL, `fonts/`).

## 7. Contas demo (Web Summit) — documentos e empresa fictícios pré-configurados

`samples.py` gera um projeto de arquitetura fictício (5 folhas A3 : plantas R/C e 1.º andar, cortes, alçados) e um estudo
geotécnico fictício, coerentes com `cases/moradia_pt_demo.json`, mais a identidade de uma empresa fictícia
(« Construções Horizonte, Lda. », logótipo gerado, NIF/alvará fictícios).

```bash
python -m engines.bet_core.samples /tmp/demo_pt      # 2 PDF + logo_empresa_demo.png + branding_empresa_demo.json
```
Os PDF trazem `/Subject = construpilot-demo:moradia_pt_demo`. Se TODOS os documentos de um pedido trazem essa marca,
`reader.read_building` salta a IA e devolve o modelo exato do caso : estudo completo em segundos, 0 € de API, resultado
sempre « PRONTO PARA VERIFICAÇÃO » (15 desenhos, 61 160 € s/ IVA). Um documento real misturado → leitura normal por IA.

No reset diário das contas demo :
1. gravar os 2 PDF em `assistant_docs` (ou na biblioteca de documentos do .pt) das contas demo **Pro**, **Pro Business** e
   **Particular**, com nomes visíveis « Projeto_arquitetura_Moradia_T3_DEMO.pdf » e « Estudo_geotecnico_Moradia_T3_DEMO.pdf » ;
2. gravar `samples.demo_branding("PT")` como campos `brand_*` (logo em `brand_logo_b64`) das contas demo Pro / Pro Business ;
3. a conta Particular usa os mesmos documentos nas suas ferramentas (estimativa de orçamento, pedido de orçamentos) ; o estudo
   BET continua reservado às contas profissionais.
