# ConstruPilot CLT industrial

O piloto está em `/clt-industrial`. O servidor recusa acesso por defeito.

## Ativação em ambiente de teste PT

1. Instalar as dependências do backend e compilar o frontend.
2. Definir `CLT_PILOT_USER_ID` com o ID interno da conta escolhida e
   `CLT_PILOT_TENANT_ID` com `org_<organization_id>` ou `usr_<user_id>`.
   Contas futuras podem ser ativadas explicitamente em
   `CLT_PILOT_ACCOUNTS` (JSON com pares ID de utilizador e tenant).
   A autorização ainda exige conta profissional e as escritas exigem a permissão de orçamentos.
3. Para DWG, configurar a atividade AutoCAD existente com o procedimento em
   `backend/scripts/setup_autodesk_dwg.py` e validar `APS_ACTIVITY_QUALIFIED` e `APS_DWG_ENABLED=true`.
   A conversão CLT reutiliza a fila e cache APS por conta. Nenhum outro conversor é chamado.
4. Para os perfis exatos de acabamentos IFC, ativar o BIM Studio no ambiente de teste
   e importar de novo o IFC com a conta piloto. As versões já processadas mantêm as
   suas medições. As faces curvas, não coplanares ou incompletas precisam de revisão.
5. Usar a conta piloto e outra conta da mesma organização para validar o isolamento.
   Verificar o painel, o Assistant BTP e o avatar administrador existente antes de propor produção.

## Primeiro ensaio

Carregar as quatro folhas do cliente e clicar numa cota para localizar a origem.
Confirmar a revisão, as unidades de área que não descodificaram e as ligações entre
planta, corte, vão e tipo de painel. Um pé-direito de acabamento não é uma altura
estrutural. Uma espessura de pormenor não identifica automaticamente um painel.

Importar DXF/DWG com painéis e recortes em camadas distintas. O motor atual aceita
polilinhas lineares fechadas no plano XY do modelo com unidades declaradas e uma
espessura confirmada por importação. Desenhos fora desse contrato requerem revisão.
Comparar volume líquido com referência aprovada por peça e por material antes de
preparar dados de fabrico. A API de painel devolve o resultado do confronto com 2%,
mas não autoriza produção.

Preparar as tarifas de compra, produção e venda. Criar um lote com referências
documentais, quantidades aprovadas para uso no orçamento e valores reais quando
disponíveis. O custo à conclusão exige previsão explícita para todas as linhas.
O Assistente BTP analisa PDFs da própria conta, consulta lotes e calcula rascunhos.
O avatar administrador pode encaminhar o pedido pelo Assistente BTP da sessão
autenticada. O piloto não atribui funções de administrador.

## Home A: troços e alturas

O levantamento do Home A junta os contornos CLT a magenta com o tracejado CLT
que não tem contorno. A espessura de cada tracejado é aprendida nos troços com
contorno da mesma folha. Uma faixa só conta como parede quando a largura
desenhada coincide com essa espessura a 3 mm. As restantes ficam pendentes.

A altura estrutural das paredes é o pé-direito acabado cotado na planta, mais a
espessura do pavimento e do teto falso medidas no corte. A escala do corte vem
das espessuras impressas da laje (240 mm) e da cobertura (140 mm). As quebras
do corte não permitem medir a altura total do painel diretamente.

## Bibliotecas de preços, cálculo e plano

O separador "Custos, preços e plano" tem três partes, partilhadas por toda a
organização:

1. **Cálculo**: os pisos chegam já preenchidos a partir da revisão do desenho
   (comprimentos por espessura, altura estrutural, placa e pintura). Indica-se a
   data de início e se o plano começa na compra da matéria-prima ou no fabrico.
   O resultado traz custo, venda, margem, prazo, plano (Gantt), detalhe por preço
   e a lista de hipóteses. Um botão cria o lote de seguimento com esse plano.
2. **Bibliotecas**: matéria-prima, energia e água, colaboradores, transporte,
   gruas e máquinas, montagem em obra, revestimentos e venda do CLT. Cada preço
   tem custo, venda opcional, base de cálculo (m³ de CLT, m³ de madeira, kg de
   cola, m² de montagem, horas, kWh, km, viagem, dia de fabrico ou montagem,
   m² de placa ou pintura, projeto) e quantidade por base. A empresa pode
   acrescentar, alterar ou retirar preços.
3. **Parâmetros técnicos**: rendimento da madeira, cola por junta, horas e
   eletricidade por m³, capacidade da fábrica, distâncias, camiões, equipa e
   prazos.

Importação: colar diretamente do Excel, ou carregar `.xlsx`, `.csv` ou `.pdf`
com tabela (`POST /clt-industrial/library/import` mostra a pré-visualização,
`POST /clt-industrial/library/table` grava). Os cabeçalhos aceites estão no
modelo CSV que se descarrega na página (categoria, código, designação,
unidade, custo, venda, base, consumo por base, fonte). Preços como `1.234,50 €`
são aceites.

Eletricidade: `POST /clt-industrial/library/electricity/refresh` lê o preço
médio não doméstico de Portugal no Eurostat (`nrg_pc_205`, sem IVA) e grava-o
como valor de mercado com o período. A água não tem fonte automática (tarifas
municipais) e fica como hipótese até a empresa a preencher.

Cada valor indica a origem:

- **empresa**: introduzido pela empresa;
- **mercado**: média publicada, com a fonte (Holzkurier, Eurostat, EPD Södra,
  Kiilto, CNR, gerador de preços CYPE, Zaask);
- **hipótese**: sem fonte pública; tem de ser substituído antes de orçamentar.

A ficha Rezult (ETA-21/0914) confirma o adesivo tipo I EN 15425 e lamelas de
20 a 43 mm, mas não publica a dosagem de cola nem a composição de cada parede.
Por omissão, 100 mm conta como 3 camadas e 160 mm (80+80) como duas placas de 3
camadas (4 juntas coladas); o valor pode ser alterado por piso. A ETA indica a
fábrica em Kyiv: a distância de transporte por omissão é hipótese.

## Limites desta entrega

- O PDF fornece evidência de dimensões e materiais. A reconstrução automática
  de todas as peças a partir deste tipo de folha continua por validar.
- As tarifas e lotes são guardados na aplicação; os fluxos ERP, fábrica, faturas
  de fornecedores e a aprovação de fabrico não estão integrados nesta fase.
- A conversão APS real precisa de um DWG e de uma atividade válida em teste.
- Os desenhos do cliente não fazem parte do código nem do pacote de integração.
