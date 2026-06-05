import * as THREE from "three";
import { MTLLoader } from "three/examples/jsm/loaders/MTLLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";

export const KENNEY_PATH = "/kenney/";
const cache = new Map<string, THREE.Object3D>();

function basename(url: string): string {
  const i = url.lastIndexOf("/");
  return i >= 0 ? url.slice(i + 1) : url;
}

/** Load Kenney OBJ (+ optional MTL). Returns a clone safe to mutate. */
export async function loadKenneyModel(
  objUrl: string,
  mtlUrl: string | null = null
): Promise<THREE.Object3D> {
  const objFile = basename(objUrl);
  const key = mtlUrl ? `${objFile}|${basename(mtlUrl)}` : objFile;
  const cached = cache.get(key);
  if (cached) return cached.clone();

  const objLoader = new OBJLoader();
  objLoader.setPath(KENNEY_PATH);

  if (mtlUrl) {
    const mtlLoader = new MTLLoader();
    mtlLoader.setPath(KENNEY_PATH);
    const materials = await mtlLoader.loadAsync(basename(mtlUrl));
    materials.preload();
    objLoader.setMaterials(materials);
  }

  const obj = await objLoader.loadAsync(objFile);
  obj.traverse((c) => {
    if (c instanceof THREE.Mesh) {
      c.castShadow = true;
      c.receiveShadow = true;
    }
  });
  cache.set(key, obj);
  return obj.clone();
}

export function loadKenneyById(
  modelId: string,
  mtlName: string | null = null
): Promise<THREE.Object3D> {
  const objUrl = `${modelId}.obj`;
  const mtlUrl = mtlName ? `${mtlName}.mtl` : `${modelId}.mtl`;
  return loadKenneyModel(objUrl, mtlUrl);
}
