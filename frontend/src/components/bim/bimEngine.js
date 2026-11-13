/*
 * Motor do visualizador BIM ConstruPilot — That Open Engine (MIT) + web-ifc (MPL-2.0) sobre three.js.
 * Carregado só na página /bim (import dinâmico): não pesa no resto da aplicação.
 *
 *   const viewer = await createBimViewer(container, { onSelect });
 *   await viewer.loadIfc(bytes, "Moradia");
 *   viewer.fit(); viewer.setSection(1.2); viewer.dispose();
 */
import * as THREE from "three";
import * as OBC from "@thatopen/components";

const ASSET_BASE = `${process.env.PUBLIC_URL || ""}/bim/`;
const HIGHLIGHT = { color: new THREE.Color("#f97316"), renderedFaces: 1, opacity: 1, transparent: false };

async function workerUrl() {
  // Worker servido pelo próprio site e passado como blob: não depende do tipo MIME de .mjs no alojamento.
  const res = await fetch(`${ASSET_BASE}fragments-worker.js`);
  if (!res.ok) throw new Error("Worker BIM em falta (public/bim). Execute scripts/copy-bim-assets.cjs.");
  const blob = new Blob([await res.text()], { type: "text/javascript" });
  return URL.createObjectURL(blob);
}

export async function createBimViewer(container, { onSelect, background = "#f5f5f4" } = {}) {
  const components = new OBC.Components();
  const world = components.get(OBC.Worlds).create();
  world.scene = new OBC.SimpleScene(components);
  world.scene.setup();
  world.scene.three.background = new THREE.Color(background);
  world.renderer = new OBC.SimpleRenderer(components, container);
  world.camera = new OBC.OrthoPerspectiveCamera(components);
  components.init();
  await world.camera.controls.setLookAt(18, 14, 18, 5, 0, 4);
  components.get(OBC.Grids).create(world);

  const fragments = components.get(OBC.FragmentsManager);
  const blobUrl = await workerUrl();
  fragments.init(blobUrl);
  world.camera.controls.addEventListener("rest", () => fragments.core.update(true));
  fragments.list.onItemSet.add(({ value: model }) => {
    model.useCamera(world.camera.three);
    world.scene.three.add(model.object);
    fragments.core.update(true);
  });

  const ifcLoader = components.get(OBC.IfcLoader);
  await ifcLoader.setup({ autoSetWasm: false, wasm: { path: ASSET_BASE, absolute: true } });

  const clipper = components.get(OBC.Clipper);
  clipper.enabled = true;
  let sectionId = null;
  let selected = null; // { model, localId }
  const casters = components.get(OBC.Raycasters);
  const caster = casters.get(world);

  async function clearSelection() {
    if (selected) {
      await selected.model.resetHighlight([selected.localId]);
      selected = null;
      await fragments.core.update(true);
    }
  }

  async function pick() {
    const hit = await caster.castRay();
    await clearSelection();
    if (!hit || hit.localId === undefined || !hit.fragments) {
      onSelect?.(null);
      return;
    }
    const model = hit.fragments;
    selected = { model, localId: hit.localId };
    await model.highlight([hit.localId], HIGHLIGHT);
    await fragments.core.update(true);
    const [data] = await model.getItemsData([hit.localId], {
      attributesDefault: true,
      relations: { IsDefinedBy: { attributes: true, relations: true }, HasAssociations: { attributes: true, relations: false } },
    });
    onSelect?.(describeItem(data));
  }

  // Clique simples (sem arrastar) = seleção.
  let down = null;
  const onDown = (e) => { down = [e.clientX, e.clientY]; };
  const onUp = (e) => {
    if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 4) pick();
    down = null;
  };
  container.addEventListener("pointerdown", onDown);
  container.addEventListener("pointerup", onUp);

  return {
    async loadIfc(bytes, name = "modelo") {
      for (const id of [...fragments.list.keys()]) await fragments.core.disposeModel(id);
      await clearSelection();
      const model = await ifcLoader.load(new Uint8Array(bytes), true, name);
      await this.fit();
      return model;
    },
    async fit() {
      await world.camera.fitToItems();
    },
    /** Corte horizontal à cota `z` (m), como uma planta de arquitetura; `null` retira o corte. */
    setSection(z) {
      if (sectionId) { clipper.delete(world, sectionId); sectionId = null; }
      if (z === null || z === undefined) return;
      sectionId = clipper.createFromNormalAndCoplanarPoint(world, new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, z, 0));
      const plane = clipper.list.get(sectionId);
      if (plane) plane.visible = false;
    },
    async setProjection(mode) {
      await world.camera.projection.set(mode === "ortho" ? "Orthographic" : "Perspective");
    },
    clearSelection,
    dispose() {
      container.removeEventListener("pointerdown", onDown);
      container.removeEventListener("pointerup", onUp);
      components.dispose();
      URL.revokeObjectURL(blobUrl);
    },
  };
}

const val = (a) => (a && typeof a === "object" && "value" in a ? a.value : a);

/** Converte os dados de um elemento (atributos + Psets/Qtos) numa ficha simples para o painel. */
export function describeItem(data) {
  if (!data) return null;
  const psets = [];
  for (const rel of data.IsDefinedBy || []) {
    const name = val(rel.Name);
    const props = [];
    for (const p of [...(rel.HasProperties || []), ...(rel.Quantities || [])]) {
      const v = val(p.NominalValue) ?? val(p.LengthValue) ?? val(p.AreaValue) ?? val(p.VolumeValue)
        ?? val(p.CountValue) ?? val(p.WeightValue);
      if (val(p.Name)) props.push({ name: val(p.Name), value: v });
    }
    if (name) psets.push({ name, props });
  }
  const material = (data.HasAssociations || []).map((m) => val(m.Name)).filter(Boolean)[0] || null;
  return {
    guid: val(data._guid) || val(data.GlobalId) || null,
    ifcClass: val(data._category) || null,
    name: val(data.Name) || null,
    localId: val(data._localId) ?? null,
    material,
    psets,
  };
}
