import * as THREE from "three";
import { BoxHelper } from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  previewGoldenDraft,
  saveGoldenLayout,
  validateGoldenDraft,
  listGoldenLayouts,
  getGoldenLayout,
  getGoldenStorageDir,
  type DraftPlacement,
  type CatalogAsset,
} from "./api";
import type { CatalogPanelController } from "./catalogPanel";
import { buildPlacementMesh, loadPlacements } from "./furnitureLoader";
import { clearPlacementOverlay } from "./placementOverlay";
import type { RoomEditor, RoomState } from "./roomEditor";
import { getCatalogThumbnail } from "./catalogThumbnail";
import {
  clampToRoom,
  findFurnitureMesh,
  localFurnitureId,
  meshCenterXZ,
  orientationFromDragDelta,
  orientStepDelta,
  RotateGizmo,
  stepMeshRotation,
} from "./goldenManipulator";
import { setOrbitTarget } from "./scene";
import { setStatus, type UIElements } from "./ui";

function formatDim(d: number): string {
  return String(d).replace(".", "_");
}

function nextUniqueGoldenId(base: string, used: Set<string>): string {
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}_${n}`)) n++;
  return `${base}_${n}`;
}

function nextPlacementId(role: string, placements: DraftPlacement[]): string {
  const prefix = role || "piece";
  const used = new Set(placements.map((p) => p.id));
  let n = 1;
  while (used.has(`${prefix}_${n}`)) n++;
  return `${prefix}_${n}`;
}

const ZONES = [
  "",
  "sleep",
  "work",
  "storage",
  "viewing",
  "dining",
  "kitchen",
  "decor",
] as const;

export interface GoldenEditorDeps {
  ui: UIElements;
  editor: RoomEditor;
  furnitureGroup: THREE.Group;
  scene: THREE.Scene;
  camera: THREE.Camera;
  domElement: HTMLElement;
  controls: OrbitControls;
  catalog: CatalogPanelController;
  getRoomState: () => RoomState;
  setRoomState: (s: RoomState) => void;
}

export class GoldenEditor {
  private placements: DraftPlacement[] = [];
  private selectedId: string | null = null;
  private pendingModel: CatalogAsset | null = null;
  private activeManip: "move" | "rotate" | null = null;
  private dragGrabOffset: { x: number; z: number } | null = null;
  private rotateStartAngle: number | null = null;
  private rotateStartOrient: number | null = null;
  private windowDragBound = false;
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  private intersect = new THREE.Vector3();
  private highlight: BoxHelper | null = null;
  private rotateGizmo: RotateGizmo;
  private previewTimer: ReturnType<typeof setTimeout> | null = null;
  private previewGen = 0;
  private previewQueue: Promise<void> = Promise.resolve();
  /** ID of the layout loaded from disk; save overwrites only when this matches Golden ID. */
  private loadedGoldenId: string | null = null;

  constructor(private deps: GoldenEditorDeps) {
    this.rotateGizmo = new RotateGizmo(this.deps.scene);
    this.bindDom();
    this.renderPieceList();
    void this.refreshStorageHint();
    this.refreshLoadList();
    window.addEventListener("keydown", (e) => this.onKeyDown(e));
  }

  private el<T extends HTMLElement>(id: string): T {
    return document.getElementById(id) as T;
  }

  private bindDom(): void {
    const roomType = this.el<HTMLSelectElement>("golden-room-type");
    roomType.addEventListener("change", () => {
      this.refreshLoadList();
      this.deps.catalog.refresh();
    });

    document.querySelectorAll<HTMLButtonElement>(".preset-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const w = parseFloat(btn.dataset.w ?? "4");
        const l = parseFloat(btn.dataset.l ?? "3.5");
        this.deps.editor.setDimensions(w, l);
        const st = this.deps.getRoomState();
        st.width_m = w;
        st.length_m = l;
        this.deps.setRoomState(st);
        this.updateDimLabels();
        this.schedulePreview();
      });
    });

    this.el<HTMLButtonElement>("btn-golden-catalog").addEventListener("click", () => {
      this.el<HTMLButtonElement>("btn-catalog").click();
    });
    this.el<HTMLButtonElement>("btn-golden-add").addEventListener("click", () => this.addRow());
    this.el<HTMLButtonElement>("btn-golden-preview").addEventListener("click", () => this.preview());
    this.el<HTMLButtonElement>("btn-golden-validate").addEventListener("click", () => this.validate());
    this.el<HTMLButtonElement>("btn-golden-save").addEventListener("click", () => this.save());

    this.el<HTMLSelectElement>("golden-load-select").addEventListener("change", async () => {
      const id = this.el<HTMLSelectElement>("golden-load-select").value;
      if (!id) {
        await this.beginNewLayout();
        return;
      }
      await this.loadGolden(id);
    });

    const el = this.deps.domElement;
    const cap = { capture: true };
    el.addEventListener("pointerdown", (e) => this.onPointerDown(e), cap);
    el.addEventListener("pointermove", (e) => this.onPointerMove(e), cap);
    el.addEventListener("pointerup", (e) => this.onPointerUp(e), cap);
    el.addEventListener("pointercancel", (e) => this.onPointerUp(e), cap);

    this.deps.domElement.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer!.dropEffect = "copy";
    });
    this.deps.domElement.addEventListener("drop", (e) => this.onDrop(e));
  }

  activate(): void {
    void this.refreshLoadList();
    void this.refreshStorageHint();
    this.deps.catalog.setOnItemSelect((asset) => {
      this.pendingModel = asset;
      setStatus(
        this.deps.ui,
        `Place: ${asset.id} — click floor to drop. Drag to move; corner arc or R to rotate.`
      );
    });
    this.updateDimLabels();
    setOrbitTarget(
      this.deps.controls,
      this.deps.camera as THREE.PerspectiveCamera,
      this.deps.getRoomState().width_m,
      this.deps.getRoomState().length_m
    );
    if (this.placements.length > 0) {
      this.schedulePreview();
    }
  }

  deactivate(): void {
    this.deps.catalog.setOnItemSelect(null);
    this.pendingModel = null;
    if (this.activeManip) this.endManip();
    this.detachWindowDrag();
    this.clearSelectionVisuals();
    this.deps.domElement.style.cursor = "";
    this.deps.controls.enabled = true;
  }

  private onKeyDown(e: KeyboardEvent): void {
    const tab = document.getElementById("tab-golden") as HTMLElement | null;
    if (!tab || tab.hidden) return;
    if ((e.key === "r" || e.key === "R") && this.selectedId) {
      const p = this.placements.find((x) => x.id === this.selectedId);
      const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
      if (p && mesh) {
        this.applyRotateImmediate(p.id, (p.orientation + 1) % 4, mesh);
        this.renderPieceList();
        this.queueSyncMeshes();
      }
    }
  }

  private updateDimLabels(): void {
    const st = this.deps.getRoomState();
    this.el<HTMLSpanElement>("golden-width-label").textContent = st.width_m.toFixed(1);
    this.el<HTMLSpanElement>("golden-length-label").textContent = st.length_m.toFixed(1);
  }

  private draftPayload() {
    const st = this.deps.getRoomState();
    const roomType = this.el<HTMLSelectElement>("golden-room-type").value;
    const id = this.el<HTMLInputElement>("golden-id").value.trim() || "golden";
    return {
      room_type: roomType,
      width_m: st.width_m,
      length_m: st.length_m,
      architecture: st.architecture,
      draft: {
        room_id: id,
        room_type: roomType,
        placements: this.placements.map((p, i) => ({
          ...p,
          placement_order: i + 1,
        })),
      },
    };
  }

  private isActive(): boolean {
    const tab = document.getElementById("tab-golden") as HTMLElement | null;
    return Boolean(tab && !tab.hidden);
  }

  private setPointerFromEvent(clientX: number, clientY: number): void {
    const rect = this.deps.domElement.getBoundingClientRect();
    this.pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.deps.camera as THREE.PerspectiveCamera);
  }

  private floorHit(clientX: number, clientY: number): { x: number; z: number } | null {
    this.setPointerFromEvent(clientX, clientY);
    const st = this.deps.getRoomState();
    const floorPt = this.deps.editor.raycastFloor(this.raycaster);
    if (floorPt) {
      return clampToRoom(floorPt.x, floorPt.z, st.width_m, st.length_m);
    }
    if (!this.raycaster.ray.intersectPlane(this.floorPlane, this.intersect)) return null;
    return clampToRoom(this.intersect.x, this.intersect.z, st.width_m, st.length_m);
  }

  private meshHit(clientX: number, clientY: number): string | null {
    this.setPointerFromEvent(clientX, clientY);
    const hits = this.raycaster.intersectObjects(this.deps.furnitureGroup.children, true);
    for (const h of hits) {
      let o: THREE.Object3D | null = h.object;
      while (o) {
        const fid = o.userData?.furniture_id as string | undefined;
        if (fid) {
          const local = localFurnitureId(fid);
          if (this.placements.some((p) => p.id === local)) return local;
          break;
        }
        o = o.parent;
      }
    }
    return null;
  }

  private cleanupReferences(removedId: string): void {
    for (const p of this.placements) {
      if (p.relative_to === removedId) p.relative_to = null;
      if (p.on_surface_of === removedId) p.on_surface_of = null;
    }
  }

  private removeMeshFromScene(furnitureId: string): void {
    const mesh = findFurnitureMesh(this.deps.furnitureGroup, furnitureId);
    if (!mesh) return;
    this.deps.furnitureGroup.remove(mesh);
    if (this.highlight && this.selectedId === furnitureId) {
      this.clearSelectionVisuals();
    }
  }

  private removePlacement(id: string): void {
    this.cleanupReferences(id);
    this.placements = this.placements.filter((x) => x.id !== id);
    this.removeMeshFromScene(id);
    if (this.selectedId === id) this.selectedId = null;
    this.renderPieceList();
    if (this.placements.length === 0) {
      void this.preview();
    } else {
      setStatus(
        this.deps.ui,
        `${this.sceneFurnitureIds().size} piece(s) in 3D (${this.placements.length} in layout)`
      );
    }
  }

  private rotateHandleHit(clientX: number, clientY: number): boolean {
    this.setPointerFromEvent(clientX, clientY);
    return this.rotateGizmo.raycast(this.raycaster) !== null;
  }

  private selectPiece(id: string, rerender = true): void {
    this.selectedId = id;
    if (rerender) this.renderPieceList();
    this.updateSelectionVisuals();
  }

  private clearSelectionVisuals(): void {
    this.clearHighlight();
    this.rotateGizmo.update(null);
  }

  private updateSelectionVisuals(): void {
    if (!this.selectedId) {
      this.clearSelectionVisuals();
      return;
    }
    const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
    const p = this.placements.find((x) => x.id === this.selectedId);
    if (!mesh || !p) {
      this.clearSelectionVisuals();
      return;
    }
    this.updateHighlight(mesh);
    this.rotateGizmo.update(mesh);
  }

  private syncCoordInputs(id: string): void {
    const p = this.placements.find((x) => x.id === id);
    if (!p) return;
    const card = this.el<HTMLDivElement>("golden-table-wrap").querySelector<HTMLElement>(
      `[data-id="${id}"]`
    );
    if (!card) return;
    const xInp = card.querySelector<HTMLInputElement>('input[data-f="center_x_m"]');
    const zInp = card.querySelector<HTMLInputElement>('input[data-f="center_z_m"]');
    const rotBtn = card.querySelector<HTMLButtonElement>("button[data-rot]");
    if (xInp) xInp.value = String(p.center_x_m);
    if (zInp) zInp.value = String(p.center_z_m);
    if (rotBtn) rotBtn.textContent = `↻ ${p.orientation}`;
  }

  private applyMoveImmediate(
    id: string,
    x: number,
    z: number,
    mesh: THREE.Object3D
  ): void {
    const row = this.placements.find((p) => p.id === id);
    if (!row) return;
    const cur = meshCenterXZ(mesh);
    mesh.position.x += x - cur.x;
    mesh.position.z += z - cur.z;
    row.center_x_m = Math.round(x * 100) / 100;
    row.center_z_m = Math.round(z * 100) / 100;
    this.highlight?.update();
    this.rotateGizmo.follow(mesh);
    this.syncCoordInputs(id);
  }

  private applyRotateImmediate(
    id: string,
    orientation: number,
    mesh: THREE.Object3D
  ): void {
    const row = this.placements.find((p) => p.id === id);
    if (!row || row.orientation === orientation) return;
    const delta = orientStepDelta(row.orientation, orientation);
    row.orientation = orientation;
    stepMeshRotation(mesh, delta);
    this.highlight?.update();
    this.rotateGizmo.follow(mesh);
    this.syncCoordInputs(id);
  }

  private attachWindowDrag(): void {
    if (this.windowDragBound) return;
    this.windowDragBound = true;
    window.addEventListener("pointermove", this.onWindowPointerMove, true);
    window.addEventListener("pointerup", this.onWindowPointerUp, true);
    window.addEventListener("pointercancel", this.onWindowPointerUp, true);
  }

  private detachWindowDrag(): void {
    if (!this.windowDragBound) return;
    this.windowDragBound = false;
    window.removeEventListener("pointermove", this.onWindowPointerMove, true);
    window.removeEventListener("pointerup", this.onWindowPointerUp, true);
    window.removeEventListener("pointercancel", this.onWindowPointerUp, true);
  }

  private onWindowPointerMove = (e: PointerEvent): void => {
    this.onPointerMove(e);
  };

  private onWindowPointerUp = (e: PointerEvent): void => {
    this.onPointerUp(e);
  };

  private beginManip(
    mode: "move" | "rotate",
    e: PointerEvent,
    floor: { x: number; z: number } | null
  ): void {
    if (this.previewTimer) {
      clearTimeout(this.previewTimer);
      this.previewTimer = null;
    }

    this.activeManip = mode;
    this.deps.controls.enabled = false;
    this.deps.domElement.style.cursor = mode === "move" ? "grabbing" : "ew-resize";
    if (mode === "move" && floor && this.selectedId) {
      const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
      if (mesh) {
        const center = meshCenterXZ(mesh);
        this.dragGrabOffset = {
          x: center.x - floor.x,
          z: center.z - floor.z,
        };
      }
    } else if (mode === "rotate" && this.selectedId) {
      const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
      const row = this.placements.find((p) => p.id === this.selectedId);
      if (mesh && row) {
        const center = meshCenterXZ(mesh);
        const pt = floor ?? { x: center.x + 0.12, z: center.z };
        this.rotateStartAngle = Math.atan2(pt.z - center.z, pt.x - center.x);
        this.rotateStartOrient = row.orientation;
      }
    }
    e.preventDefault();
    e.stopPropagation();
    this.deps.domElement.setPointerCapture(e.pointerId);
    this.attachWindowDrag();
  }

  private endManip(): void {
    const wasManip = this.activeManip !== null;
    const mode = this.activeManip;
    this.activeManip = null;
    this.dragGrabOffset = null;
    this.rotateStartAngle = null;
    this.rotateStartOrient = null;
    this.detachWindowDrag();
    this.deps.controls.enabled = true;
    this.deps.domElement.style.cursor = this.selectedId ? "grab" : "";
    if (wasManip) {
      this.renderPieceList();
      if (mode === "move") {
        // Re-sync stack links and mesh height (floor vs on-surface) immediately.
        this.queuePreview(() => this.runFullPreview());
      } else if (mode === "rotate") {
        this.queueSyncMeshes();
      }
    }
  }

  private onDrop(e: DragEvent): void {
    const tab = document.getElementById("tab-golden") as HTMLElement | null;
    if (!tab || tab.hidden) return;
    e.preventDefault();
    const modelId = e.dataTransfer?.getData("text/kenney-model");
    if (!modelId) return;
    const hit = this.floorHit(e.clientX, e.clientY);
    if (!hit) return;
    this.placeModel(modelId, hit.x, hit.z, "decor");
  }

  private placeModel(modelId: string, x: number, z: number, role: string): void {
    const id = nextPlacementId(role, this.placements);
    this.placements.push({
      id,
      model_id: modelId,
      placement_order: this.placements.length + 1,
      center_x_m: Math.round(x * 100) / 100,
      center_z_m: Math.round(z * 100) / 100,
      orientation: 0,
      relative_to: null,
      on_surface_of: null,
      composition_role: null,
      zone: null,
    });
    this.selectPiece(id);
    this.pendingModel = null;
    this.queueAppendMeshes();
  }

  private onPointerDown(e: PointerEvent): void {
    if (!this.isActive() || e.button !== 0) return;

    if (this.selectedId && this.rotateHandleHit(e.clientX, e.clientY)) {
      let floor = this.floorHit(e.clientX, e.clientY);
      if (!floor) {
        const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
        if (mesh) {
          const c = meshCenterXZ(mesh);
          floor = { x: c.x + 0.12, z: c.z };
        }
      }
      this.beginManip("rotate", e, floor);
      return;
    }

    const floor = this.floorHit(e.clientX, e.clientY);

    if (floor && this.pendingModel) {
      this.placeModel(
        this.pendingModel.id,
        floor.x,
        floor.z,
        this.pendingModel.role || "piece"
      );
      return;
    }

    const meshId = this.meshHit(e.clientX, e.clientY);

    if (meshId) {
      this.selectPiece(meshId, false);
      let grabFloor = floor;
      if (!grabFloor) {
        const mesh = findFurnitureMesh(this.deps.furnitureGroup, meshId);
        if (mesh) {
          const c = meshCenterXZ(mesh);
          grabFloor = { x: c.x, z: c.z };
        }
      }
      if (grabFloor) {
        this.beginManip("move", e, grabFloor);
      } else {
        this.renderPieceList();
      }
      return;
    }

    if (!floor) return;

    this.selectedId = null;
    this.renderPieceList();
    this.clearSelectionVisuals();
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.isActive()) return;

    if (!this.activeManip) {
      if (this.rotateHandleHit(e.clientX, e.clientY)) {
        this.deps.domElement.style.cursor = "grab";
      } else if (this.meshHit(e.clientX, e.clientY)) {
        this.deps.domElement.style.cursor = "grab";
      } else if (this.selectedId) {
        this.deps.domElement.style.cursor = "";
      }
      return;
    }

    if (!this.selectedId) return;
    const hit = this.floorHit(e.clientX, e.clientY);
    if (!hit) return;
    const mesh = findFurnitureMesh(this.deps.furnitureGroup, this.selectedId);
    if (!mesh) return;

    if (this.activeManip === "move" && this.dragGrabOffset) {
      const st = this.deps.getRoomState();
      const target = clampToRoom(
        hit.x + this.dragGrabOffset.x,
        hit.z + this.dragGrabOffset.z,
        st.width_m,
        st.length_m
      );
      this.applyMoveImmediate(this.selectedId, target.x, target.z, mesh);
      e.preventDefault();
    } else if (
      this.activeManip === "rotate" &&
      this.rotateStartAngle !== null &&
      this.rotateStartOrient !== null
    ) {
      const c = meshCenterXZ(mesh);
      const pointerAngle = Math.atan2(hit.z - c.z, hit.x - c.x);
      const orient = orientationFromDragDelta(
        this.rotateStartOrient,
        this.rotateStartAngle,
        pointerAngle
      );
      this.applyRotateImmediate(this.selectedId, orient, mesh);
      e.preventDefault();
    }
  }

  private onPointerUp(e: PointerEvent): void {
    if (!this.isActive()) return;
    if (!this.activeManip) return;
    if (this.deps.domElement.hasPointerCapture(e.pointerId)) {
      this.deps.domElement.releasePointerCapture(e.pointerId);
    }
    this.endManip();
  }

  private addRow(): void {
    const id = nextPlacementId("piece", this.placements);
    const n = this.placements.length + 1;
    this.placements.push({
      id,
      model_id: "sideTable",
      placement_order: n,
      center_x_m: 1,
      center_z_m: 1,
      orientation: 0,
      relative_to: null,
      on_surface_of: null,
    });
    this.selectedId = id;
    this.renderPieceList();
    this.queueAppendMeshes();
  }

  private queuePreview(task: () => Promise<void>): void {
    this.previewQueue = this.previewQueue.then(task).catch((err) => {
      console.error("Golden preview error", err);
    });
  }

  private applyDraftFromPreview(draft?: { placements: DraftPlacement[] }): void {
    if (!draft?.placements?.length) return;
    const byId = new Map(draft.placements.map((p) => [p.id, p]));
    let changed = false;
    for (const row of this.placements) {
      const linked = byId.get(row.id);
      if (!linked) continue;
      if (linked.on_surface_of !== row.on_surface_of) {
        row.on_surface_of = linked.on_surface_of ?? null;
        changed = true;
      }
    }
    if (changed) this.renderPieceList();
  }

  private sceneFurnitureIds(): Set<string> {
    const ids = new Set<string>();
    this.deps.furnitureGroup.traverse((o) => {
      const fid = o.userData?.furniture_id as string | undefined;
      if (fid) ids.add(localFurnitureId(fid));
    });
    return ids;
  }

  private async appendMissingMeshes(): Promise<void> {
    if (this.placements.length === 0) {
      await this.runFullPreview();
      return;
    }
    const gen = ++this.previewGen;
    const body = this.draftPayload();
    try {
      const res = await previewGoldenDraft(body);
      if (gen !== this.previewGen) return;
      const inScene = this.sceneFurnitureIds();
      let added = 0;
      for (const p of res.placements) {
        const id = localFurnitureId(p.furniture_id);
        if (inScene.has(id)) continue;
        const model = await buildPlacementMesh(p, body.width_m, body.length_m);
        if (gen !== this.previewGen) return;
        this.deps.furnitureGroup.add(model);
        inScene.add(id);
        added++;
      }
      if (gen !== this.previewGen) return;
      this.applyDraftFromPreview(res.draft);
      if (added > 0) {
        this.updateSelectionVisuals();
      }
      const stacked = this.placements.filter((p) => p.on_surface_of).length;
      const stackNote = stacked > 0 ? `, ${stacked} stacked` : "";
      setStatus(
        this.deps.ui,
        `${inScene.size} piece(s) in 3D (${this.placements.length} in layout${stackNote})`
      );
    } catch (err) {
      if (gen === this.previewGen) {
        setStatus(this.deps.ui, `Preview failed: ${err}`);
      }
    }
  }

  private queueAppendMeshes(): void {
    this.queuePreview(() => this.appendMissingMeshes());
  }

  /** Rebuild in-scene meshes from draft so Kenney yaw matches orientation 0–3. */
  private async syncSceneMeshesFromDraft(): Promise<void> {
    if (this.placements.length === 0) return;
    const gen = ++this.previewGen;
    const body = this.draftPayload();
    try {
      const res = await previewGoldenDraft(body);
      if (gen !== this.previewGen) return;
      const byId = new Map(
        res.placements.map((p) => [localFurnitureId(p.furniture_id), p])
      );
      for (const row of this.placements) {
        const kp = byId.get(row.id);
        if (!kp) continue;
        const old = findFurnitureMesh(this.deps.furnitureGroup, row.id);
        if (!old) continue;
        const fresh = await buildPlacementMesh(kp, body.width_m, body.length_m);
        if (gen !== this.previewGen) return;
        this.deps.furnitureGroup.remove(old);
        this.deps.furnitureGroup.add(fresh);
      }
      if (gen !== this.previewGen) return;
      this.applyDraftFromPreview(res.draft);
      this.updateSelectionVisuals();
    } catch (err) {
      if (gen === this.previewGen) {
        setStatus(this.deps.ui, `Sync rotation failed: ${err}`);
      }
    }
  }

  private queueSyncMeshes(): void {
    this.queuePreview(() => this.syncSceneMeshesFromDraft());
  }

  private schedulePreview(): void {
    if (this.previewTimer) clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => this.preview(), 320);
  }

  private clearHighlight(): void {
    if (this.highlight) {
      this.deps.scene.remove(this.highlight);
      this.highlight = null;
    }
  }

  private updateHighlight(mesh: THREE.Object3D): void {
    this.clearHighlight();
    this.highlight = new BoxHelper(mesh, 0x44aaff);
    this.deps.scene.add(this.highlight);
  }

  private renderPieceList(): void {
    const wrap = this.el<HTMLDivElement>("golden-table-wrap");
    if (this.placements.length === 0) {
      wrap.innerHTML =
        '<p class="hint">No placements. Drag from catalog or click model then floor.</p>';
      return;
    }

    let html = '<div class="golden-pieces">';
    for (const p of this.placements) {
      const sel = p.id === this.selectedId ? " selected" : "";
      const isAnchor = p.composition_role === "anchor";
      const zoneOpts = ZONES.map(
        (z) =>
          `<option value="${z}"${p.zone === z || (!p.zone && z === "") ? " selected" : ""}>${z || "—"}</option>`
      ).join("");
      html += `<article class="golden-piece${sel}" data-id="${p.id}">`;
      html += `<div class="golden-piece-head">`;
      html += `<canvas class="golden-thumb" data-model="${p.model_id}" width="48" height="48"></canvas>`;
      html += `<div class="golden-piece-title"><strong>${p.model_id}</strong><span class="muted">${p.id}</span></div>`;
      html += `<button type="button" class="golden-del" data-del="${p.id}" title="Remove">×</button>`;
      html += `</div>`;
      html += `<div class="golden-piece-fields">`;
      html += `<label>id <input data-f="id" value="${p.id}" size="8"/></label>`;
      html += `<label>x <input data-f="center_x_m" type="number" step="0.05" value="${p.center_x_m}" size="4"/></label>`;
      html += `<label>z <input data-f="center_z_m" type="number" step="0.05" value="${p.center_z_m}" size="4"/></label>`;
      html += `<button type="button" class="golden-rot" data-rot="${p.id}" title="Rotate (R)">↻ ${p.orientation}</button>`;
      html += `<label class="golden-anchor"><input type="checkbox" data-f="anchor" ${isAnchor ? "checked" : ""}/> Anchor</label>`;
      html += `<label>zone <select data-f="zone">${zoneOpts}</select></label>`;
      html += `<label>relative_to <input data-f="relative_to" value="${p.relative_to ?? ""}" size="8"/></label>`;
      html += `<label>on_surface <input data-f="on_surface_of" value="${p.on_surface_of ?? ""}" size="8"/></label>`;
      html += `</div></article>`;
    }
    html += "</div>";
    wrap.innerHTML = html;

    wrap.querySelectorAll<HTMLElement>(".golden-piece").forEach((card) => {
      card.addEventListener("click", (ev) => {
        if ((ev.target as HTMLElement).closest("input,select,button")) return;
        const id = card.dataset.id ?? null;
        if (id) this.selectPiece(id);
        else {
          this.selectedId = null;
          this.renderPieceList();
          this.clearSelectionVisuals();
        }
      });
      card.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input[data-f],select[data-f]").forEach(
        (inp) => {
          inp.addEventListener("change", () => this.syncCardFromDom(card));
        }
      );
      const del = card.querySelector<HTMLButtonElement>("button[data-del]");
      del?.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this.removePlacement(del.dataset.del!);
      });
      const rot = card.querySelector<HTMLButtonElement>("button[data-rot]");
      rot?.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const p = this.placements.find((x) => x.id === rot.dataset.rot);
        const mesh = p ? findFurnitureMesh(this.deps.furnitureGroup, p.id) : null;
        if (p && mesh) {
          this.applyRotateImmediate(p.id, (p.orientation + 1) % 4, mesh);
          this.renderPieceList();
          this.queueSyncMeshes();
        }
      });
    });

    wrap.querySelectorAll<HTMLCanvasElement>(".golden-thumb").forEach((canvas) => {
      const mid = canvas.dataset.model;
      if (!mid) return;
      getCatalogThumbnail(mid).then((url) => {
        if (!url) return;
        const img = new Image();
        img.onload = () => {
          const ctx = canvas.getContext("2d");
          if (ctx) ctx.drawImage(img, 0, 0, 48, 48);
        };
        img.src = url;
      });
    });
  }

  private syncCardFromDom(card: HTMLElement): void {
    const id = card.dataset.id!;
    const p = this.placements.find((x) => x.id === id);
    if (!p) return;
    const anchorInp = card.querySelector<HTMLInputElement>('input[data-f="anchor"]');
    if (anchorInp) {
      p.composition_role = anchorInp.checked ? "anchor" : "support";
      if (anchorInp.checked) p.relative_to = null;
    }
    card.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input[data-f],select[data-f]").forEach(
      (inp) => {
        const f = (inp as HTMLInputElement).dataset.f!;
        if (f === "anchor") return;
        const v = (inp as HTMLInputElement).value.trim();
        if (f === "center_x_m") p.center_x_m = parseFloat(v) || 0;
        else if (f === "center_z_m") p.center_z_m = parseFloat(v) || 0;
        else if (f === "orientation") p.orientation = parseInt(v, 10) || 0;
        else if (f === "relative_to") p.relative_to = v || null;
        else if (f === "on_surface_of") p.on_surface_of = v || null;
        else if (f === "zone") p.zone = v || null;
        else if (f === "id") p.id = v;
      }
    );
    if (p.id !== id) {
      this.placements = this.placements.map((x) => (x.id === id ? p : x));
      this.selectedId = p.id;
    }
    this.renderPieceList();
    this.schedulePreview();
  }

  private async refreshStorageHint(): Promise<void> {
    const el = document.getElementById("golden-storage-hint");
    if (!el) return;
    try {
      const dir = await getGoldenStorageDir();
      const layouts = await listGoldenLayouts();
      const count = layouts.length;
      el.innerHTML =
        `Saved layouts: <code>${dir}/</code> — ${count} file${count === 1 ? "" : "s"} on disk (one <code>.json</code> per Golden ID)`;
    } catch {
      /* keep default hint */
    }
  }

  private async suggestGoldenId(existing?: { id: string }[]): Promise<string> {
    const roomType = this.el<HTMLSelectElement>("golden-room-type").value;
    const st = this.deps.getRoomState();
    const base = `${roomType}_${formatDim(st.width_m)}x${formatDim(st.length_m)}`;
    const layouts = existing ?? (await listGoldenLayouts());
    const used = new Set(layouts.map((g) => g.id));
    return nextUniqueGoldenId(base, used);
  }

  private async beginNewLayout(): Promise<void> {
    this.loadedGoldenId = null;
    this.placements = [];
    this.selectedId = null;
    this.previewGen++;
    clearPlacementOverlay(this.deps.scene);
    while (this.deps.furnitureGroup.children.length) {
      this.deps.furnitureGroup.remove(this.deps.furnitureGroup.children[0]);
    }
    this.clearSelectionVisuals();
    const id = await this.suggestGoldenId();
    this.el<HTMLInputElement>("golden-id").value = id;
    this.el<HTMLInputElement>("golden-label").value = id.replace(/_/g, " ");
    this.renderPieceList();
    setStatus(this.deps.ui, `New layout — will save as ${id}`);
  }

  async refreshLoadList(selectedId?: string): Promise<void> {
    const sel = this.el<HTMLSelectElement>("golden-load-select");
    const layouts = await listGoldenLayouts();
    layouts.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
    const current = selectedId ?? sel.value;
    sel.innerHTML = '<option value="">— new —</option>';
    for (const g of layouts) {
      const opt = document.createElement("option");
      opt.value = g.id;
      const fs = g.few_shot ? " ★" : "";
      opt.textContent = `${g.label}${fs} [${g.room_type}] ${g.width_m}×${g.length_m}`;
      sel.appendChild(opt);
    }
    if (current) sel.value = current;
  }

  async loadGolden(id: string): Promise<void> {
    const rec = await getGoldenLayout(id);
    this.loadedGoldenId = rec.id;
    this.placements = [...rec.draft.placements];
    this.el<HTMLInputElement>("golden-id").value = rec.id;
    this.el<HTMLInputElement>("golden-label").value = rec.label;
    this.el<HTMLSelectElement>("golden-room-type").value = rec.room_type;
    const fewShot = this.el<HTMLInputElement>("golden-few-shot");
    if (fewShot) fewShot.checked = rec.few_shot !== false;
    this.deps.editor.setDimensions(rec.width_m, rec.length_m);
    const st = this.deps.getRoomState();
    st.width_m = rec.width_m;
    st.length_m = rec.length_m;
    if (rec.architecture) st.architecture = rec.architecture;
    this.deps.setRoomState(st);
    this.updateDimLabels();
    this.renderPieceList();
    await this.preview();
    setStatus(this.deps.ui, `Loaded golden ${id}`);
  }

  async preview(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.queuePreview(async () => {
        try {
          await this.runFullPreview();
          resolve();
        } catch (e) {
          reject(e);
        }
      });
    });
  }

  private async runFullPreview(): Promise<void> {
    if (this.previewTimer) {
      clearTimeout(this.previewTimer);
      this.previewTimer = null;
    }
    if (this.placements.length === 0) {
      this.previewGen++;
      clearPlacementOverlay(this.deps.scene);
      while (this.deps.furnitureGroup.children.length) {
        this.deps.furnitureGroup.remove(this.deps.furnitureGroup.children[0]);
      }
      this.clearSelectionVisuals();
      return;
    }
    const gen = ++this.previewGen;
    this.clearSelectionVisuals();
    clearPlacementOverlay(this.deps.scene);
    const body = this.draftPayload();
    try {
      const res = await previewGoldenDraft(body);
      if (gen !== this.previewGen) return;
      this.applyDraftFromPreview(res.draft);
      const applied = await loadPlacements(
        this.deps.furnitureGroup,
        res.placements,
        undefined,
        {
          room_width_m: body.width_m,
          room_length_m: body.length_m,
          isStale: () => gen !== this.previewGen,
        }
      );
      if (!applied || gen !== this.previewGen) return;
      this.updateSelectionVisuals();
      setStatus(
        this.deps.ui,
        `${res.placements.length} piece(s) in 3D (${this.placements.length} in layout)`
      );
    } catch (err) {
      if (gen === this.previewGen) {
        setStatus(this.deps.ui, `Preview failed: ${err}`);
      }
    }
  }

  async validate(): Promise<void> {
    const body = this.draftPayload();
    const res = await validateGoldenDraft(body);
    this.placements = res.draft.placements as DraftPlacement[];
    this.renderPieceList();
    if (res.valid) {
      const notes = res.errors.filter((e) => e.trim().length > 0);
      if (notes.length > 0) {
        setStatus(
          this.deps.ui,
          `Validation passed (${notes.length} note(s)).\n${notes.join("\n")}`
        );
      } else {
        setStatus(this.deps.ui, "Validation passed.");
      }
      this.queuePreview(() => this.runFullPreview());
    } else {
      const blocking =
        res.blocking_errors && res.blocking_errors.length > 0
          ? res.blocking_errors
          : res.errors;
      setStatus(this.deps.ui, `Validation failed:\n${blocking.join("\n")}`);
    }
  }

  async save(): Promise<void> {
    const body = this.draftPayload();
    let id = this.el<HTMLInputElement>("golden-id").value.trim() || "golden";
    let label = this.el<HTMLInputElement>("golden-label").value.trim() || id;
    const few_shot = this.el<HTMLInputElement>("golden-few-shot")?.checked ?? true;
    const existing = await listGoldenLayouts();
    const used = new Set(existing.map((g) => g.id));
    const exists = used.has(id);
    const updating = exists && this.loadedGoldenId === id;
    if (exists && !updating) {
      const prevId = id;
      id = nextUniqueGoldenId(id, used);
      this.el<HTMLInputElement>("golden-id").value = id;
      if (label === prevId || label === prevId.replace(/_/g, " ")) {
        label = id.replace(/_/g, " ");
        this.el<HTMLInputElement>("golden-label").value = label;
      }
    }
    await saveGoldenLayout({
      id,
      label,
      room_type: body.room_type,
      width_m: body.width_m,
      length_m: body.length_m,
      architecture: body.architecture,
      few_shot,
      draft: body.draft,
    });
    this.loadedGoldenId = id;
    await this.refreshLoadList(id);
    await this.refreshStorageHint();
    const dir = await getGoldenStorageDir();
    const note = updating
      ? `Updated ${dir}/${id}.json`
      : `Saved new file ${dir}/${id}.json`;
    setStatus(this.deps.ui, note);
  }
}
