export const PostalDestination = ({ destination, edited, onChange, complete }) => <div className="space-y-2" data-testid="postal-destination">
  <div role="radiogroup" aria-label="Adresse destinataire" className="flex flex-wrap gap-3 text-xs">
    {[["contact", "Adresse du contact"], ["terrain", "Adresse du terrain"]].map(([value, label]) => <label key={value} className="flex items-center gap-2">
      <input type="radio" name="postal-destination" value={value} checked={destination === value} onChange={() => onChange(value)} data-testid={`postal-destination-${value}`} />{label}
    </label>)}
  </div>
  <p className="text-xs font-semibold" data-testid="postal-address-source">{edited ? "Adresse modifiée manuellement" : destination === "terrain" ? "Envoi à l’adresse du terrain" : "Envoi à l’adresse du contact"}</p>
  {!complete && <p role="status" className="text-xs text-amber-700" data-testid="postal-missing-address">Adresse postale incomplète. Renseignez la voie, le code postal et la ville avant de poster.</p>}
</div>;