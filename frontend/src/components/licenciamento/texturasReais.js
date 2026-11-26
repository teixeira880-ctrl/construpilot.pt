import * as THREE from "three";

// Texturas fotográficas CC0 (Poly Haven, domínio público) servidas pelo próprio site em /texturas/.
// O ficheiro /texturas/manifest.json é escrito pelo script backend/scripts/baixar_texturas_cc0.py:
//   { "<padrao>": { "id": "...", "m": 2.0, "dif": "dif.jpg", "nor": "nor.jpg", "rug": "rug.jpg", "natural": true, ... } }
// Sem manifest (ou sem rede), o 3D usa as texturas desenhadas no próprio Estúdio — nada falha.

let promessa = null;

function carregar(loader, url) {
  return new Promise((resolve) => {
    loader.load(url, (t) => resolve(t), undefined, () => resolve(null));
  });
}

function preparar(t, m, cor = false) {
  if (!t) return null;
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(1 / m, 1 / m);                 // as geometrias do Estúdio têm UV em metros
  t.anisotropy = 8;
  if (cor) t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** Promessa única: { padrao: { map, normalMap, roughnessMap, natural, m } } (vazio se não houver texturas). */
export function texturasReais(base = "/texturas") {
  if (promessa) return promessa;
  promessa = (async () => {
    try {
      const r = await fetch(`${base}/manifest.json`, { cache: "force-cache" });
      if (!r.ok) return {};
      const manifest = await r.json();
      const loader = new THREE.TextureLoader();
      const out = {};
      await Promise.all(Object.entries(manifest || {}).map(async ([padrao, e]) => {
        if (!e || !e.dif) return;
        const pasta = `${base}/${padrao}`;
        const m = Number(e.m) > 0 ? Number(e.m) : 2;
        const [dif, nor, rug] = await Promise.all([
          carregar(loader, `${pasta}/${e.dif}`), e.nor ? carregar(loader, `${pasta}/${e.nor}`) : null, e.rug ? carregar(loader, `${pasta}/${e.rug}`) : null,
        ]);
        if (!dif) return;
        out[padrao] = { map: preparar(dif, m, true), normalMap: preparar(nor, m), roughnessMap: preparar(rug, m), natural: e.natural !== false, m };
      }));
      return out;
    } catch {
      return {};
    }
  })();
  return promessa;
}

/** Cor final do material: materiais naturais (madeira, pedra, telha, relva) mostram a cor da fotografia; os pintados
 *  (rebocos, cerâmicos coloridos) levam a cor escolhida, misturada com a fotografia. */
export function corComTextura(cor, real) {
  if (!real) return cor;
  if (real.natural) return "#ffffff";
  const c = new THREE.Color(cor);
  return `#${c.lerp(new THREE.Color("#ffffff"), 0.35).getHexString()}`;
}
