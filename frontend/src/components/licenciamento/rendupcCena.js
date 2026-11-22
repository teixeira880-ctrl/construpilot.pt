import * as THREE from "three";
import { GradientEquirectTexture } from "three-gpu-pathtracer";

/* Cena do rendu no PC (sem React, para poder ser testada à parte): câmaras e sol do Blender → three.js. */

export const W = 1600, H = 900;
export const AMOSTRAS = { forte: 384, medio: 128 };
export const PRAZO_VISTA_S = { forte: 240, medio: 300 };

// Blender (z para cima) → glTF / three.js (y para cima): (x, y, z) → (x, z, −y), igual ao exportador glTF do Blender
export const v3 = (p) => new THREE.Vector3(p[0], p[2], -p[1]);

export function avaliarGPU() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2");
    if (!gl) return { ok: false, nivel: "fraco", nome: "WebGL 2 indisponível", motivo: "O navegador não tem WebGL 2." };
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    const nome = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER) || "");
    const float = !!gl.getExtension("EXT_color_buffer_float");
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    const software = /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i.test(nome);
    const movel = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent || "");
    const forte = /RTX|GTX 1[06-9]|Radeon RX|Radeon Pro|Arc A|Apple M\d|Apple GPU/i.test(nome) && !movel;
    if (!float || software) return { ok: false, nivel: "fraco", nome, motivo: "Placa gráfica sem cálculo em vírgula flutuante (ou em modo software)." };
    if (movel) return { ok: false, nivel: "fraco", nome, motivo: "Telemóvel ou tablet: o cálculo faz-se no servidor." };
    return { ok: true, nivel: forte ? "forte" : "medio", nome };
  } catch {
    return { ok: false, nivel: "fraco", nome: "?", motivo: "Não foi possível avaliar a placa gráfica." };
  }
}

export function camaraThree(c) {
  const lente = c.lente_mm || 35;
  const hfov = 2 * Math.atan(18 / lente);                       // sensor de 36 mm, como no Blender
  const vfov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(hfov / 2) / (W / H)));
  const cam = new THREE.PerspectiveCamera(vfov, W / H, 0.1, 2000);
  cam.position.copy(v3(c.pos));
  cam.lookAt(v3(c.alvo));
  cam.updateMatrixWorld();
  return cam;
}

export function cena(gltf, sol) {
  const s = new THREE.Scene();
  s.add(gltf.scene);
  gltf.scene.traverse((o) => {                      // o glTF não traz a transmissão do vidro do Blender
    const m = o.isMesh && o.material;
    if (m && /vidro/i.test(m.name || "")) {
      m.color?.set(0xffffff);
      m.transmission = 0.92; m.ior = 1.5; m.roughness = 0.02; m.metalness = 0; m.thickness = 0;
    }
  });
  const ceu = new GradientEquirectTexture(256);
  ceu.topColor.set(0x8fb8e6);
  ceu.bottomColor.set(0xc9d6e2);
  ceu.exponent = 2;
  ceu.update();
  s.background = ceu;
  s.environment = ceu;
  s.environmentIntensity = 0.75;
  const d = v3(sol?.dir_local || [0.3, -0.5, 0.8]).normalize();
  const luz = new THREE.DirectionalLight(new THREE.Color(1.0, 0.95, 0.88), 3.2);
  luz.position.copy(d.multiplyScalar(200));
  luz.target.position.set(0, 0, 0);
  s.add(luz, luz.target);
  s.updateMatrixWorld(true);
  return s;
}
