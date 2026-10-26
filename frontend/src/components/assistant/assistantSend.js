import { createContext, useContext } from "react";

// Permet aux cartes de questions (ChoiceCard) d'envoyer un message utilisateur structuré
// dans le fil de l'Assistant, sans prop-drilling à travers MessageBubble/ActionCard.
export const AssistantSendContext = createContext(null);

export function useAssistantSend() {
  return useContext(AssistantSendContext);
}
