import * as THREE from "three";
import type { KenneyPlacement } from "./api";

const OVERLAY_GROUP = "placementOverlay";

export function clearPlacementOverlay(scene: THREE.Scene): void {
  const existing = scene.getObjectByName(OVERLAY_GROUP);
  if (existing) {
    scene.remove(existing);
    existing.traverse((o) => {
      if (o instanceof THREE.Line) {
        o.geometry.dispose();
        (o.material as THREE.Material).dispose();
      }
    });
  }
}

export function showPlacementFootprints(
  scene: THREE.Scene,
  placements: KenneyPlacement[]
): void {
  clearPlacementOverlay(scene);
  const group = new THREE.Group();
  group.name = OVERLAY_GROUP;

  for (const p of placements) {
    const [x0, z0, x1, z1] = p.footprint_m;
    const w = x1 - x0;
    const d = z1 - z0;
    const geo = new THREE.PlaneGeometry(w, d);
    geo.rotateX(-Math.PI / 2);
    const fill = new THREE.Mesh(
      geo,
      new THREE.MeshBasicMaterial({
        color: 0x44ff88,
        transparent: true,
        opacity: 0.2,
        depthWrite: false,
      })
    );
    fill.position.set(x0 + w / 2, 0.03, z0 + d / 2);
    group.add(fill);

    const pts = [
      new THREE.Vector3(x0, 0.04, z0),
      new THREE.Vector3(x1, 0.04, z0),
      new THREE.Vector3(x1, 0.04, z1),
      new THREE.Vector3(x0, 0.04, z1),
      new THREE.Vector3(x0, 0.04, z0),
    ];
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x44ff88 })
    );
    group.add(line);
  }

  scene.add(group);
}
