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
trap 'rm -f .env.agent' EXIT   # Lot 107
{ for v in SYNTHESIA_API_KEY OPENAI_API_KEY AVATAR_AGENT_KEY; do printf '%s=%s\n' "$v" "${!v}"; done
  printf 'CONSTRUPILOT_PT_URL=%s\nCONSTRUPILOT_FR_URL=%s\nAVATAR_VOICE=%s\n' "${CONSTRUPILOT_PT_URL:-https://construpilot.pt}" "${CONSTRUPILOT_FR_URL:-https://construpilot.fr}" "${AVATAR_VOICE:-marin}"
  printf 'AVATAR_REALTIME_MODEL=%s\nAVATAR_REASONING=%s\n' "${AVATAR_REALTIME_MODEL:-gpt-realtime-2.1}" "${AVATAR_REASONING:-low}"
  if [ -n "${AVATAR_IDS:-}" ]; then printf "AVATAR_IDS=%s\n" "$AVATAR_IDS"; fi
  for v in AZURE_SPEECH_KEY AZURE_SPEECH_REGION AVATAR_VOICE_PROVIDER AZURE_TTS_VOICE_FR AZURE_TTS_VOICE_PT AZURE_TTS_VOICE_EN AZURE_TTS_RATE AZURE_TTS_FALLBACK_VOICE AVATAR_FILLER_GAP AVATAR_VAD_THRESHOLD AVATAR_VAD_SILENCE_MS AVATAR_NOISE AVATAR_BVC AVATAR_MIN_INTERRUPT; do  # Azure Speech TTS (remplace ElevenLabs)
    if [ -n "${!v:-}" ]; then printf '%s=%s\n' "$v" "${!v}"; fi; done; } > .env.agent
if [ -f livekit.toml ]; then
  lk agent update-secrets --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" >/dev/null
  lk agent deploy --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
else
  lk agent create --region eu-central --secrets-file .env.agent --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" --silent . 2>&1 | grep -viE "secret|key" | tail -8
fi
rm -f .env.agent
lk agent list --url "$LIVEKIT_URL" --api-key "$LIVEKIT_API_KEY" --api-secret "$LIVEKIT_API_SECRET" 2>&1 | grep -viE "secret|key" | tail -5
