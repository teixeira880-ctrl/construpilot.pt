import { useI18n } from "@/context/I18nContext";

const COPY = {
  fr: {
    credits: "Créditos de correio pré-pagos:", buyPack: "Acheter", packHint: "Após os envios gratuitos: 20 € sem IVA por carta (24 € com IVA) ou packs de créditos.",
    paidPhase: "Fase paga · 20 € sem IVA por envio ou packs de créditos", paidNotice: "Envio postal real pelo Merci Facteur: o pagamento Stripe inicia automaticamente a impressão e a expedição da carta.",
    creditAmount: "1 crédito de correio · 0,00 €", paidAmount: "24,00 € TTC (20,00 € HT + TVA 20 %)", creditConsent: "Confirmo a morada e autorizo este envio. Será consumido 1 crédito de correio da minha empresa.",
    paidConsent: "Confirmo a morada e autorizo este envio pago: 20,00 € + IVA 20 % = 24,00 €, pagos por cartão via Stripe. A carta parte assim que o pagamento for confirmado.",
    sendCredit: "Enviar (1 crédito)", sendPaid: "Pagar 24,00 € e enviar", creditCharge: "Sem pagamento: será consumido 1 crédito pré-pago.", paidCharge: "Será redirecionado para o pagamento seguro Stripe.",
    redirecting: "A redirecionar para o pagamento…", trackingTitle: "Acompanhamento das cartas", trackingRefresh: "Atualizar acompanhamento", trackingEmpty: "Ainda não foi enviada nenhuma carta.", returnedAlert: "Carta devolvida / não entregável — verifique a morada.",
    stAccepted: "Aceite", stPrinted: "Impressa", stPosted: "Enviada", stDelivered: "Entregue", stReturned: "Devolvida",
    completeSender: "Completar os dados do remetente",
    trialOffer: "Fase de testes · 20 envios gratuitos por empresa",
    liveNotice: "Envio postal real pelo Merci Facteur: a sua confirmação inicia a impressão e a expedição de uma carta física. O ConstruPilot assume os custos dos envios oferecidos.",
    demo: "Demonstração · 20 envios gratuitos por empresa", available: "Envios gratuitos restantes para a sua empresa:", used: "Os 20 envios gratuitos da sua empresa já foram todos utilizados.", pending: "Todos os envios gratuitos estão utilizados ou por verificar. Não é permitido outro envio.", future: "Depois: 20 € sem IVA por envio (24 € com IVA) pagos por cartão, ou packs de créditos pré-pagos.", checking: "A verificar a oferta da sua empresa…", offerError: "Não foi possível verificar a oferta. Não é permitido enviar.", retry: "Tentar novamente", amount: "A pagar pela sua empresa", free: "0,00 € · offert", costCovered: "Impressão e portes pagos pelo ConstruPilot durante a demonstração.", consent: "Confirmo a morada e autorizo este envio gratuito. Será utilizado um dos envios oferecidos à minha empresa.", unavailable: "Indisponible", calculating: "A verificar…", validRequired: "É necessário validar a carta e a oferta antes do envio.", refresh: "Atualizar a validação", send: "Enviar gratuitamente", diagnosis: "Diagnostic postal administrateur", noCharge: "Não é necessário cartão bancário. Não será efetuada qualquer cobrança.",
  },
  pt: {
    credits: "Créditos de correio pré-pagos:", buyPack: "Comprar", packHint: "Após os envios gratuitos: 20 € sem IVA por carta (24 € com IVA) ou packs de créditos.",
    paidPhase: "Fase paga · 20 € sem IVA por envio ou packs de créditos", paidNotice: "Envio postal real pelo Merci Facteur: o pagamento Stripe inicia automaticamente a impressão e a expedição da carta.",
    creditAmount: "1 crédito de correio · 0,00 €", paidAmount: "24,00 € com IVA (20,00 € + IVA 20 %)", creditConsent: "Confirmo a morada e autorizo este envio. Será consumido 1 crédito de correio da minha empresa.",
    paidConsent: "Confirmo a morada e autorizo este envio pago: 20,00 € + IVA 20 % = 24,00 €, pagos por cartão via Stripe. A carta parte assim que o pagamento for confirmado.",
    sendCredit: "Enviar (1 crédito)", sendPaid: "Pagar 24,00 € e enviar", creditCharge: "Sem pagamento: será consumido 1 crédito pré-pago.", paidCharge: "Será redirecionado para o pagamento seguro Stripe.",
    redirecting: "A redirecionar para o pagamento…", trackingTitle: "Acompanhamento das cartas", trackingRefresh: "Atualizar acompanhamento", trackingEmpty: "Ainda não foi enviada nenhuma carta.", returnedAlert: "Carta devolvida / não entregável — verifique a morada.",
    stAccepted: "Aceite", stPrinted: "Impressa", stPosted: "Enviada", stDelivered: "Entregue", stReturned: "Devolvida",
    completeSender: "Completar os dados do remetente",
    trialOffer: "Fase de testes · 20 envios gratuitos por empresa",
    liveNotice: "Envio postal real pelo Merci Facteur: a sua confirmação inicia a impressão e a expedição de uma carta física. O ConstruPilot assume os custos dos envios oferecidos.",
    demo: "Demonstração · 20 envios gratuitos por empresa", available: "Envios gratuitos restantes para a sua empresa:", used: "Os 20 envios gratuitos da sua empresa já foram todos utilizados.", pending: "Todos os envios gratuitos estão utilizados ou por verificar. Não é permitido outro envio.", future: "Depois: 20 € sem IVA por envio (24 € com IVA) pagos por cartão, ou packs de créditos pré-pagos.", checking: "A verificar a oferta da sua empresa…", offerError: "Não foi possível verificar a oferta. Não é permitido enviar.", retry: "Tentar novamente", amount: "A pagar pela sua empresa", free: "0,00 € · gratuito", costCovered: "Impressão e portes pagos pelo ConstruPilot durante a demonstração.", consent: "Confirmo a morada e autorizo este envio gratuito. Será utilizado um dos envios oferecidos à minha empresa.", unavailable: "Indisponível", calculating: "A verificar…", validRequired: "É necessário validar a carta e a oferta antes do envio.", refresh: "Atualizar a validação", send: "Enviar gratuitamente", diagnosis: "Diagnóstico postal do administrador", noCharge: "Não é necessário cartão bancário. Não será efetuada qualquer cobrança.",
  },
  en: {
    credits: "Prepaid letter credits:", buyPack: "Buy", packHint: "After the free letters: €20 excl. VAT per letter (€24 incl. VAT) or credit packs.",
    paidPhase: "Paid phase · €20 excl. VAT per letter or credit packs", paidNotice: "Real postal delivery via Merci Facteur: the Stripe payment automatically triggers printing and dispatch of the letter.",
    creditAmount: "1 letter credit · €0.00", paidAmount: "€24.00 incl. VAT (€20.00 + 20% VAT)", creditConsent: "I confirm the address and authorize this letter. It will consume 1 letter credit of my company.",
    paidConsent: "I confirm the address and authorize this paid letter: €20.00 + 20% VAT = €24.00, paid by card via Stripe. The letter is dispatched once payment is confirmed.",
    sendCredit: "Send (1 credit)", sendPaid: "Pay €24.00 and send", creditCharge: "No payment: 1 prepaid credit will be consumed.", paidCharge: "You will be redirected to Stripe secure checkout.",
    redirecting: "Redirecting to payment…", trackingTitle: "Letter tracking", trackingRefresh: "Refresh tracking", trackingEmpty: "No letter sent yet.", returnedAlert: "Letter returned / undeliverable — check the address.",
    stAccepted: "Accepted", stPrinted: "Printed", stPosted: "Posted", stDelivered: "Delivered", stReturned: "Returned",
    completeSender: "Complete sender details",
    trialOffer: "Testing phase · 20 free letters per company",
    liveNotice: "Real postal delivery via Merci Facteur: your confirmation starts the printing and dispatch of a physical letter. ConstruPilot covers the cost of the complimentary sends.",
    demo: "Demo · 20 free letters per company", available: "Free letters remaining for your company:", used: "All 20 of your company's free letters have been used.", pending: "All free letters are used or pending verification. Another send is not allowed.", future: "Afterwards: €20 excl. VAT per letter (€24 incl. VAT) paid by card, or prepaid credit packs.", checking: "Checking your company's offer…", offerError: "Unable to verify the offer. Sending is blocked.", retry: "Retry", amount: "Your company pays", free: "€0.00 · free", costCovered: "Printing and postage are covered by ConstruPilot during the demo.", consent: "I confirm the address and authorize this free letter. This uses one of my company's complimentary sends.", unavailable: "Unavailable", calculating: "Checking…", validRequired: "The letter and offer must be validated before sending.", refresh: "Refresh validation", send: "Send for free", diagnosis: "Admin postal diagnostics", noCharge: "No card required. No payment will be charged.",
  },
};
export const usePostalCopy = () => {
  const { lang } = useI18n();
  return (key) => COPY[lang]?.[key] || COPY.fr[key] || key;
};