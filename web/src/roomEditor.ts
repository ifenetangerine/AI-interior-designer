import * as THREE from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const MIN_DIM = 2;
const MAX_DIM = 12;
const WALL_HEIGHT = 0.15;
const HANDLE_SIZE = 0.2;

export type WallSide = "south" | "west" | "east" | "north";

export interface RoomArchitecture {
  door_wall: WallSide;
  door_offset_m: number;
  door_width_m: number;
  focal_wall: WallSide | null;
  focal_center_x_m: number | null;
  focal_center_z_m: number | null;
}

export interface RoomState {
  width_m: number;
  length_m: number;
  architecture: RoomArchitecture;
}

type DragId = "east" | "north" | "door" | "focal";

export function defaultArchitecture(
  width_m: number,
  length_m: number,
  roomType = "living_room"
): RoomArchitecture {
  const focal_wall: WallSide =
    roomType === "bedroom" ? "west" : "north";
  let focal_x = width_m / 2;
  let focal_z = length_m / 2;
  if (focal_wall === "north") focal_z = length_m;
  else if (focal_wall === "south") focal_z = 0;
  else if (focal_wall === "west") focal_x = 0;
  else if (focal_wall === "east") focal_x = width_m;

  return {
    door_wall: "south",
    door_offset_m: Math.max(0, width_m / 2 - 0.45),
    door_width_m: 0.9,
    focal_wall,
    focal_center_x_m: focal_x,
    focal_center_z_m: focal_z,
  };
}

function doorCenter(arch: RoomArchitecture, w: number, d: number): [number, number] {
  const half = arch.door_width_m / 2;
  const along = arch.door_offset_m + half;
  switch (arch.door_wall) {
    case "south":
      return [along, 0.08];
    case "north":
      return [along, d - 0.08];
    case "west":
      return [0.08, along];
    case "east":
      return [w - 0.08, along];
  }
}

export class RoomEditor {
  readonly group = new THREE.Group();
  private floor: THREE.Mesh;
  private walls: THREE.Group;
  private handles: THREE.Group;
  private width_m: number;
  private length_m: number;
  private architecture: RoomArchitecture;
  private onChange: (state: RoomState) => void;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private intersect = new THREE.Vector3();
  private dragging: DragId | null = null;
  private domElement: HTMLElement;
  private camera: THREE.Camera;
  private orbit: OrbitControls;

  constructor(
    scene: THREE.Scene,
    camera: THREE.Camera,
    domElement: HTMLElement,
    orbit: OrbitControls,
    onChange: (state: RoomState) => void,
    initial?: Partial<RoomState>
  ) {
    this.camera = camera;
    this.domElement = domElement;
    this.orbit = orbit;
    this.onChange = onChange;
    this.width_m = initial?.width_m ?? 4;
    this.length_m = initial?.length_m ?? 3.5;
    this.architecture =
      initial?.architecture ??
      defaultArchitecture(this.width_m, this.length_m);

    this.floor = new THREE.Mesh(
      new THREE.PlaneGeometry(1, 1),
      new THREE.MeshStandardMaterial({
        color: 0x4a6a8a,
        transparent: true,
        opacity: 0.45,
        side: THREE.DoubleSide,
      })
    );
    this.floor.rotation.x = -Math.PI / 2;
    this.floor.receiveShadow = true;
    this.group.add(this.floor);

    this.walls = new THREE.Group();
    this.handles = new THREE.Group();
    this.group.add(this.walls);
    this.group.add(this.handles);
    scene.add(this.group);

    this._rebuild();
    this._bindPointer();
  }

  getState(): RoomState {
    return {
      width_m: this.width_m,
      length_m: this.length_m,
      architecture: { ...this.architecture },
    };
  }

  setDimensions(width_m: number, length_m: number): void {
    this.width_m = THREE.MathUtils.clamp(width_m, MIN_DIM, MAX_DIM);
    this.length_m = THREE.MathUtils.clamp(length_m, MIN_DIM, MAX_DIM);
    this._rebuild();
    this.onChange(this.getState());
  }

  private _rebuild(): void {
    const w = this.width_m;
    const d = this.length_m;

    this.floor.scale.set(w, d, 1);
    this.floor.position.set(w / 2, 0.01, d / 2);

    while (this.walls.children.length) {
      const c = this.walls.children[0];
      this.walls.remove(c);
      if (c instanceof THREE.Mesh) {
        c.geometry.dispose();
        (c.material as THREE.Material).dispose();
      }
    }

    const wallMat = new THREE.MeshStandardMaterial({
      color: 0x88aacc,
      emissive: 0x223344,
    });
    const addWall = (pw: number, pd: number, px: number, pz: number) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(pw, WALL_HEIGHT, pd), wallMat);
      m.position.set(px, WALL_HEIGHT / 2, pz);
      this.walls.add(m);
    };

    addWall(w, 0.06, w / 2, 0.03);
    addWall(w, 0.06, w / 2, d - 0.03);
    addWall(0.06, d, 0.03, d / 2);
    addWall(0.06, d, w - 0.03, d / 2);

    while (this.handles.children.length) {
      const c = this.handles.children[0];
      this.handles.remove(c);
      if (c instanceof THREE.Mesh) {
        c.geometry.dispose();
        (c.material as THREE.Material).dispose();
      }
    }

    const resizeMat = new THREE.MeshStandardMaterial({
      color: 0xffcc66,
      emissive: 0x554400,
    });
    const doorMat = new THREE.MeshStandardMaterial({
      color: 0x44aaff,
      emissive: 0x113355,
    });
    const focalMat = new THREE.MeshStandardMaterial({
      color: 0xff66cc,
      emissive: 0x551133,
    });

    const addHandle = (id: DragId, px: number, pz: number, mat: THREE.Material) => {
      const h = new THREE.Mesh(
        new THREE.BoxGeometry(HANDLE_SIZE, HANDLE_SIZE * 1.5, HANDLE_SIZE),
        mat
      );
      h.position.set(px, HANDLE_SIZE, pz);
      h.userData.dragId = id;
      this.handles.add(h);
    };

    addHandle("east", w, d / 2, resizeMat);
    addHandle("north", w / 2, d, resizeMat);

    const [dx, dz] = doorCenter(this.architecture, w, d);
    addHandle("door", dx, dz, doorMat);

    const fx = this.architecture.focal_center_x_m ?? w / 2;
    const fz = this.architecture.focal_center_z_m ?? d / 2;
    addHandle("focal", fx, fz, focalMat);
  }

  private _bindPointer(): void {
    const el = this.domElement;
    el.addEventListener("pointerdown", this._onPointerDown);
    el.addEventListener("pointermove", this._onPointerMove);
    el.addEventListener("pointerup", this._onPointerUp);
    el.addEventListener("pointerleave", this._onPointerUp);
  }

  private _onPointerDown = (e: PointerEvent): void => {
    if (this.dragging) return;
    const hit = this._raycastHandles(e);
    if (!hit) return;
    this.dragging = hit.userData.dragId as DragId;
    this.orbit.enabled = false;
    e.preventDefault();
  };

  private _onPointerMove = (e: PointerEvent): void => {
    if (!this.dragging) return;
    this._updatePointer(e);
    this.raycaster.ray.intersectPlane(this.dragPlane, this.intersect);
    const w = this.width_m;
    const d = this.length_m;

    if (this.dragging === "east") {
      this.width_m = THREE.MathUtils.clamp(this.intersect.x, MIN_DIM, MAX_DIM);
    } else if (this.dragging === "north") {
      this.length_m = THREE.MathUtils.clamp(this.intersect.z, MIN_DIM, MAX_DIM);
    } else if (this.dragging === "door") {
      const half = this.architecture.door_width_m / 2;
      if (this.architecture.door_wall === "south" || this.architecture.door_wall === "north") {
        const x = THREE.MathUtils.clamp(this.intersect.x - half, 0, w - this.architecture.door_width_m);
        this.architecture.door_offset_m = x;
      } else {
        const z = THREE.MathUtils.clamp(this.intersect.z - half, 0, d - this.architecture.door_width_m);
        this.architecture.door_offset_m = z;
      }
    } else if (this.dragging === "focal") {
      const x = THREE.MathUtils.clamp(this.intersect.x, 0, w);
      const z = THREE.MathUtils.clamp(this.intersect.z, 0, d);
      this.architecture.focal_center_x_m = x;
      this.architecture.focal_center_z_m = z;
      const distNorth = d - z;
      const distSouth = z;
      const distWest = x;
      const distEast = w - x;
      const min = Math.min(distNorth, distSouth, distWest, distEast);
      if (min === distNorth) this.architecture.focal_wall = "north";
      else if (min === distSouth) this.architecture.focal_wall = "south";
      else if (min === distWest) this.architecture.focal_wall = "west";
      else this.architecture.focal_wall = "east";
    }
    this._rebuild();
    this.onChange(this.getState());
  };

  private _onPointerUp = (): void => {
    if (!this.dragging) return;
    this.dragging = null;
    this.orbit.enabled = true;
  };

  private _raycastHandles(e: PointerEvent): THREE.Object3D | null {
    this._updatePointer(e);
    const hits = this.raycaster.intersectObjects(this.handles.children, false);
    return hits.length ? hits[0].object : null;
  }

  private _updatePointer(e: PointerEvent): void {
    const rect = this.domElement.getBoundingClientRect();
    this.pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
  }
}

export function randomRoom(): { type: string; width_m: number; length_m: number } {
  const types = ["bedroom", "living_room", "kitchen"];
  const type = types[Math.floor(Math.random() * types.length)];
  const width_m = Math.round((3 + Math.random() * 3) * 10) / 10;
  const length_m = Math.round((3 + Math.random() * 2.5) * 10) / 10;
  return { type, width_m, length_m };
}
