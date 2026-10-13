const text = (value) => String(value ?? "").trim();
export const completePostalAddress = (address) => ["adresse1", "cp", "ville"].every((key) => text(address?.[key]));
export const defaultPostalDestination = (opp) => completePostalAddress(opp?.promoteur) ? "contact" : "terrain";

export const postalRecipient = (opp, destination = defaultPostalDestination(opp)) => {
  const promoteur = opp?.promoteur;
  const terrain = destination === "terrain";
  // Switch the entire address, never combine a contact street with the site's town.
  return {
    nom: text(promoteur?.nom) || "À l’attention du maître d’ouvrage",
    societe: text(promoteur?.societe),
    adresse1: text(terrain ? opp?.adresse : promoteur?.adresse1),
    adresse2: text(terrain ? opp?.adresse_complement : promoteur?.adresse2),
    cp: text(terrain ? opp?.cp : promoteur?.cp),
    ville: text(terrain ? opp?.commune : promoteur?.ville),
  };
};