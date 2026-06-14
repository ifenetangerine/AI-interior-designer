import * as THREE from "three";
import { loadKenneyById } from "./kenneyLoad";

const cache = new Map<string, string>();
const pending = new Map<string, Promise<string>>();

/** Single offscreen renderer — avoid exhausting browser WebGL context limit. */
let sharedRenderer: THREE.WebGLRenderer | null = null;

function getSharedRenderer(): THREE.WebGLRenderer {
  if (!sharedRenderer) {
    sharedRenderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    });
  }
  return sharedRenderer;
}

const queue: Array<() => Promise<void>> = [];
let queueRunning = false;

function enqueue<T>(fn: () => Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    queue.push(async () => {
      try {
        resolve(await fn());
      } catch (e) {
        reject(e);
      }
    });
    drainQueue();
  });
}

async function drainQueue(): Promise<void> {
  if (queueRunning) return;
  queueRunning = true;
  while (queue.length > 0) {
    const task = queue.shift()!;
    await task();
  }
  queueRunning = false;
}

function renderThumb(model: THREE.Object3D): string {
  const size = 48;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2a2a36);
  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const dir = new THREE.DirectionalLight(0xffffff, 0.6);
  dir.position.set(2, 4, 3);
  scene.add(dir);

  const clone = model.clone();
  const box = new THREE.Box3().setFromObject(clone);
  const center = new THREE.Vector3();
  box.getCenter(center);
  clone.position.sub(center);
  const span = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(span.x, span.y, span.z, 0.01);
  clone.scale.setScalar(1.2 / maxDim);
  scene.add(clone);

  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 50);
  camera.position.set(1.8, 1.4, 1.8);
  camera.lookAt(0, 0.2, 0);

  const renderer = getSharedRenderer();
  renderer.setSize(size, size, false);
  renderer.render(scene, camera);
  return renderer.domElement.toDataURL("image/png");
}

export function getCatalogThumbnail(modelId: string): Promise<string> {
  const hit = cache.get(modelId);
  if (hit) return Promise.resolve(hit);
  const inflight = pending.get(modelId);
  if (inflight) return inflight;

  const p = enqueue(async () => {
    const model = await loadKenneyById(modelId);
    const url = renderThumb(model);
    cache.set(modelId, url);
    pending.delete(modelId);
    return url;
  }).catch(() => {
    pending.delete(modelId);
    return "";
  });

  pending.set(modelId, p);
  return p;
}
