import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface SceneContext {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  furnitureGroup: THREE.Group;
}

export function createScene(container: HTMLElement): SceneContext {
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

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  return { renderer, scene, camera, controls, furnitureGroup };
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
