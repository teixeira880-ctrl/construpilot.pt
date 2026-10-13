import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/** Aperçu 3D interactif d'un escalier (volée droite approximée depuis le résultat). */
export default function Stair3D({ result, stairWidthMm = 1000 }) {
  const mountRef = useRef(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !result) return;
    const W = mount.clientWidth || 640;
    const H = 360;
    const n = Math.max(2, result.num_steps || 16);
    const g = (result.tread_depth_mm || 280) / 1000;
    const r = (result.riser_height_mm || 175) / 1000;
    const w = (stairWidthMm || 1000) / 1000;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f6f8);
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(3, 5, 4);
    scene.add(dir);

    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color: 0xff5a00, roughness: 0.6, metalness: 0.05 });
    const landMat = new THREE.MeshStandardMaterial({ color: 0xffb27a, roughness: 0.75 });
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x333333 });

    const treads = Array.isArray(result.treads) && result.treads.length ? result.treads : null;
    const stype = (result.stair_type || "straight").toLowerCase();
    const flights = Array.isArray(result.steps_per_flight) && result.steps_per_flight.length
      ? result.steps_per_flight.slice() : [n];
    const hasWinders = treads ? treads.some((t) => Math.abs(t.angle_deg || 0) > 0.01) : false;
    const totalTurn = (stype.includes("half") || stype.includes("demi")) ? 180
      : (stype.includes("quarter") || stype.includes("quart")) ? 90 : 0;
    const landingTurnDeg = (!hasWinders && flights.length > 1) ? totalTurn / (flights.length - 1) : 0;
    const turnSign = result.direction === "right" ? -1 : 1;

    const bb = { minx: 1e9, maxx: -1e9, minz: 1e9, maxz: -1e9, maxy: 0 };
    const addBox = (cx, cy, cz, depth, rot, material) => {
      const geo = new THREE.BoxGeometry(w, r, depth);
      const mesh = new THREE.Mesh(geo, material);
      mesh.position.set(cx, cy, cz); mesh.rotation.y = rot;
      group.add(mesh);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat);
      edges.position.set(cx, cy, cz); edges.rotation.y = rot;
      group.add(edges);
      bb.minx = Math.min(bb.minx, cx); bb.maxx = Math.max(bb.maxx, cx);
      bb.minz = Math.min(bb.minz, cz); bb.maxz = Math.max(bb.maxz, cz);
      bb.maxy = Math.max(bb.maxy, cy + r);
    };

    // Parcours de la ligne de foulée : on avance de la profondeur de chaque marche,
    // on tourne le cap des balancés (angle_deg) et on insère les paliers entre volées.
    let theta = 0, x = 0, z = 0, yLast = 0, idx = 0;
    for (let f = 0; f < flights.length; f++) {
      const count = flights[f] || 0;
      for (let k = 0; k < count; k++) {
        const t = treads ? treads[idx] : null;
        const depth = t ? (t.depth_walkline_mm || 280) / 1000 : g;
        const ang = t ? (t.angle_deg || 0) : 0;
        const yTop = t ? (t.cumulative_height_mm || r * 1000 * (idx + 1)) / 1000 : r * (idx + 1);
        const fx = Math.sin(theta), fz = -Math.cos(theta);
        addBox(x + fx * depth / 2, yTop - r / 2, z + fz * depth / 2, depth, theta, mat);
        x += fx * depth; z += fz * depth; yLast = yTop; idx++;
        if (Math.abs(ang) > 0.01) theta += turnSign * ang * Math.PI / 180;
      }
      if (f < flights.length - 1 && !hasWinders) {
        const fx = Math.sin(theta), fz = -Math.cos(theta);
        addBox(x + fx * w / 2, yLast - r / 2, z + fz * w / 2, w, theta, landMat); // palier
        x += fx * w; z += fz * w;
        if (landingTurnDeg) theta += turnSign * landingTurnDeg * Math.PI / 180;
        // décalage latéral pour que la volée suivante longe la précédente (demi-tour)
        const perpx = Math.cos(theta), perpz = Math.sin(theta);
        x += perpx * w * turnSign; z += perpz * w * turnSign;
      }
    }

    const cx = (bb.minx + bb.maxx) / 2, cz = (bb.minz + bb.maxz) / 2;
    group.position.set(-cx, 0, -cz);
    const span = Math.max(1, bb.maxx - bb.minx, bb.maxz - bb.minz, yLast);

    // sol
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(span * 3, span * 3),
      new THREE.MeshStandardMaterial({ color: 0xe2e5ea, roughness: 1 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0;
    scene.add(floor);
    scene.add(group);

    camera.position.set(span * 1.2, yLast * 1.3 + span * 0.5, span * 1.3);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, yLast / 2, 0);
    controls.enableDamping = true;
    controls.update();

    let raf;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();

    const onResize = () => {
      const nw = mount.clientWidth || 640;
      camera.aspect = nw / H; camera.updateProjectionMatrix(); renderer.setSize(nw, H);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      controls.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode) renderer.domElement.parentNode.removeChild(renderer.domElement);
    };
  }, [result, stairWidthMm]);

  return (
    <div className="rounded-lg border border-border overflow-hidden" data-testid="stair-3d">
      <div ref={mountRef} className="w-full" style={{ height: 360 }} />
      <p className="text-[11px] text-muted-foreground px-3 py-2 border-t border-border">
        Pré-visualização 3D indicativa — arraste para rodar, roda do rato para fazer zoom.
      </p>
    </div>
  );
}
