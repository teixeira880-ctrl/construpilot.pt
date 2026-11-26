// Textos da Execução de obra — Portugal (pt-PT, 3.ª pessoa formal).
// O componente ExecucaoObra.jsx é idêntico no .pt e no .fr; só este ficheiro muda.
export const LOCALE = "pt-PT";
export const T = {
  // separadores
  assessor: "Assessor de voz", mapa: "Mapa da obra", tesouraria: "Tesouraria", camaras: "Câmaras",
  // comuns
  carregar: "A carregar…", guardar: "Guardar", cancelar: "Cancelar", apagar: "Apagar", editar: "Editar", adicionar: "Adicionar",
  erro: "Ocorreu um erro", nenhum: "Nada registado.", data: "Data", nome: "Nome", pdf: "PDF", fechar: "Fechar",
  // assessor
  assessor_sub: "Dite (ou escreva) o que aconteceu em obra. O assessor prepara o diário, o stock, a qualidade e segurança, os pedidos de esclarecimento e o avanço por zona. Nada é gravado sem a sua confirmação.",
  ditar: "Ditar", relato_ph: "Ex.: «Hoje estiveram 4 pessoas da equipa do Rui. Chegaram 40 sacos de cimento. O reboco da cozinha está a 60 %. O fiscal esteve cá às 15h. Temos uma dúvida para o arquiteto sobre a cota da soleira.»",
  interpretar: "Interpretar", usar_ia: "Usar IA (mais preciso)", fonte_ia: "Interpretado por IA e verificado com os dados da obra",
  fonte_local: "Interpretação local (sem IA): funciona mesmo sem internet", rever: "Reveja e corrija antes de gravar",
  confirmar: "Confirmar e gravar", gravar_n: "Gravar {n} registo(s)", nada_proposto: "Nada a propor neste relato.",
  diario_existe: "Já existe uma entrada do diário neste dia: o texto será acrescentado.", diario_assinado: "A entrada deste dia está assinada: o texto será acrescentado como aditamento.",
  t_diario: "Diário de obra", t_stock: "Stock", t_qse: "Qualidade e segurança", t_rfi: "Pedido de esclarecimento", t_avanco: "Avanço",
  entrada: "Entrada", saida: "Saída", material: "Material", unidade: "Unidade", quantidade: "Quantidade", material_novo: "material novo",
  material_conhecido: "material já em stock", trabalhos: "Trabalhos", ocorrencias: "Ocorrências", entregas: "Entregas", visitas: "Visitas",
  observacoes: "Observações", efetivos: "Efetivos", estado: "Estado", equipa: "Equipa", titulo: "Título", descricao: "Descrição", gravidade: "Gravidade", local: "Local",
  assunto: "Assunto", pergunta: "Pergunta", destinatario: "Destinatário", zona: "Zona", atividade: "Atividade", frase: "Frase ditada",
  qse_tipos: { incidente: "Incidente / acidente", quase_acidente: "Quase-acidente", epi: "Equipamento de proteção (EPI)", nao_conformidade: "Não conformidade", ambiente: "Ambiente" },
  gravidades: { baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica" },
  perfis: { "": "—", arquiteto: "Arquiteto", fiscalizacao: "Fiscalização", dono_obra: "Dono de obra" },
  resultado_ok: "Gravado", resultado_erro: "Não gravado", gravado_tudo: "Registos gravados na obra", novo_relato: "Novo relato",
  assessor_dica: "Dica: crie primeiro as zonas no «Mapa da obra» para que o avanço por divisão seja reconhecido.",
  // mapa
  mapa_sub: "Avanço por zona ou divisão, desenhado sobre a planta real. Clique numa zona para atualizar as atividades.",
  global: "Avanço global", concluidas: "zonas concluídas", por_iniciar: "por iniciar", piso: "Piso", pisos: "Pisos", zonas: "Zonas",
  atividades: "Atividades", peso: "Peso", area: "Área (m²)", media: "Média", estrutura: "Estrutura do mapa", editar_estrutura: "Editar estrutura",
  carregar_planta: "Carregar planta", sem_planta: "Carregue a planta do piso (imagem) para desenhar as zonas por cima.",
  desenhar: "Desenhar na planta", desenhar_ajuda: "Escolha a zona e arraste sobre a planta para desenhar o seu retângulo.",
  modelo: "Modelo de atividades", aplicar_modelo: "Aplicar modelo", mapa_vazio: "O mapa ainda não tem zonas. Crie os pisos, as zonas (divisões) e as atividades a acompanhar.",
  novo_piso: "Piso", nova_zona: "Zona", nova_atividade: "Atividade", sem_ret: "sem retângulo", matriz: "Matriz zonas × atividades",
  base_area: "Média ponderada pela área das zonas", base_zonas: "Zonas com o mesmo peso (indique as áreas para ponderar)",
  guardar_avanco: "Guardar avanço", nota: "Nota", ultimos: "Últimos registos", legenda: "0 % · em curso · avançado · concluído",
  // tesouraria
  tes_sub: "Fluxo de caixa da obra: o que já entrou e saiu e o que está previsto, mês a mês. Antecipe quando a obra precisa de financiamento.",
  recebido: "Recebido", pago: "Pago", saldo_atual: "Saldo atual", por_receber: "Por receber", por_pagar: "Por pagar",
  vencido: "Vencido por receber", saldo_final: "Saldo final previsto", pior_saldo: "Pior saldo previsto",
  entradas: "Entradas", saidas: "Saídas", entradas_prev: "Entradas previstas", saidas_prev: "Saídas previstas", saldo: "Saldo acumulado",
  movimentos: "Movimentos manuais", movimento: "Movimento", valor: "Valor (€)", categoria: "Categoria", contraparte: "Entidade",
  realizado: "Realizado", previsto: "Previsto", tipo: "Tipo", eventos: "Movimentos considerados", origem: "Origem",
  origens: { fatura: "Fatura", encomenda: "Encomenda", horas: "Mão de obra", manual: "Manual" }, cfg: "Parâmetros",
  prazo_fornecedor: "Prazo de pagamento a fornecedores (dias)", saldo_inicial: "Saldo inicial da obra (€)", taxa_falta: "Sem taxa horária na obra: defina-a no separador Orçamento para incluir a mão de obra.",
  sem_dados: "Ainda não há faturas, encomendas nem movimentos nesta obra.", em_atraso: "em atraso",
  // câmaras
  cam_sub: "Imagens em direto do estaleiro. Use o endereço https da imagem (JPEG atualizado pela câmara), do vídeo ou da incorporação do serviço da câmara.",
  cam_tipos: { imagem: "Imagem (atualização automática)", video: "Vídeo (MP4 / HLS)", embed: "Incorporação (YouTube, Vimeo, IPCamLive, Angelcam…)" },
  url: "Endereço https", atualizar: "Atualizar a cada (s)", partilhar: "Partilhar com o dono de obra e a fiscalização",
  cam_vazio: "Nenhuma câmara configurada.", cam_hosts: "Serviços aceites para incorporação:", cam_erro: "Imagem indisponível",
};
