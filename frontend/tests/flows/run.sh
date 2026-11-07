#!/usr/bin/env bash
# Percursos completos (perfil, orçamento guiado, registo diário, visita, ferramentas) em jsdom, modo demo offline.
# Requisitos: node_modules do frontend + jsdom, @testing-library/react, fake-indexeddb, esbuild.
set -euo pipefail
cd "$(dirname "$0")"
SRC="$(cd ../../src && pwd)"
npx esbuild flow.test.jsx --bundle --platform=node --format=esm --outfile=bundle.mjs --loader:.js=jsx --jsx=automatic \
  --alias:@="$SRC" --define:process.env.REACT_APP_BACKEND_URL='""' --log-level=error --external:jsdom --external:fake-indexeddb \
  --banner:js="import {createRequire} from 'module';const require=createRequire(import.meta.url);"
node runner.mjs
