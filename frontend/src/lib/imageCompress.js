/**
 * Compression photo côté client via Canvas.
 * - Cible ~150 Ko max, largeur max 1600px
 * - Conserve HEIC/HEIF/PNG à jpeg pour compatibilité
 * - Retourne un File JPEG.
 */
const TARGET_BYTES = 150 * 1024;
const MAX_WIDTH = 1600;

const loadImage = (file) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });

const canvasToBlob = (canvas, quality) =>
  new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", quality));

export async function compressImage(file) {
  if (!file || !file.type.startsWith("image/")) return file;
  // Fichiers déjà petits : on garde tel quel
  if (file.size <= TARGET_BYTES && file.type === "image/jpeg") return file;

  let img;
  try {
    img = await loadImage(file);
  } catch {
    return file; // fallback : on ne casse pas l'upload
  }

  const ratio = Math.min(1, MAX_WIDTH / img.width);
  const w = Math.round(img.width * ratio);
  const h = Math.round(img.height * ratio);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, w, h);
  URL.revokeObjectURL(img.src);

  // Boucle qualité jusqu'à atteindre la cible
  let quality = 0.85;
  let blob = await canvasToBlob(canvas, quality);
  while (blob && blob.size > TARGET_BYTES && quality > 0.35) {
    quality -= 0.1;
    blob = await canvasToBlob(canvas, quality);
  }
  if (!blob) return file;
  const name = (file.name || "photo").replace(/\.[^.]+$/, "") + ".jpg";
  return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
}
