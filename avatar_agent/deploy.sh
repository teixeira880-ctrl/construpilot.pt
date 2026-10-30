#!/usr/bin/env bash
# Déploie l'agent « construpilot-avatar » sur LiveKit Cloud depuis un serveur qui a déjà les clés en variables
# d'environnement (jamais affichées). Usage : bash avatar_agent/deploy.sh   (depuis la racine du dépôt)
set -euo pipefail
cd "$(dirname "$0")"
for v in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET SYNTHESIA_API_KEY OPENAI_API_KEY AVATAR_AGENT_KEY; do
  [ -n "${!v:-}" ] || { echo "MANQUE $v"; exit 2; }
done
command -v lk >/dev/null || curl -sSL https://get.livekit.io/cli | bash >/dev/null
umask 077
{ for v in SYNTHESIA_API_KEY OPENAI_API_KEY AVATAR_AGENT_KEY; do printf '%s=%s\n' "$v" "${!v}"; done
  printf 'CONSTRUPILOT_PT_URL=%s\nCONSTRUPILOT_FR_URL=%s\nAVATAR_VOICE=%s\n' "${CONSTRUPILOT_PT_URL:-https://construpilot.pt}" "${CONSTRUPILOT_FR_URL:-https://construpilot.fr}" "${AVATAR_VOICE:-coral}"
  if [ -n "${AVATAR_IDS:-}" ]; then printf "AVATAR_IDS=%s\n" "$AVATAR_IDS"; fi; } > .env.agent
if [ -f livekit.toml ]; then
  lk agent update-secrets --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" >/dev/null
  lk agent deploy --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
else
  lk agent create --region eu-central --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" --silent . 2>&1 | grep -viE "secret|key" | tail -8
fi
rm -f .env.agent
lk agent list --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
