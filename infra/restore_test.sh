#!/bin/sh
# Teste de recuperação: restaura o último backup num MongoDB temporário e compara o número de documentos
# por coleção com a base em produção. Não toca na base em uso. Correr uma vez por mês.
set -eu
cd "$(dirname "$0")"
. ./.env
LAST="$(ls -1t backups/mongo-*.archive.gz | head -1)"
echo "A testar $LAST"
sha256sum -c "$LAST.sha256"
docker rm -f cp-restore-test >/dev/null 2>&1 || true
docker run -d --name cp-restore-test -v "$(pwd)/backups":/backups mongo:8.0 >/dev/null
sleep 8
docker exec cp-restore-test mongorestore --quiet --archive="/backups/$(basename "$LAST")" --gzip
COUNT='db.getMongo().getDBNames().filter(d=>!["admin","local","config"].includes(d)).forEach(d=>{const x=db.getSiblingDB(d);x.getCollectionNames().sort().forEach(c=>print(d+"."+c+" "+x[c].estimatedDocumentCount()))})'
docker exec cp-restore-test mongosh --quiet --eval "$COUNT" > /tmp/cp-restore.txt
docker compose exec -T mongo mongosh --quiet -u "$MONGO_ROOT_USER" -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval "$COUNT" > /tmp/cp-live.txt
docker rm -f cp-restore-test >/dev/null
echo "Coleções restauradas: $(wc -l < /tmp/cp-restore.txt)"
diff /tmp/cp-live.txt /tmp/cp-restore.txt && echo "OK: backup idêntico à base (contagens)" || echo "Diferenças acima (normal se houve escritas depois do backup)"
