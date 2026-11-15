"""ConstruPilot Discovery Engine (/connect) — subsistema comercial exclusivo do construpilot.pt.

Módulos puros (sem acesso à base de dados):
  * catalog     — catálogo estruturado e auditável (capacidades, dores, demos), validado no arranque
  * recommend   — regras determinísticas respostas → necessidades → capacidades → demonstração
  * scoring     — prioridade comercial 0–100 transparente e configurável
  * demo_compute — demonstrações que chamam os motores reais (engines/geometry.py, fórmulas de margem)
  * business_time — prazos em horas úteis (Europe/Lisbon)
  * emails      — modelos transacionais PT-PT / EN / FR
"""
