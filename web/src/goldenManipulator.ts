import * as THREE from "three";

export type ManipMode = "move" | "rotate";

const HANDLE_TAG = "golden_rotate_handle";
const GIZMO_COLOR = 0x6699cc;

/** API uses `room_id:piece_id`; golden draft rows use `piece_id` only. */
export function localFurnitureId(id: string): string {
  const i = id.lastIndexOf(":");
  return i >= 0 ? id.slice(i + 1) : id;
}

export function findFurnitureMesh(
  group: THREE.Group,
  furnitureId: string
): THREE.Object3D | null {
  const want = localFurnitureId(furnitureId);
  let found: THREE.Object3D | null = null;
  group.traverse((obj) => {
    const fid = obj.userData?.furniture_id as string | undefined;
    if (!found && fid && localFurnitureId(fid) === want) {
      found = obj;
    }
  });
  return found;
}

export function meshCenterXZ(mesh: THREE.Object3D): { x: number; z: number } {
  const box = new THREE.Box3().setFromObject(mesh);
  const c = new THREE.Vector3();
  box.getCenter(c);
  return { x: c.x, z: c.z };
}

export function clampToRoom(
  x: number,
  z: number,
  roomW: number,
  roomL: number
): { x: number; z: number } {
  return {
    x: Math.max(0.05, Math.min(roomW - 0.05, x)),
    z: Math.max(0.05, Math.min(roomL - 0.05, z)),
  };
}

/** Shortest signed quarter-turn steps from one orientation to another. */
export function orientStepDelta(from: number, to: number): number {
  let d = ((to - from) % 4 + 4) % 4;
  if (d === 3) return -1;
  return d;
}

export function orientationFromDragDelta(
  startOrient: number,
  startAngleRad: number,
  pointerAngleRad: number
): number {
  const delta = pointerAngleRad - startAngleRad;
  const steps = Math.round(delta / (Math.PI / 2));
  return ((startOrient + steps) % 4 + 4) % 4;
}

/** Rotate around Y in place, keeping the footprint center fixed. */
export function stepMeshRotation(mesh: THREE.Object3D, quarterTurns: number): void {
  if (quarterTurns === 0) return;
  const before = meshCenterXZ(mesh);
  mesh.rotation.y += quarterTurns * (Math.PI / 2);
  const after = meshCenterXZ(mesh);
  mesh.position.x += before.x - after.x;
  mesh.position.z += before.z - after.z;
}

/** Small corner arc + dot — subtle rotate affordance. */
export class RotateGizmo {
  readonly group = new THREE.Group();

  constructor(private scene: THREE.Scene) {
    this.group.name = "golden_rotate_gizmo";
    this.scene.add(this.group);
  }

  dispose(): void {
    this.clearMeshes();
    this.scene.remove(this.group);
  }

  private clearMeshes(): void {
    for (const child of [...this.group.children]) {
      child.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.geometry.dispose();
          (o.material as THREE.Material).dispose();
        }
      });
      this.group.remove(child);
    }
  }

  update(mesh: THREE.Object3D | null): void {
    this.clearMeshes();
    if (!mesh) return;

    const box = new THREE.Box3().setFromObject(mesh);
    const cx = (box.min.x + box.max.x) / 2;
    const cz = (box.min.z + box.max.z) / 2;
    const cornerX = box.max.x + 0.04;
    const cornerZ = box.max.z + 0.04;

    const mat = new THREE.MeshBasicMaterial({
      color: GIZMO_COLOR,
      transparent: true,
      opacity: 0.72,
      depthTest: false,
    });

    const arc = new THREE.Mesh(
      new THREE.TorusGeometry(0.1, 0.01, 6, 12, Math.PI / 2),
      mat
    );
    arc.rotation.x = Math.PI / 2;
    arc.position.set(cornerX, 0.05, cornerZ);
    arc.renderOrder = 10;
    arc.userData[HANDLE_TAG] = true;
    this.group.add(arc);

    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(0.035, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0x99ccee, depthTest: false })
    );
    dot.position.set(cornerX + 0.1, 0.07, cornerZ);
    dot.renderOrder = 11;
    dot.userData[HANDLE_TAG] = true;
    this.group.add(dot);

    const tick = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.008, 0.008),
      mat
    );
    tick.position.set(cx, 0.04, box.min.z - 0.03);
    tick.renderOrder = 9;
    this.group.add(tick);
  }

  follow(mesh: THREE.Object3D): void {
    this.update(mesh);
  }

  isRotateHandle(object: THREE.Object3D | null): boolean {
    let o: THREE.Object3D | null = object;
    while (o) {
      if (o.userData?.[HANDLE_TAG]) return true;
      o = o.parent;
    }
    return false;
  }

  raycast(raycaster: THREE.Raycaster): THREE.Intersection | null {
    const gizmoHits = raycaster.intersectObjects(this.group.children, true);
    for (const h of gizmoHits) {
      if (this.isRotateHandle(h.object)) return h;
    }
    return null;
  }
}
