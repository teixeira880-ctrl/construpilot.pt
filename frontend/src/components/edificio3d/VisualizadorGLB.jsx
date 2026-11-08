import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

/**
 * Visualizador do GLB exportado pelo Blender (geometria real, sem reconstrução).
 * O GLB vem rodado para o azimute real: glTF Y-up → +X = Este, -Z = Norte.
 */
const VisualizadorGLB = forwardRef(function VisualizadorGLB({ dados, azimute = 180, altura = 480 }, ref) {
  const host = useRef(null);
  const st = useRef({});
  const [erro, setErro] = useState(null);

  useEffect(() => {
    if (!dados || !host.current) return undefined;
    const el = host.current;
    const w = el.clientWidth || 800;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(w, altura);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xdfe9f2);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    const camera = new THREE.PerspectiveCamera(40, w / altura, 0.1, 2000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;
    controls.target.set(0, 3.5, 0);

    const sol = new THREE.DirectionalLight(0xfff3e0, 2.6);
    sol.position.set(-18, 26, 16);
    sol.castShadow = true;
    sol.shadow.mapSize.set(2048, 2048);
    Object.assign(sol.shadow.camera, { left: -25, right: 25, top: 25, bottom: -25 });
    scene.add(sol, new THREE.HemisphereLight(0xdfefff, 0x6b7d4f, 0.6));
    const chao = new THREE.Mesh(new THREE.CircleGeometry(60, 64), new THREE.MeshStandardMaterial({ color: 0x7f9a5c, roughness: 1 }));
    chao.rotation.x = -Math.PI / 2;
    chao.receiveShadow = true;
    scene.add(chao);
    // seta do Norte
    const norte = new THREE.Mesh(new THREE.ConeGeometry(0.6, 1.8, 3), new THREE.MeshBasicMaterial({ color: 0xc0392b }));
    norte.rotation.x = -Math.PI / 2;
    norte.position.set(0, 0.05, -14);
    scene.add(norte);

    let raf;
    new GLTFLoader().parse(dados, "", gltf => {
      gltf.scene.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      st.current.raio = box.getSize(new THREE.Vector3()).length() / 2;
      st.current.vista("perspetiva");
    }, e => setErro(String(e?.message || e)));

    const a = THREE.MathUtils.degToRad(azimute);
    const frente = new THREE.Vector3(Math.sin(a), 0, -Math.cos(a));
    st.current.vista = (nome) => {
      const r = (st.current.raio || 9) * 2.6;
      const dir = frente.clone();
      const rot = { frente: 0, direita: -Math.PI / 2, tardoz: Math.PI, esquerda: Math.PI / 2, perspetiva: Math.PI / 4.5 }[nome];
      if (nome === "aerea") { camera.position.set(0.01, r * 1.5, 0.01); controls.target.set(0, 0, 0); controls.update(); return; }
      dir.applyAxisAngle(new THREE.Vector3(0, 1, 0), rot ?? 0);
      camera.position.set(dir.x * r, nome === "perspetiva" ? r * 0.45 : 2.2, dir.z * r);
      controls.target.set(0, 3.5, 0);
      controls.update();
    };
    st.current.captura = () => renderer.domElement.toDataURL("image/jpeg", 0.9);

    const anim = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(anim); };
    anim();
    const ro = new ResizeObserver(() => {
      const nw = el.clientWidth || w;
      renderer.setSize(nw, altura); camera.aspect = nw / altura; camera.updateProjectionMatrix();
    });
    ro.observe(el);
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); pmrem.dispose();
      scene.traverse(o => { o.geometry?.dispose?.(); (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m?.dispose?.()); });
      renderer.dispose(); el.removeChild(renderer.domElement);
    };
  }, [dados, azimute, altura]);

  useImperativeHandle(ref, () => ({ vista: n => st.current.vista?.(n), captura: () => st.current.captura?.() }), []);

  return (
    <div className="relative w-full" style={{ height: altura }} data-testid="ed3d-glb">
      <div ref={host} className="w-full h-full" />
      {erro && <div className="absolute inset-0 grid place-items-center text-sm text-destructive bg-background/80">GLB: {erro}</div>}
    </div>
  );
});

export default VisualizadorGLB;
