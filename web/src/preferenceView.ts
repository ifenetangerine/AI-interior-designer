import * as THREE from "three";
import type { KenneyPlacement } from "./api";
import { loadPlacements } from "./furnitureLoader";
import { createScene, setOrbitTarget, setRoomShell } from "./scene";

interface PrefPane {
  container: HTMLElement;
  furnitureGroup: THREE.Group;
  roomGroup: THREE.Group;
  ctx: ReturnType<typeof createScene>;
}

/** Side-by-side A/B viewports — created and animated only while Preference tab is active. */
export class DualPreferenceView {
  private paneA: PrefPane | null = null;
  private paneB: PrefPane | null = null;
  private readonly root: HTMLElement;
  private readonly containerAId: string;
  private readonly containerBId: string;
  private width_m = 4;
  private length_m = 3.5;
  private loadGen = 0;
  private visible = false;

  constructor(rootId: string, containerAId: string, containerBId: string) {
    this.root = document.getElementById(rootId)!;
    this.containerAId = containerAId;
    this.containerBId = containerBId;
    window.addEventListener("resize", () => {
      if (this.visible) this.resize();
    });
  }

  private ensurePanes(): void {
    if (this.paneA && this.paneB) return;
    this.paneA = this.createPane(this.containerAId);
    this.paneB = this.createPane(this.containerBId);
  }

  private createPane(containerId: string): PrefPane {
    const container = document.getElementById(containerId)!;
    const ctx = createScene(container, { animate: false });
    const roomGroup = new THREE.Group();
    roomGroup.name = "room-shell";
    ctx.scene.add(roomGroup);
    return {
      container,
      furnitureGroup: ctx.furnitureGroup,
      roomGroup,
      ctx,
    };
  }

  private panes(): PrefPane[] {
    return [this.paneA, this.paneB].filter((p): p is PrefPane => p !== null);
  }

  show(): void {
    this.ensurePanes();
    this.visible = true;
    this.root.hidden = false;
    for (const pane of this.panes()) pane.ctx.start();
    this.resize();
  }

  hide(): void {
    this.visible = false;
    this.root.hidden = true;
    for (const pane of this.panes()) pane.ctx.stop();
    this.loadGen++;
  }

  private resize(): void {
    for (const pane of this.panes()) {
      const w = pane.container.clientWidth;
      const h = pane.container.clientHeight;
      if (w > 0 && h > 0) {
        pane.ctx.camera.aspect = w / h;
        pane.ctx.camera.updateProjectionMatrix();
        pane.ctx.renderer.setSize(w, h);
      }
    }
  }

  setRoomDimensions(width_m: number, length_m: number): void {
    this.width_m = width_m;
    this.length_m = length_m;
    this.ensurePanes();
    for (const pane of this.panes()) {
      setRoomShell(pane.roomGroup, width_m, length_m);
      setOrbitTarget(pane.ctx.controls, pane.ctx.camera, width_m, length_m);
    }
    if (this.visible) this.resize();
  }

  async showPair(
    placementsA: KenneyPlacement[],
    placementsB: KenneyPlacement[]
  ): Promise<void> {
    this.ensurePanes();
    const gen = ++this.loadGen;
    const stale = () => gen !== this.loadGen;
    const opts = {
      room_width_m: this.width_m,
      room_length_m: this.length_m,
      isStale: stale,
    };
    await Promise.all([
      loadPlacements(this.paneA!.furnitureGroup, placementsA, () => {}, opts),
      loadPlacements(this.paneB!.furnitureGroup, placementsB, () => {}, opts),
    ]);
  }

  clear(): void {
    this.loadGen++;
    for (const pane of this.panes()) {
      while (pane.furnitureGroup.children.length) {
        pane.furnitureGroup.remove(pane.furnitureGroup.children[0]);
      }
    }
  }
}
