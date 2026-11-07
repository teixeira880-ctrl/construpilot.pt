// Material three.js de revestimento: cor + textura procedimental (azulejo, madeira, pedra, tijolo, reboco)
// e até 4 zonas em altura (ex.: azulejo até 1,20 m, pintura por cima). Coordenadas IFC (Z para cima).
import * as THREE from "three";

const VERT = `
varying vec3 vPos;
varying vec3 vNormalW;
void main() {
  vPos = position;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = `
uniform int uCount;
uniform float uFrom[4];
uniform float uTo[4];
uniform vec3 uColor[4];
uniform int uPattern[4];
uniform float uSize[4];
uniform float uZ0;
uniform vec2 uTangent;   // direção horizontal ao longo da face (paredes); (0,0) = laje (usa XY)
uniform vec3 uTint;
uniform float uTintMix;
varying vec3 vPos;
varying vec3 vNormalW;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
vec3 shade(int pat, vec3 c, vec2 uv, float s) {
  if (pat == 1) { // reboco
    return c * (0.94 + 0.08 * noise(uv * 35.0));
  } else if (pat == 2) { // azulejo
    vec2 f = fract(uv / s);
    float j = 0.035;
    if (f.x < j || f.y < j) return mix(c, vec3(0.78, 0.77, 0.74), 0.75);
    return c * (0.97 + 0.04 * hash(floor(uv / s)));
  } else if (pat == 3) { // madeira (tábuas horizontais)
    float row = floor(uv.y / s);
    float off = hash(vec2(row, 3.0)) * 3.0;
    float grain = sin((uv.x + off) * 18.0 + noise(vec2(uv.x * 2.0, uv.y * 40.0)) * 4.0) * 0.5 + 0.5;
    vec3 col = c * (0.85 + 0.2 * hash(vec2(row, 7.0))) * (0.9 + 0.12 * grain);
    if (fract(uv.y / s) < 0.03) col *= 0.7;
    return col;
  } else if (pat == 4) { // pedra
    vec2 g = uv / s;
    g.x += mod(floor(g.y), 2.0) * 0.5;
    vec2 f = fract(g);
    if (f.x < 0.03 || f.y < 0.05) return c * 0.62;
    return c * (0.8 + 0.3 * hash(floor(g))) * (0.92 + 0.12 * noise(uv * 18.0));
  } else if (pat == 5) { // tijolo (aparelho corrido)
    vec2 g = vec2(uv.x / s, uv.y / (s * 0.3));
    g.x += mod(floor(g.y), 2.0) * 0.5;
    vec2 f = fract(g);
    if (f.x < 0.04 || f.y < 0.1) return vec3(0.78, 0.76, 0.72);
    return c * (0.85 + 0.25 * hash(floor(g)));
  }
  return c;
}
void main() {
  float h = vPos.z - uZ0;
  vec2 uv = (uTangent.x == 0.0 && uTangent.y == 0.0) ? vPos.xy : vec2(dot(vPos.xy, uTangent), vPos.z);
  vec3 base = vec3(0.85);
  bool hit = false;
  for (int k = 0; k < 4; k++) {
    if (k >= uCount) break;
    if (h >= uFrom[k] - 1e-4 && h <= uTo[k] + 1e-4) { base = shade(uPattern[k], uColor[k], uv, uSize[k]); hit = true; }
  }
  if (!hit) base = vec3(0.82, 0.80, 0.76);
  vec3 L = normalize(vec3(0.45, 0.8, 0.35));
  float light = 0.58 + 0.42 * max(dot(normalize(vNormalW), L), 0.0);
  vec3 col = mix(base * light, uTint, uTintMix);
  gl_FragColor = vec4(col, 1.0);
}`;

export function makeFinishMaterial(zones, faces) {
  const z = zones.slice(0, 4);
  const pad = (arr, v) => [...arr, ...Array(4 - arr.length).fill(v)];
  const axis = faces?.axis;
  return new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    side: THREE.DoubleSide,
    uniforms: {
      uCount: { value: z.length },
      uFrom: { value: pad(z.map((x) => x.from), 0) },
      uTo: { value: pad(z.map((x) => x.to), 0) },
      uColor: { value: pad(z.map((x) => new THREE.Color(...x.color)), new THREE.Color(1, 1, 1)) },
      uPattern: { value: pad(z.map((x) => x.pattern), 0) },
      uSize: { value: pad(z.map((x) => x.size), 0.3) },
      uZ0: { value: faces?.kind === "wall" ? faces.z0 : 0 },
      uTangent: { value: faces?.kind === "wall" && axis ? new THREE.Vector2(-axis[1], axis[0]) : new THREE.Vector2(0, 0) },
      uTint: { value: new THREE.Color(0, 0, 0) },
      uTintMix: { value: 0 },
    },
  });
}

/** Aplica destaque/seleção tanto a materiais normais como de revestimento. */
export function tintMaterial(mat, color, amount, base) {
  if (mat.isShaderMaterial) {
    mat.uniforms.uTint.value.copy(color || new THREE.Color(0, 0, 0));
    mat.uniforms.uTintMix.value = color ? amount : 0;
    return;
  }
  mat.color.copy(color || base);
}
