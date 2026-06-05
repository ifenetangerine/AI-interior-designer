export interface RoomArchitecture {
  door_wall: "south" | "west" | "east" | "north";
  door_offset_m: number;
  door_width_m: number;
  focal_wall: "south" | "west" | "east" | "north" | null;
  focal_center_x_m: number | null;
  focal_center_z_m: number | null;
}

export interface PipelineRunRequest {
  room_id: string;
  type: string;
  width_m: number;
  length_m: number;
  preferences: string;
  architecture?: RoomArchitecture;
  mock_llm: boolean;
  placement_mode?: "llm_refine" | "llm_only" | "ip_full";
  modulor_cell_m?: number;
}

export interface KenneyPlacement {
  furniture_id: string;
  category: string;
  model_id: string;
  obj_url: string;
  mtl_url: string | null;
  position_m: [number, number, number];
  rotation_y_rad: number;
  scale: [number, number, number];
  footprint_m: [number, number, number, number];
  wall_anchor?: string | null;
}

export interface OrientationLabelEntry {
  front_dir: [number, number];
  wall_anchor?: string;
  labeled_at?: string;
}

export interface OrientationLabelsResponse {
  labels: Record<string, OrientationLabelEntry>;
  skipped: string[];
  progress: { total: number; labeled: number; skipped: number; remaining: number };
}

export interface OrientationModelRow {
  id: string;
  role: string;
  category: string;
  width_m: number;
  depth_m: number;
  has_label: boolean;
  skipped: boolean;
}

export async function fetchOrientationLabels(): Promise<OrientationLabelsResponse> {
  const res = await fetch("/api/orientation/labels");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchOrientationModels(): Promise<OrientationModelRow[]> {
  const res = await fetch("/api/orientation/models");
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function saveOrientationLabel(
  modelId: string,
  frontDir: [number, number],
  wallAnchor?: string
): Promise<void> {
  const res = await fetch(`/api/orientation/labels/${encodeURIComponent(modelId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ front_dir: frontDir, wall_anchor: wallAnchor }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function skipOrientationModel(modelId: string): Promise<void> {
  const res = await fetch(`/api/orientation/skip/${encodeURIComponent(modelId)}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function clearOrientationLabel(modelId: string): Promise<void> {
  const res = await fetch(`/api/orientation/labels/${encodeURIComponent(modelId)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

export interface PipelineRunResponse {
  status: string;
  scene_graph: Record<string, unknown>;
  layout: Record<string, unknown>;
  placements: KenneyPlacement[];
  placement_mode?: string;
  errors: string[];
}

export async function runPipeline(
  req: PipelineRunRequest
): Promise<PipelineRunResponse> {
  const res = await fetch("/api/pipeline/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}
