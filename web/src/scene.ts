import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface SceneContext {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  furnitureGroup: THREE.Group;
  start: () => void;
  stop: () => void;
}

export function createScene(
  container: HTMLElement,
  options?: { animate?: boolean }
): SceneContext {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a1a22);

  const camera = new THREE.PerspectiveCamera(
    50,
    container.clientWidth / container.clientHeight,
    0.1,
    200
  );
  camera.position.set(6, 8, 6);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  setOrbitTarget(controls, camera, 4, 3.5);

  scene.add(new THREE.AmbientLight(0xffffff, 0.55));
  const dir = new THREE.DirectionalLight(0xffffff, 0.85);
  dir.position.set(5, 12, 8);
  dir.castShadow = true;
  scene.add(dir);

  const grid = new THREE.GridHelper(20, 40, 0x444455, 0x333340);
  scene.add(grid);

  const furnitureGroup = new THREE.Group();
  furnitureGroup.name = "furniture";
  scene.add(furnitureGroup);

  const onResize = () => {
    const w = container.clientWidth;
    const h = container.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  };
  window.addEventListener("resize", onResize);

  let running = options?.animate !== false;
  let frameId = 0;

  function animate(): void {
    if (!running) return;
    frameId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }

  const start = (): void => {
    if (running) return;
    running = true;
    animate();
  };

  const stop = (): void => {
    running = false;
    cancelAnimationFrame(frameId);
  };

  if (running) animate();

  return { renderer, scene, camera, controls, furnitureGroup, start, stop };
}

export function setOrbitTarget(
  controls: OrbitControls,
  camera: THREE.PerspectiveCamera,
  width_m: number,
  length_m: number
): void {
  const tx = width_m / 2;
  const tz = length_m / 2;
  controls.target.set(tx, 0, tz);
  const dist = Math.max(width_m, length_m) * 1.4 + 2;
  camera.position.set(tx + dist * 0.6, dist * 0.7, tz + dist * 0.6);
  controls.update();
}

const WALL_HEIGHT = 2.4;

/** Simple room floor + walls for preference A/B panes. */
export function setRoomShell(
  group: THREE.Group,
  width_m: number,
  length_m: number
): void {
  while (group.children.length) {
    const child = group.children[0];
    group.remove(child);
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      const m = child.material;
      if (Array.isArray(m)) m.forEach((x) => x.dispose());
      else m.dispose();
    }
  }

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(width_m, length_m),
    new THREE.MeshStandardMaterial({ color: 0x2e2e3a })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(width_m / 2, 0, length_m / 2);
  floor.receiveShadow = true;
  group.add(floor);

  const wallMat = new THREE.MeshStandardMaterial({
    color: 0x4a4a58,
    transparent: true,
    opacity: 0.35,
  });
  const t = 0.08;
  const walls: [number, number, number, number, number, number][] = [
    [width_m / 2, WALL_HEIGHT / 2, -t / 2, width_m, WALL_HEIGHT, t],
    [width_m / 2, WALL_HEIGHT / 2, length_m + t / 2, width_m, WALL_HEIGHT, t],
    [-t / 2, WALL_HEIGHT / 2, length_m / 2, t, WALL_HEIGHT, length_m],
    [width_m + t / 2, WALL_HEIGHT / 2, length_m / 2, t, WALL_HEIGHT, length_m],
  ];
  for (const [x, y, z, w, h, d] of walls) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMat);
    m.position.set(x, y, z);
    group.add(m);
  }
}
