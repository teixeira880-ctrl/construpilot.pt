import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RotateCcw, Maximize2, Home, Move3d, Download, Paperclip } from "lucide-react";

/**
 * Composant 3D interactif — extrusion des rooms mesurés + segments de murs détectés.
 * Contrôles souris : clic-gauche = orbite, molette = zoom.
 * Nécessite : `rooms` (polygones), `walls` (segments), `scale_m_per_px`.
 */
export function Interactive3D({ rooms = [], walls = [], structure = null,
                                 dalleEpM = 0.2, voileEpM = 0.2,
                                 poutreLM = 0.2, poutreHM = 0.4,
                                 scaleMperPx = 0.01,
                                 wallHeightM = 2.5, imageHeight = 600, onAttach = null }) {
  const mountRef = useRef(null);
  const [wallHeight, setWallHeight] = useState(wallHeightM);
  const controlsRef = useRef(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const width = mount.clientWidth || 800;
    const height = imageHeight;

    // ===== Scene =====
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f5f0);

    // Grid
    const grid = new THREE.GridHelper(50, 50, 0xcccccc, 0xeeeeee);
    scene.add(grid);

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dir = new THREE.DirectionalLight(0xffffff, 0.8);
    dir.position.set(20, 30, 20); dir.castShadow = true;
    scene.add(dir);

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 200);
    camera.position.set(15, 15, 15);
    camera.lookAt(0, 0, 0);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true;
    mount.innerHTML = "";
    mount.appendChild(renderer.domElement);

    // ===== Bounding box computation (rooms + structure, fallback to points) =====
    const getPoly = (r) => r.polygon_px || r.points || [];
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    const acc = (x, y) => {
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
    };
    rooms.forEach((r) => getPoly(r).forEach(([x, y]) => acc(x, y)));
    walls.forEach((s) => { acc(s.x1, s.y1); acc(s.x2, s.y2); });
    if (structure) {
      ["walls", "beams", "columns", "footings"].forEach((k) =>
        (structure[k] || []).forEach((e) => { acc(e.x1, e.y1); acc(e.x2, e.y2); }));
      (structure.floors || []).forEach((f) => (f.points || []).forEach(([x, y]) => acc(x, y)));
    }
    if (!isFinite(minX)) { minX = 0; maxX = 100; minY = 0; maxY = 100; }
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    const scale = scaleMperPx;

    // Convert px→3D coords (Y = -Z in three, X = X)
    const toWorld = (px, py) => [(px - cx) * scale, -(py - cy) * scale];

    // ===== Room floors =====
    const roomColors = [0xffd7a8, 0xa8d8ff, 0xd8ffa8, 0xffa8d8, 0xd8a8ff, 0xffe8a8];
    rooms.forEach((r, i) => {
      const poly = getPoly(r);
      if (poly.length < 3) return;
      const shape = new THREE.Shape();
      poly.forEach(([px, py], k) => {
        const [wx, wz] = toWorld(px, py);
        if (k === 0) shape.moveTo(wx, wz);
        else shape.lineTo(wx, wz);
      });
      const geom = new THREE.ShapeGeometry(shape);
      const mat = new THREE.MeshLambertMaterial({
        color: roomColors[i % roomColors.length], side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.rotation.x = -Math.PI / 2; // put shape flat on ground
      mesh.position.y = 0.01;
      mesh.receiveShadow = true;
      scene.add(mesh);

      // Room label as sprite
      if (r.name) {
        const canvas = document.createElement("canvas");
        canvas.width = 256; canvas.height = 64;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#1a1a1a"; ctx.font = "bold 32px sans-serif";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(r.name, 128, 32);
        const tex = new THREE.CanvasTexture(canvas);
        const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
        spr.scale.set(2, 0.5, 1);
        const [wx, wz] = toWorld(...(r.centroid_px || [(poly[0][0] + poly[2][0]) / 2, (poly[0][1] + poly[2][1]) / 2]));
        spr.position.set(wx, 0.3, wz);
        scene.add(spr);
      }
    });

    // ===== Walls (extruded segments) =====
    const WALL_COLORS = { porteur: 0xdc2626, cloison: 0xff9500, doublage: 0x3b82f6 };
    walls.forEach((s) => {
      const [x1, z1] = toWorld(s.x1, s.y1);
      const [x2, z2] = toWorld(s.x2, s.y2);
      const length = Math.hypot(x2 - x1, z2 - z1);
      if (length < 0.1) return;
      const thick = Math.max(0.08, (s.thickness_px || 8) * scale);
      const geom = new THREE.BoxGeometry(length, wallHeight, thick);
      const mat = new THREE.MeshLambertMaterial({
        color: WALL_COLORS[s.wall_type] || 0xff9500,
      });
      const mesh = new THREE.Mesh(geom, mat);
      mesh.castShadow = true;
      mesh.position.set((x1 + x2) / 2, wallHeight / 2, (z1 + z2) / 2);
      mesh.rotation.y = -Math.atan2(z2 - z1, x2 - x1);
      scene.add(mesh);
    });

    // ===== Openings (portes / fenêtres / baies) =====
    // Distribute each room's openings along the perimeter edges. Doors go
    // from floor up; windows/bays have a 0.9 m sill. Colors : brown door,
    // sky-blue window, deep blue bay.
    const OPENING_COLORS = { porte: 0x8b4513, fenetre: 0x87ceeb, baie: 0x1e40af };
    rooms.forEach((r) => {
      const openings = r.openings || [];
      const poly = getPoly(r);
      if (!openings.length || poly.length < 3) return;
      // Compute edges + lengths
      const edges = [];
      for (let i = 0; i < poly.length; i++) {
        const [ax, ay] = poly[i];
        const [bx, by] = poly[(i + 1) % poly.length];
        const [wx1, wz1] = toWorld(ax, ay);
        const [wx2, wz2] = toWorld(bx, by);
        const len = Math.hypot(wx2 - wx1, wz2 - wz1);
        edges.push({ x1: wx1, z1: wz1, x2: wx2, z2: wz2, len });
      }
      // Flatten count for multi-openings
      const items = [];
      openings.forEach((op) => {
        for (let k = 0; k < (op.count || 1); k++) items.push(op);
      });
      items.forEach((op, idx) => {
        const edge = edges[idx % edges.length];
        if (edge.len < op.width_m + 0.2) return;    // skip too-short walls
        // t = fractional position along the edge (spread openings across)
        const inEdge = Math.floor(idx / edges.length);
        const inEdgeCount = Math.ceil(items.length / edges.length) || 1;
        const t = (inEdge + 1) / (inEdgeCount + 1);
        const mx = edge.x1 + (edge.x2 - edge.x1) * t;
        const mz = edge.z1 + (edge.z2 - edge.z1) * t;
        const angle = -Math.atan2(edge.z2 - edge.z1, edge.x2 - edge.x1);
        const w = op.width_m, h = op.height_m;
        const sill = op.kind === "porte" ? 0 : 0.9;
        const geom = new THREE.BoxGeometry(w, h, 0.14);
        const mat = new THREE.MeshLambertMaterial({
          color: OPENING_COLORS[op.kind] || 0x87ceeb,
          transparent: op.kind !== "porte", opacity: op.kind === "porte" ? 1 : 0.55,
        });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.position.set(mx, sill + h / 2, mz);
        mesh.rotation.y = angle;
        scene.add(mesh);
      });
    });

    // ===== Volumes structurels détectés (métré béton) =====
    // Voiles/murs (rouge), planchers (vert), poteaux (violet), poutres (gris foncé), semelles (jaune)
    if (structure) {
      const seg = (a, b) => {
        const [x1, z1] = toWorld(a[0], a[1]);
        const [x2, z2] = toWorld(b[0], b[1]);
        return { x1, z1, x2, z2, len: Math.hypot(x2 - x1, z2 - z1),
                 mx: (x1 + x2) / 2, mz: (z1 + z2) / 2,
                 angle: -Math.atan2(z2 - z1, x2 - x1) };
      };
      const box = (w, h, d, color, x, y, z, angle = 0, opacity = 1) => {
        const g = new THREE.BoxGeometry(Math.max(w, 0.02), Math.max(h, 0.02), Math.max(d, 0.02));
        const m = new THREE.MeshLambertMaterial({ color, transparent: opacity < 1, opacity });
        const mesh = new THREE.Mesh(g, m);
        mesh.castShadow = true; mesh.position.set(x, y, z); mesh.rotation.y = angle;
        scene.add(mesh);
      };
      // Voiles / murs porteurs
      (structure.walls || []).forEach((w) => {
        const s = seg([w.x1, w.y1], [w.x2, w.y2]);
        if (s.len < 0.1) return;
        const thick = w.type === "cloison" ? Math.max(0.06, voileEpM * 0.5) : voileEpM;
        const color = w.type === "cloison" ? 0xff9500 : 0xdc2626;
        box(s.len, wallHeight, thick, color, s.mx, wallHeight / 2, s.mz, s.angle);
      });
      // Planchers (dalles) — slab au sol
      const FLOOR_COL = 0x22c55e;
      (structure.floors || []).forEach((f) => {
        const poly = f.points || [];
        if (poly.length < 3) return;
        const shape = new THREE.Shape();
        poly.forEach(([px, py], k) => {
          const [wx, wz] = toWorld(px, py);
          if (k === 0) shape.moveTo(wx, wz); else shape.lineTo(wx, wz);
        });
        const geom = new THREE.ExtrudeGeometry(shape, { depth: dalleEpM, bevelEnabled: false });
        const mat = new THREE.MeshLambertMaterial({ color: FLOOR_COL, transparent: true, opacity: 0.55, side: THREE.DoubleSide });
        const mesh = new THREE.Mesh(geom, mat);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.y = 0.02;
        mesh.receiveShadow = true;
        scene.add(mesh);
      });
      // Poteaux (violet) — box du sol au plafond
      (structure.columns || []).forEach((c) => {
        const [wx1, wz1] = toWorld(Math.min(c.x1, c.x2), Math.min(c.y1, c.y2));
        const [wx2, wz2] = toWorld(Math.max(c.x1, c.x2), Math.max(c.y1, c.y2));
        const w = Math.max(0.15, Math.abs(wx2 - wx1));
        const d = Math.max(0.15, Math.abs(wz2 - wz1));
        box(w, wallHeight, d, 0x9333ea, (wx1 + wx2) / 2, wallHeight / 2, (wz1 + wz2) / 2);
      });
      // Poutres (gris foncé) — box en tête de mur (section b×h réglable)
      (structure.beams || []).forEach((b) => {
        const s = seg([b.x1, b.y1], [b.x2, b.y2]);
        if (s.len < 0.1) return;
        box(s.len, poutreHM, poutreLM, 0x475569, s.mx, wallHeight - poutreHM / 2, s.mz, s.angle);
      });
      // Semelles (jaune) — box au sol
      (structure.footings || []).forEach((ft) => {
        const [wx1, wz1] = toWorld(Math.min(ft.x1, ft.x2), Math.min(ft.y1, ft.y2));
        const [wx2, wz2] = toWorld(Math.max(ft.x1, ft.x2), Math.max(ft.y1, ft.y2));
        const w = Math.max(0.2, Math.abs(wx2 - wx1));
        const d = Math.max(0.2, Math.abs(wz2 - wz1));
        box(w, 0.35, d, 0xeab308, (wx1 + wx2) / 2, -0.15, (wz1 + wz2) / 2, 0, 0.85);
      });
    }

    // ===== Simple manual orbit controls (drag = orbit, wheel = zoom) =====
    let rotY = Math.PI / 4, rotX = Math.PI / 4, dist = 20;
    let dragging = false, lastX = 0, lastY = 0;
    const updateCamera = () => {
      camera.position.x = Math.sin(rotY) * Math.cos(rotX) * dist;
      camera.position.z = Math.cos(rotY) * Math.cos(rotX) * dist;
      camera.position.y = Math.sin(rotX) * dist;
      camera.lookAt(0, 1, 0);
    };
    updateCamera();
    const onDown = (e) => { dragging = true; lastX = e.clientX; lastY = e.clientY; };
    const onUp = () => { dragging = false; };
    const onMove = (e) => {
      if (!dragging) return;
      rotY -= (e.clientX - lastX) * 0.01;
      rotX = Math.max(0.1, Math.min(Math.PI / 2 - 0.1, rotX + (e.clientY - lastY) * 0.01));
      lastX = e.clientX; lastY = e.clientY;
      updateCamera();
    };
    const onWheel = (e) => {
      e.preventDefault();
      dist = Math.max(3, Math.min(80, dist + e.deltaY * 0.02));
      updateCamera();
    };
    renderer.domElement.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousemove", onMove);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

    controlsRef.current = {
      resetCam: () => { rotY = Math.PI / 4; rotX = Math.PI / 4; dist = 20; updateCamera(); },
      topView: () => { rotY = 0; rotX = Math.PI / 2 - 0.15; dist = 25; updateCamera(); },
      snapshot: () => {
        renderer.render(scene, camera);
        const url = renderer.domElement.toDataURL("image/png");
        const a = document.createElement("a");
        a.href = url; a.download = "maquette-3d-beton.png"; a.click();
      },
      dataUrl: () => { renderer.render(scene, camera); return renderer.domElement.toDataURL("image/png"); },
    };

    // Animation loop
    let raf;
    const animate = () => { raf = requestAnimationFrame(animate); renderer.render(scene, camera); };
    animate();

    // Resize
    const onResize = () => {
      const w = mount.clientWidth;
      camera.aspect = w / height;
      camera.updateProjectionMatrix();
      renderer.setSize(w, height);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousemove", onMove);
      renderer.dispose();
      mount.innerHTML = "";
    };
  }, [rooms, walls, structure, scaleMperPx, wallHeight, imageHeight, dalleEpM, voileEpM, poutreLM, poutreHM]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Label className="text-xs">Hauteur murs :</Label>
        <input type="range" min="2" max="4" step="0.1" value={wallHeight}
               onChange={(e) => setWallHeight(parseFloat(e.target.value))}
               data-testid="wall-height-slider"
               className="accent-primary" />
        <span className="num text-xs">{wallHeight.toFixed(1)} m</span>
        <Button size="sm" variant="outline"
                onClick={() => controlsRef.current?.resetCam()}
                data-testid="cam-reset-btn"
                className="rounded-sm gap-1 h-7 text-xs ml-auto">
          <RotateCcw className="h-3 w-3" /> Reset
        </Button>
        <Button size="sm" variant="outline"
                onClick={() => controlsRef.current?.topView()}
                data-testid="cam-top-btn"
                className="rounded-sm gap-1 h-7 text-xs">
          <Home className="h-3 w-3" /> Vue dessus
        </Button>
        <Button size="sm" variant="outline"
                onClick={() => controlsRef.current?.snapshot()}
                data-testid="cam-snapshot-btn"
                className="rounded-sm gap-1 h-7 text-xs">
          <Download className="h-3 w-3" /> PNG
        </Button>
        {onAttach && (
          <Button size="sm"
                  onClick={() => { const u = controlsRef.current?.dataUrl(); if (u) onAttach(u); }}
                  data-testid="cam-attach-btn"
                  className="rounded-sm gap-1 h-7 text-xs">
            <Paperclip className="h-3 w-3" /> Joindre au devis
          </Button>
        )}
      </div>
      <div ref={mountRef} data-testid="three-canvas"
           className="w-full border border-border rounded-sm overflow-hidden bg-secondary/30"
           style={{ height: imageHeight, cursor: "grab" }} />
      <p className="text-[10px] text-muted-foreground text-center">
        <Move3d className="h-3 w-3 inline mr-1" />
        Clic-glisser pour orbiter · Molette pour zoomer
      </p>
    </div>
  );
}

export default Interactive3D;
