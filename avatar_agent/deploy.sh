#!/usr/bin/env bash
# Põe o agente « construpilot-avatar » em linha no LiveKit Cloud a partir de um servidor que já tem as chaves no ambiente (nunca mostradas).
# Uso: bash avatar_agent/deploy.sh   (a partir da raiz do repositório)
set -euo pipefail
cd "$(dirname "$0")"
for v in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET SYNTHESIA_API_KEY OPENAI_API_KEY AVATAR_AGENT_KEY; do
  [ -n "${!v:-}" ] || { echo "FALTA $v"; exit 2; }
done
command -v lk >/dev/null || curl -sSL https://get.livekit.io/cli | bash >/dev/null
umask 077
{ for v in SYNTHESIA_API_KEY OPENAI_API_KEY AVATAR_AGENT_KEY; do printf '%s=%s\n' "$v" "${!v}"; done
  printf 'CONSTRUPILOT_PT_URL=%s\nCONSTRUPILOT_FR_URL=%s\nAVATAR_VOICE=%s\n' "${CONSTRUPILOT_PT_URL:-https://construpilot.pt}" "${CONSTRUPILOT_FR_URL:-https://construpilot.fr}" "${AVATAR_VOICE:-marin}"
  [ -n "${AVATAR_IDS:-}" ] && printf 'AVATAR_IDS=%s\n' "$AVATAR_IDS"; } > .env.agent
if [ -f livekit.toml ]; then
  lk agent update-secrets --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" >/dev/null
  lk agent deploy --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
else
  lk agent create --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" --silent . 2>&1 | grep -viE "secret|key" | tail -8
fi
rm -f .env.agent
lk agent list --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
