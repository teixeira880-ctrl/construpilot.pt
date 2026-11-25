#!/bin/sh
# Constrói o frontend de um site e coloca-o em infra/www/<site> (servido pelo Caddy).
#   ./build_frontend.sh pt        (usa PT_DOMAIN de infra/.env)
#   ./build_frontend.sh fr        (usa FR_DOMAIN e FR_REPO_DIR)
# Corre dentro de um contentor Node (nada a instalar na VM). O plugin de edição visual da Emergent
# (@emergentbase/visual-edits, devDependency opcional) é retirado numa cópia temporária: o build não precisa dele.
set -eu
cd "$(dirname "$0")"
SITE="${1:?uso: ./build_frontend.sh pt|fr}"
. ./.env
case "$SITE" in
  pt) SRC="$(cd .. && pwd)/frontend"; DOMAIN="$PT_DOMAIN" ;;
  fr) SRC="$(cd "${FR_REPO_DIR}" && pwd)/frontend"; DOMAIN="$FR_DOMAIN" ;;
  *) echo "site desconhecido: $SITE"; exit 1 ;;
esac
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar -C "$SRC" --exclude=node_modules --exclude=build -cf - . | tar -C "$TMP" -xf -
sed -i '/@emergentbase\/visual-edits/d' "$TMP/package.json"
docker run --rm -v "$TMP":/src -w /src -e REACT_APP_BACKEND_URL="https://$DOMAIN" \
  -e NODE_OPTIONS=--max-old-space-size=3072 node:22-bookworm \
  sh -c "yarn install --network-timeout 600000 && yarn build"
rm -rf "www/$SITE.new" && mkdir -p www && cp -r "$TMP/build" "www/$SITE.new"
rm -rf "www/$SITE.old"; [ -d "www/$SITE" ] && mv "www/$SITE" "www/$SITE.old"
mv "www/$SITE.new" "www/$SITE"
echo "Frontend $SITE pronto em infra/www/$SITE (anterior guardado em www/$SITE.old)"
