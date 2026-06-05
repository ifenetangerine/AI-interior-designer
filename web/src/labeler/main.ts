import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  clearOrientationLabel,
  fetchOrientationLabels,
  fetchOrientationModels,
  saveOrientationLabel,
  skipOrientationModel,
  type OrientationModelRow,
} from "../api";
import { loadKenneyById } from "../kenneyLoad";

const container = document.getElementById("canvas-container")!;
const progressEl = document.getElementById("progress")!;
const modelInfoEl = document.getElementById("model-info")!;
const statusEl = document.getElementById("status")!;
const filterEl = document.getElementById("filter") as HTMLSelectElement;
const wallAnchorEl = document.getElementById("wall-anchor") as HTMLSelectElement;
const angleReadoutEl = document.getElementById("angle-readout")!;
const btnPrev = document.getElementById("btn-prev")!;
const btnSkip = document.getElementById("btn-skip")!;
const btnSave = document.getElementById("btn-save")!;
const btnClear = document.getElementById("btn-clear")!;
const btnRotCcw = document.getElementById("btn-rot-ccw")!;
const btnRotCw = document.getElementById("btn-rot-cw")!;

const SNAP_RAD = Math.PI / 4; // 45°

let allModels: OrientationModelRow[] = [];
let queue: OrientationModelRow[] = [];
let queueIndex = 0;
let currentModel: THREE.Object3D | null = null;
let frontDir: THREE.Vector2 | null = null;
let arrowHelper: THREE.ArrowHelper | null = null;
let dragActive = false;
let meshCenter = new THREE.Vector3();

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a22);

const camera = new THREE.PerspectiveCamera(
  50,
  container.clientWidth / container.clientHeight,
  0.1,
  200
);
camera.position.set(3, 4, 3);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.shadowMap.enabled = true;
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 0.5, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const dir = new THREE.DirectionalLight(0xffffff, 0.85);
dir.position.set(4, 8, 6);
dir.castShadow = true;
scene.add(dir);

const grid = new THREE.GridHelper(8, 16, 0x444455, 0x333340);
scene.add(grid);

const axisX = new THREE.ArrowHelper(
  new THREE.Vector3(1, 0, 0),
  new THREE.Vector3(0, 0.02, 0),
  1.2,
  0xe8c060,
  0.15,
  0.08
);
axisX.line.material = new THREE.LineBasicMaterial({ color: 0xe8c060 });
scene.add(axisX);

const modelGroup = new THREE.Group();
scene.add(modelGroup);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

function setStatus(msg: string) {
  statusEl.textContent = msg;
}

function snapFrontDir(dx: number, dz: number): THREE.Vector2 {
  const angle = Math.atan2(dz, dx);
  const snapped = Math.round(angle / SNAP_RAD) * SNAP_RAD;
  return new THREE.Vector2(Math.cos(snapped), Math.sin(snapped));
}

function setFrontDirFromXZ(dx: number, dz: number): void {
  if (dx * dx + dz * dz < 1e-6) return;
  frontDir = snapFrontDir(dx, dz);
  updateAngleReadout();
  updateArrow();
  applyPreviewRotation();
}

function frontDirAngleDeg(): number {
  if (!frontDir) return 0;
  return (Math.atan2(frontDir.y, frontDir.x) * 180) / Math.PI;
}

function updateAngleReadout(): void {
  if (!frontDir) {
    angleReadoutEl.textContent = "Front: —";
    return;
  }
  const deg = Math.round(frontDirAngleDeg());
  const card =
    deg === 0
      ? "east (+X)"
      : deg === 90
        ? "south (+Z)"
        : deg === 180 || deg === -180
          ? "west (−X)"
          : deg === -90 || deg === 270
            ? "north (−Z)"
            : `${deg}°`;
  angleReadoutEl.textContent = `Front: ${card} (45° snap)`;
}

function rotateFrontByQuarterTurn(steps: number): void {
  if (!frontDir) frontDir = new THREE.Vector2(1, 0);
  const angle = Math.atan2(frontDir.y, frontDir.x) + steps * SNAP_RAD;
  const snapped = Math.round(angle / SNAP_RAD) * SNAP_RAD;
  frontDir = new THREE.Vector2(Math.cos(snapped), Math.sin(snapped));
  updateAngleReadout();
  updateArrow();
  applyPreviewRotation();
}

function yawRestDegFromFront(dx: number, dz: number): number {
  const s = snapFrontDir(dx, dz);
  return (Math.atan2(s.y, s.x) * 180) / Math.PI - 90;
}

function defaultWallAnchor(row: OrientationModelRow): string {
  const back = ["counter", "fridge", "wardrobe", "tv_stand", "dresser"];
  return back.includes(row.category) ? "back_center" : "center";
}

function rebuildQueue() {
  const f = filterEl.value;
  queue = allModels.filter((m) => {
    if (f === "unlabeled") return !m.has_label && !m.skipped;
    if (f === "labeled") return m.has_label;
    if (f === "skipped") return m.skipped;
    return true;
  });
  if (queueIndex >= queue.length) queueIndex = Math.max(0, queue.length - 1);
}

async function refreshProgress() {
  const data = await fetchOrientationLabels();
  const p = data.progress;
  progressEl.textContent = `${p.labeled} labeled · ${p.skipped} skipped · ${p.remaining} remaining (${p.total} total)`;
  allModels = await fetchOrientationModels();
  rebuildQueue();
}

function updateArrow() {
  if (arrowHelper) {
    scene.remove(arrowHelper);
    arrowHelper = null;
  }
  if (!frontDir || frontDir.lengthSq() < 1e-6) return;
  const dir3 = new THREE.Vector3(frontDir.x, 0, frontDir.y).normalize();
  arrowHelper = new THREE.ArrowHelper(
    dir3,
    new THREE.Vector3(meshCenter.x, 0.05, meshCenter.z),
    1.0,
    0x44cc88,
    0.12,
    0.06
  );
  scene.add(arrowHelper);
}

function applyPreviewRotation() {
  if (!currentModel || !frontDir) return;
  const yaw = yawRestDegFromFront(frontDir.x, frontDir.y);
  currentModel.rotation.y = (yaw * Math.PI) / 180;
  updateAngleReadout();
}

function pointerOnFloor(clientX: number, clientY: number): THREE.Vector3 | null {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = new THREE.Vector3();
  if (!raycaster.ray.intersectPlane(floorPlane, hit)) return null;
  return hit;
}

async function showModelAt(index: number) {
  if (queue.length === 0) {
    modelInfoEl.textContent = "Queue empty — change filter or label all models.";
    while (modelGroup.children.length) modelGroup.remove(modelGroup.children[0]);
    currentModel = null;
    frontDir = null;
    updateArrow();
    updateAngleReadout();
    return;
  }
  queueIndex = ((index % queue.length) + queue.length) % queue.length;
  const row = queue[queueIndex];
  setStatus(`Loading ${row.id}…`);
  while (modelGroup.children.length) modelGroup.remove(modelGroup.children[0]);
  currentModel = null;
  frontDir = null;

  try {
    const model = await loadKenneyById(row.id);
    const box = new THREE.Box3().setFromObject(model);
    box.getCenter(meshCenter);
    model.position.set(-meshCenter.x, -box.min.y, -meshCenter.z);
    modelGroup.add(model);
    currentModel = model;

    wallAnchorEl.value = defaultWallAnchor(row);
    const labels = await fetchOrientationLabels();
    const existing = labels.labels[row.id];
    if (existing?.front_dir) {
      setFrontDirFromXZ(existing.front_dir[0], existing.front_dir[1]);
      if (existing.wall_anchor) wallAnchorEl.value = existing.wall_anchor;
    } else {
      setFrontDirFromXZ(1, 0);
    }

    modelInfoEl.textContent =
      `${queueIndex + 1} / ${queue.length}\n` +
      `id: ${row.id}\nrole: ${row.role}\ncategory: ${row.category}\n` +
      `bbox: ${row.width_m.toFixed(2)} × ${row.depth_m.toFixed(2)} m`;

    const dist = Math.max(row.width_m, row.depth_m) * 2.5;
    controls.target.set(0, 0.4, 0);
    camera.position.set(dist * 0.8, dist * 0.9, dist * 0.8);
    controls.update();
    setStatus("Drag floor or use ±45° / Q E — front snaps to 45°.");
  } catch (e) {
    setStatus(`Load error: ${e}`);
  }
}

async function saveAndNext() {
  if (!queue.length || !frontDir) return;
  const row = queue[queueIndex];
  const snapped = snapFrontDir(frontDir.x, frontDir.y);
  const fd: [number, number] = [snapped.x, snapped.y];
  setStatus("Saving…");
  await saveOrientationLabel(row.id, fd, wallAnchorEl.value);
  await refreshProgress();
  rebuildQueue();
  if (filterEl.value === "unlabeled") {
    await showModelAt(queueIndex);
  } else {
    await showModelAt(queueIndex + 1);
  }
  await refreshProgress();
}

async function skipCurrent() {
  if (!queue.length) return;
  const row = queue[queueIndex];
  await skipOrientationModel(row.id);
  await refreshProgress();
  rebuildQueue();
  await showModelAt(queueIndex);
}

async function clearCurrent() {
  if (!queue.length) return;
  await clearOrientationLabel(queue[queueIndex].id);
  await refreshProgress();
  rebuildQueue();
  await showModelAt(queueIndex);
}

renderer.domElement.addEventListener("pointerdown", (e) => {
  if (!currentModel) return;
  dragActive = true;
  controls.enabled = false;
});

renderer.domElement.addEventListener("pointermove", (e) => {
  if (!dragActive || !currentModel) return;
  const hit = pointerOnFloor(e.clientX, e.clientY);
  if (!hit) return;
  setFrontDirFromXZ(hit.x - meshCenter.x, hit.z - meshCenter.z);
});

renderer.domElement.addEventListener("pointerup", () => {
  dragActive = false;
  controls.enabled = true;
});

filterEl.addEventListener("change", async () => {
  rebuildQueue();
  queueIndex = 0;
  await showModelAt(0);
});

btnSave.addEventListener("click", () => void saveAndNext());
btnSkip.addEventListener("click", () => void skipCurrent());
btnPrev.addEventListener("click", () => void showModelAt(queueIndex - 1));
btnClear.addEventListener("click", () => void clearCurrent());
btnRotCcw.addEventListener("click", () => rotateFrontByQuarterTurn(-1));
btnRotCw.addEventListener("click", () => rotateFrontByQuarterTurn(1));

window.addEventListener("keydown", (e) => {
  if (
    e.target instanceof HTMLInputElement ||
    e.target instanceof HTMLTextAreaElement ||
    e.target instanceof HTMLSelectElement
  ) {
    return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    void saveAndNext();
  } else if (e.key === "s" || e.key === "S") {
    void skipCurrent();
  } else if (e.key === "ArrowLeft") {
    void showModelAt(queueIndex - 1);
  } else if (e.key === "q" || e.key === "Q") {
    rotateFrontByQuarterTurn(-1);
  } else if (e.key === "e" || e.key === "E") {
    rotateFrontByQuarterTurn(1);
  }
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener("resize", () => {
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
});

(async () => {
  await refreshProgress();
  rebuildQueue();
  await showModelAt(0);
})();
