import * as THREE from "three";
import type { KenneyPlacement } from "./api";
import { localFurnitureId } from "./goldenManipulator";
import { loadKenneyModel } from "./kenneyLoad";

const CLAMP_EPS = 0.02;

export interface LoadPlacementsOptions {
  room_width_m?: number;
  room_length_m?: number;
  /** When true, discard this load (another preview superseded it). */
  isStale?: () => boolean;
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

function disposeObject3D(root: THREE.Object3D): void {
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.geometry?.dispose();
      const m = o.material;
      if (Array.isArray(m)) m.forEach((x) => x.dispose());
      else m?.dispose();
    }
  });
}

function clearGroup(group: THREE.Group): void {
  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    disposeObject3D(child);
  }
}

function placementDrawOrder(p: KenneyPlacement): number {
  const id = p.model_id.toLowerCase();
  if (id.includes("rug")) return 0;
  if (id.includes("lamp")) return 2;
  return 1;
}

export async function buildPlacementMesh(
  p: KenneyPlacement,
  roomW: number,
  roomL: number
): Promise<THREE.Object3D> {
  try {
    const model = await loadKenneyModel(p.obj_url, p.mtl_url);
    alignToFootprint(model, p);
    applyWallAnchor(model, p.footprint_m, p.wall_anchor ?? undefined, roomW, roomL);
    clampModelToBounds(model, p.footprint_m, roomW, roomL);
    model.userData = {
      furniture_id: localFurnitureId(p.furniture_id),
      category: p.category,
    };
    return model;
  } catch (e) {
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
    fw.userData = {
      furniture_id: localFurnitureId(p.furniture_id),
      category: p.category,
    };
    return fw;
  }
}

export async function loadPlacements(
  group: THREE.Group,
  placements: KenneyPlacement[],
  onProgress?: (msg: string) => void,
  options?: LoadPlacementsOptions
): Promise<boolean> {
  const roomW = options?.room_width_m ?? 20;
  const roomL = options?.room_length_m ?? 20;
  const stale = options?.isStale ?? (() => false);

  let loaded = 0;
  let failed = 0;
  const meshes: THREE.Object3D[] = [];

  const ordered = [...placements].sort(
    (a, b) => placementDrawOrder(a) - placementDrawOrder(b)
  );

  for (const p of ordered) {
    if (stale()) return false;
    onProgress?.(`Loading ${p.model_id}…`);
    try {
      const model = await buildPlacementMesh(p, roomW, roomL);
      if (stale()) return false;
      meshes.push(model);
      loaded++;
    } catch (e) {
      failed++;
      const msg = e instanceof Error ? e.message : String(e);
      onProgress?.(`Failed ${p.model_id}: ${msg}`);
    }
  }

  if (stale()) return false;

  clearGroup(group);
  for (const mesh of meshes) {
    group.add(mesh);
  }

  onProgress?.(
    `Meshes: ${loaded} Kenney models, ${failed} fallbacks (orange = load error).`
  );
  return true;
}
