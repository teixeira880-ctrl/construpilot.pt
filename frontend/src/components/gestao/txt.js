// Textos da Gestão de obra — Portugal (pt-PT, 3.ª pessoa formal).
// O componente GestaoObra.jsx é idêntico no .pt e no .fr; só este ficheiro muda.
export const LOCALE = "pt-PT";
export const T = {
  // separadores
  diario: "Diário de obra", qse: "Qualidade e segurança", rfi: "Pedidos de esclarecimento", indicadores: "Curva S e alertas",
  stock: "Stock da obra", copiloto: "Copiloto", historico: "Histórico", webhooks: "Webhooks (ERP)",
  // comuns
  carregar: "A carregar…", guardar: "Guardar", editar: "Editar", cancelar: "Cancelar", criar: "Criar", fechar: "Fechar", abrir: "Abrir",
  enviar: "Enviar", pdf: "PDF", foto: "Fotografia", fotos: "Fotografias", nenhum: "Nada registado.", erro: "Ocorreu um erro",
  estado: "Estado", data: "Data", lote: "Lote", local: "Local", descricao: "Descrição", titulo: "Título", empresa: "Empresa",
  todos: "Todos", obrigatorio: "Campo obrigatório", ditar: "Ditar",
  // diário
  diario_sub: "Uma entrada por dia: meteorologia real, efetivo do ponto, trabalhos, ocorrências, fotografias e assinatura. Depois de assinada, a entrada fica imutável (só aditamentos).",
  novo_dia: "Novo dia", preparar: "Preparar o dia", meteo: "Meteorologia", meteo_auto: "Meteorologia obtida automaticamente (Open-Meteo)",
  meteo_falta: "Meteorologia não obtida (cidade da obra em falta ou serviço indisponível).", efetivo: "Efetivo",
  efetivo_auto: "{n} trabalhador(es) · {h} h registadas no ponto", pendentes_ponto: "{n} picagem(ns) por validar",
  equipas: "Equipas / subempreiteiros em obra", equipa: "Equipa", n_pessoas: "N.º", trabalhos: "Trabalhos realizados",
  ocorrencias: "Ocorrências", entregas: "Entregas de materiais", visitas: "Visitas e reuniões", observacoes: "Observações",
  oper_registos: "Registos dos operários neste dia", anexar_fotos_oper: "Anexar as fotografias dos operários",
  rascunho: "Rascunho", assinado: "Assinado", publicado: "Visível no portal", privado: "Interno",
  publicar: "Mostrar no portal", despublicar: "Retirar do portal", assinar: "Assinar", assinar_titulo: "Assinar a entrada do diário",
  assinar_aviso: "Depois de assinada, a entrada já não pode ser alterada: só pode acrescentar aditamentos.",
  nome_assinante: "Nome de quem assina", desenhe: "Desenhe a assinatura", limpar: "Limpar",
  aditamento: "Aditamento", aditamento_ph: "Correção ou complemento (fica datado e assinado com o seu nome)",
  visto: "Visto da fiscalização", dar_visto: "Dar visto", visto_obs: "Observação (opcional)",
  entrega_sug: "Entregas registadas neste dia", diario_vazio: "Ainda não há entradas no diário.",
  // QSE
  qse_sub: "Inspeções por lista de verificação, não conformidades com plano de ação 5W2H, acidentes, quase-acidentes, diálogos de segurança e EPI.",
  novo_registo: "Novo registo", tipo: "Tipo", gravidade: "Gravidade", modelo: "Lista de verificação", tipo_obra: "Tipo de obra",
  checklist: "Pontos a verificar", ok: "OK", nok: "Não OK", na: "N/A", conformidade: "Conformidade", gerar_nc: "Gerar NC dos pontos «não OK»",
  acoes: "Plano de ação (5W2H)", nova_acao: "Nova ação", o_que: "O quê", porque: "Porquê", quem: "Quem", onde: "Onde", quando: "Quando",
  como: "Como", quanto: "Quanto custa (€)", responsavel: "Empresa responsável", participantes: "Participantes (um por linha)",
  tema: "Tema", dias_baixa: "Dias de baixa", fechar_reg: "Fechar o registo", justificacao: "Justificação do fecho (obrigatória se houver ações por verificar)",
  reabrir: "Reabrir", analisar_ia: "Analisar a fotografia (IA)", analise_ia: "Análise por IA (indicativa)",
  perigos: "Perigos", ncs: "Não conformidades", medidas: "Medidas", alertas_operarios: "Alertas enviados pelos operários",
  qualificar: "Qualificar", registo_pdf: "Registo QSE (PDF)", atraso: "em atraso", lembrete: "Lembrete",
  // RFI
  rfi_sub: "Perguntas técnicas com destinatário, prazo e resposta registada. Uma empresa só vê os seus pedidos e os partilhados com todos.",
  novo_rfi: "Novo pedido", assunto: "Assunto", pergunta: "Pergunta", destinatario: "Destinatário", prazo: "Prazo de resposta",
  visibilidade: "Visibilidade", vis_todos: "Todos os intervenientes", vis_restrito: "Só eu e o destinatário",
  impacto_custo: "Pode ter impacto no custo", impacto_prazo: "Pode ter impacto no prazo", responder: "Responder", resposta: "Resposta",
  anexo: "Anexo", rfi_vazio: "Nenhum pedido de esclarecimento.", perfil_dest: { dono_obra: "Dono de obra", fiscalizacao: "Fiscalização", arquiteto: "Arquiteto", gestor: "Direção de obra" },
  // indicadores
  curva_sub: "Avanço previsto (planeamento) × avanço real (registado dia a dia) × custos reais. Nada é estimado: o que falta é indicado.",
  previsto: "Previsto", real: "Real", custo_real: "Custo real (% do orçamento de custo)", desvio: "Desvio", spi: "Índice de prazo (SPI)",
  cpi: "Índice de custo (CPI)", ref_congelada: "Planeamento de referência congelado", alertas: "Alertas", sem_alertas: "Nenhum alerta. 👍",
  // stock
  stock_sub: "Receções das encomendas (com guia de remessa), saídas para a obra, ajustes de inventário e stock mínimo.",
  material: "Material", unidade: "Unidade", quantidade: "Quantidade", saldo: "Saldo", minimo: "Mínimo", entrada: "Entrada", saida: "Saída",
  ajuste: "Ajuste", movimento: "Novo movimento", rececionar: "Rececionar", encomendas: "Encomendas a rececionar", pedida: "Pedida",
  recebida: "Recebida", em_falta: "Em falta", guia: "Guia de remessa", conforme: "Conforme", nota: "Nota", movimentos: "Últimos movimentos",
  abaixo_min: "abaixo do mínimo",
  // copiloto
  copiloto_sub: "Pergunte sobre a obra em linguagem corrente. O copiloto responde só com os dados registados (diário, QSE, pedidos, planeamento, custos, stock).",
  pergunta_ph: "Ex.: O que está atrasado esta semana e porquê?", perguntar: "Perguntar", resumo_semana: "Gerar o resumo semanal",
  relatorio_pdf: "Relatório semanal (PDF)", fonte_calculo: "Resposta calculada (IA indisponível)",
  sugestoes: ["O que está atrasado e qual o impacto no prazo?", "Que não conformidades estão por fechar?", "Que pedidos aguardam resposta?", "Que materiais estão abaixo do mínimo?"],
  // histórico e webhooks
  historico_sub: "Quem fez o quê e quando nesta obra (diário, QSE, pedidos, stock).",
  webhooks_sub: "Avise o seu ERP ou a contabilidade quando algo acontece nas obras. Cada envio é assinado (HMAC SHA-256) com o segredo mostrado uma única vez.",
  url: "Endereço https", eventos: "Eventos", testar: "Testar", segredo: "Segredo (copie agora: não volta a ser mostrado)",
  apagar: "Apagar",
};
export const SEV_CLS = { critica: "bg-red-100 text-red-800", alta: "bg-orange-100 text-orange-800", media: "bg-amber-100 text-amber-800", info: "bg-slate-100 text-slate-600" };
