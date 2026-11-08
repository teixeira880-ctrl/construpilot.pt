# ConstruPilot — Posto «Edifício 3D» (Blender + ArcGIS Pro)

## Requisitos técnicos
- Windows 10/11 64 bits, 16 GB RAM (32 GB recomendado), GPU com 4 GB+ (opcional; o Cycles também corre em CPU).
- **Blender 4.2 LTS ou superior** (gratuito, blender.org).
- **ArcGIS Pro 3.x** com licença ativa e extensão **3D Analyst** (Import 3D Files) — opcional:
  sem ArcGIS Pro o posto produz o modelo Blender, os renders e o GLB; a implantação georreferenciada
  no ArcGIS Pro (multipatch, cena local, .slpk) só é feita quando o ArcGIS Pro está configurado.
- Sessão ArcGIS Online iniciada no ArcGIS Pro (para o mapa base Imagery e a altitude World Elevation).
- Ligação à internet (HTTPS de saída para o ConstruPilot; não é preciso abrir portas).

## Instalação
1. Descompacte esta pasta, por exemplo em `C:\ConstruPilot\edificio3d`.
2. Edite `iniciar_worker.bat`: token (igual ao `EDIFICIO3D_WORKER_TOKEN` do servidor) e caminhos.
3. Execute `iniciar_worker.bat`. O posto aparece como «ligado» na página *Edifício 3D* do ConstruPilot.

Sem ArcGIS Pro, aponte `ARCGIS_PROPY` para vazio e execute `python worker_local.py`.

## O que é produzido
- Blender: `edificio.glb` (georreferenciável, rodado para o azimute real), `edificio.blend`,
  renders Cycles: fachada frente/tardoz/laterais, perspetiva, vista aérea do telhado, antes/depois.
- ArcGIS Pro: `construpilot.gdb` (ponto e polígono de implantação, multipatch do edifício),
  vistas da cena com ortofotomapa e terreno (aérea antes/depois, 4 vistas em contexto), `edificio.slpk`, `.aprx`.

## Blender no próprio servidor (sem posto local)
O backend usa o Blender diretamente se `import bpy` funcionar (ou se `BLENDER_BIN` apontar para o executável).
- Python 3.11 → `pip install bpy==4.5.*` (ou a versão 4.x mais recente disponível para 3.11); Python 3.13 → `pip install bpy==5.2.*`.
- Bibliotecas de sistema por vezes necessárias: `libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1`.
- Teste: `python -c "import bpy; print(bpy.app.version_string)"`.
- Demonstração completa no servidor: `python scripts/edificio3d_demo.py` (Blender + renders + acabamento fotorrealista).
