# dwg2json — leitura de DWG com LibreDWG (open source)

Converte um DWG em JSON (espaço modelo + blocos usados) com
[@mlightcad/libredwg-web](https://github.com/mlightcad/libredwg-web), o LibreDWG compilado em WebAssembly.
`engines/dwg_libredwg.py` chama este programa num processo separado e reconstrói um DXF com o ezdxf.

**Licença:** LibreDWG e @mlightcad/libredwg-web são GPL-3.0. Correm aqui como programa independente no servidor
(subprocesso), sem ligação ao código do ConstruPilot, e não são enviados ao navegador. Código-fonte:
https://github.com/LibreDWG/libredwg e https://github.com/mlightcad/libredwg-web.

## Instalação no servidor

```bash
# Node ≥ 20
cd backend/tools/dwg2json && npm ci --omit=dev
```

Sem esta instalação, `dwg_convert` passa aos conversores seguintes (Autodesk APS, CloudConvert) ou pede um DXF.
Variáveis opcionais: `NODE_BINARY`, `LIBREDWG_TOOL_DIR`, `LIBREDWG_DISABLED=true`.

Teste manual: `node dwg2json.mjs planta.dwg planta.json`
