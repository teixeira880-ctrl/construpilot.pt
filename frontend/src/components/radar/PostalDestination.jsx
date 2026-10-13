export const PostalDestination = ({ destination, edited, onChange, complete }) => <div className="space-y-2" data-testid="postal-destination">
  <div role="radiogroup" aria-label="Morada do destinatário" className="flex flex-wrap gap-3 text-xs">
    {[["contact", "Morada do contacto"], ["terrain", "Morada do terreno"]].map(([value, label]) => <label key={value} className="flex items-center gap-2">
      <input type="radio" name="postal-destination" value={value} checked={destination === value} onChange={() => onChange(value)} data-testid={`postal-destination-${value}`} />{label}
    </label>)}
  </div>
  <p className="text-xs font-semibold" data-testid="postal-address-source">{edited ? "Morada editada manualmente" : destination === "terrain" ? "Envio para a morada do terreno" : "Envio para a morada do contacto"}</p>
  {!complete && <p role="status" className="text-xs text-amber-700" data-testid="postal-missing-address">Morada postal incompleta. Indique a rua, o código postal e a localidade antes do envio.</p>}
</div>;