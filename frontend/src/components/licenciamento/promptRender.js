// Texto do pedido do render fotorrealista, escrito a partir do modelo (função pura, testada).

/** Texto do pedido a partir do modelo (função pura). */
export function promptDoModelo(derivado) {
  const md = derivado?.medicoes || {};
  const ac = md.acabamentos || [];
  const de = (prefixo) => ac.find((a) => (a.elemento || "").toLowerCase().startsWith(prefixo))?.material;
  const fachada = de("fachada") || de("façade");
  const cobertura = de("cobertura") || de("toiture");
  const caixilharia = de("caixilharia") || de("menuiserie");
  const pisos = (derivado?.pisos || []).length;
  const ext = (md.exteriores || []).map((e) => e.nome).slice(0, 6);
  const partes = [
    "Photorealistic architectural visualization of this exact building.",
    "Keep exactly the same geometry, volumes, window and door openings, roof shape, camera angle and framing as the reference image.",
    pisos ? `${pisos}-storey house.` : "",
    fachada ? `Facade finish: ${fachada}.` : "",
    cobertura ? `Roof: ${cobertura}.` : "",
    caixilharia ? `Window frames: ${caixilharia}, large clear glazing with realistic reflections.` : "",
    ext.length ? `Outdoor elements to keep in place: ${ext.join(", ")}.` : "",
    "Natural late-afternoon sunlight, soft realistic shadows, clear sky, lush realistic landscaping,",
    "high-end architectural photography, sharp details, no text, no watermark, no people.",
  ];
  return partes.filter(Boolean).join(" ").slice(0, 990);
}

