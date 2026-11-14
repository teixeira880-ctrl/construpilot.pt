// Telefone obrigatório no registo (14/11, Martinho): validação de formato, sem SMS.
// Aceita «+351 912 345 678», «00351912345678», «912345678» (PT), «06 12 34 56 78» (FR); o servidor normaliza para +indicativo.
export function validPhone(value) {
  const s = String(value || "").replace(/[\s.\-()/]/g, "");
  if (/^(\+|00)\d{8,15}$/.test(s)) return true;
  return /^\d{9,10}$/.test(s);
}
