import * as THREE from "three";
import type { KenneyPlacement } from "./api";
import { loadKenneyModel } from "./kenneyLoad";

const CLAMP_EPS = 0.02;

export interface LoadPlacementsOptions {
  room_width_m?: number;
  room_length_m?: number;
}

function alignToFootprint(model: THREE.Object3D, p: KenneyPlacement): void {
  const [px, py, pz] = p.position_m;
  const [sx, sy, sz] = p.scale;
  model.scale.set(sx, sy, sz);
  model.rotation.y = p.rotation_y_rad;

  const box = new THREE.Box3().setFromObject(model);
  const center = new THREE.Vector3();
  box.getCenter(center);
  const floorY = py > 0 ? py : 0;
  model.position.set(px - center.x, floorY - box.min.y, pz - center.z);
}

/** Shift so back edge (opposite front) sits on wall-touching footprint edge. */
function applyWallAnchor(
  model: THREE.Object3D,
  footprint: [number, number, number, number],
  wallAnchor: string | undefined,
  roomW: number,
  roomL: number
): void {
  if (wallAnchor !== "back_center") return;
  const [x0, z0, x1, z1] = footprint;
  const box = new THREE.Box3().setFromObject(model);
  const eps = 0.1;
  if (x0 < eps) model.position.x += x0 - box.min.x;
  if (x1 > roomW - eps) model.position.x += x1 - box.max.x;
  if (z0 < eps) model.position.z += z0 - box.min.z;
  if (z1 > roomL - eps) model.position.z += z1 - box.max.z;
}

/** Nudge mesh AABB inside footprint and room bounds. */
export function clampModelToBounds(
  model: THREE.Object3D,
  footprint: [number, number, number, number],
  roomW: number,
  roomL: number
): void {
  const [x0, z0, x1, z1] = footprint;
  const inner = {
    x0: x0 + CLAMP_EPS,
    z0: z0 + CLAMP_EPS,
    x1: x1 - CLAMP_EPS,
    z1: z1 - CLAMP_EPS,
  };
  const room = {
    x0: CLAMP_EPS,
    z0: CLAMP_EPS,
    x1: roomW - CLAMP_EPS,
    z1: roomL - CLAMP_EPS,
  };

  for (let pass = 0; pass < 4; pass++) {
    const box = new THREE.Box3().setFromObject(model);
    if (box.min.x < inner.x0) model.position.x += inner.x0 - box.min.x;
    if (box.max.x > inner.x1) model.position.x += inner.x1 - box.max.x;
    if (box.min.z < inner.z0) model.position.z += inner.z0 - box.min.z;
    if (box.max.z > inner.z1) model.position.z += inner.z1 - box.max.z;
    const box2 = new THREE.Box3().setFromObject(model);
    if (box2.min.x < room.x0) model.position.x += room.x0 - box2.min.x;
    if (box2.max.x > room.x1) model.position.x += room.x1 - box2.max.x;
    if (box2.min.z < room.z0) model.position.z += room.z0 - box2.min.z;
    if (box2.max.z > room.z1) model.position.z += room.z1 - box2.max.z;
  }
}

export async function loadPlacements(
  group: THREE.Group,
  placements: KenneyPlacement[],
  onProgress?: (msg: string) => void,
  options?: LoadPlacementsOptions
): Promise<void> {
  const roomW = options?.room_width_m ?? 20;
  const roomL = options?.room_length_m ?? 20;

  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    child.traverse((o) => {
      if (o instanceof THREE.Mesh) {
        o.geometry?.dispose();
        const m = o.material;
        if (Array.isArray(m)) m.forEach((x) => x.dispose());
        else m?.dispose();
      }
    });
  }

  let loaded = 0;
  let failed = 0;

  for (const p of placements) {
    onProgress?.(`Loading ${p.model_id}…`);
    try {
      const model = await loadKenneyModel(p.obj_url, p.mtl_url);
      alignToFootprint(model, p);
      applyWallAnchor(model, p.footprint_m, p.wall_anchor, roomW, roomL);
      clampModelToBounds(model, p.footprint_m, roomW, roomL);
      model.userData = { furniture_id: p.furniture_id, category: p.category };
      group.add(model);
      loaded++;
    } catch (e) {
      failed++;
      const msg = e instanceof Error ? e.message : String(e);
      onProgress?.(`Failed ${p.model_id}: ${msg}`);
      console.error("Kenney load failed", p, e);
      const [x0, z0, x1, z1] = p.footprint_m;
      const fw = new THREE.Mesh(
        new THREE.BoxGeometry(x1 - x0, 0.35, z1 - z0),
        new THREE.MeshStandardMaterial({
          color: 0xff6644,
          transparent: true,
          opacity: 0.7,
        })
      );
      fw.position.set((x0 + x1) / 2, 0.175, (z0 + z1) / 2);
      group.add(fw);
    }
  }

  onProgress?.(
    `Meshes: ${loaded} Kenney models, ${failed} fallbacks (orange = load error).`
  );
}
