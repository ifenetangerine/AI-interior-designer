export interface RoomArchitecture {
  door_wall: "south" | "west" | "east" | "north";
  door_offset_m: number;
  door_width_m: number;
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
  layout_draft?: Record<string, unknown> | null;
  placement_mode?: string;
  errors: string[];
}

export interface CatalogAsset {
  id: string;
  role: string;
  category: string;
  rooms: string[];
  width_m: number;
  depth_m: number;
  height_m?: number;
}

export interface CatalogResponse {
  assets: CatalogAsset[];
  category_defaults?: Record<string, string>;
}

export async function fetchCatalog(): Promise<CatalogResponse> {
  const res = await fetch("/api/catalog");
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return {
    assets: (data.assets ?? []).map((a: CatalogAsset) => ({
      id: a.id,
      role: a.role ?? "decor",
      category: a.category ?? "misc",
      rooms: a.rooms ?? [],
      width_m: a.width_m,
      depth_m: a.depth_m,
      height_m: a.height_m,
    })),
    category_defaults: data.category_defaults,
  };
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

export interface DraftPlacement {
  id: string;
  model_id: string;
  placement_order: number;
  center_x_m: number;
  center_z_m: number;
  orientation: number;
  relative_to?: string | null;
  on_surface_of?: string | null;
  composition_role?: string | null;
  zone?: string | null;
  note?: string | null;
}

export interface GoldenLayoutRecord {
  id: string;
  label: string;
  room_type: string;
  width_m: number;
  length_m: number;
  few_shot?: boolean;
  architecture?: RoomArchitecture | null;
  draft: {
    room_id: string;
    room_type: string;
    placements: DraftPlacement[];
    weights?: Record<string, number>;
  };
}

export interface GoldenLayoutSummary {
  id: string;
  label: string;
  room_type: string;
  width_m: number;
  length_m: number;
  few_shot?: boolean;
  updated_at?: string;
}

export async function listGoldenLayouts(
  roomType?: string
): Promise<GoldenLayoutSummary[]> {
  const q = roomType ? `?room_type=${encodeURIComponent(roomType)}` : "";
  const res = await fetch(`/api/golden-layouts${q}`);
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return data.layouts ?? [];
}

export async function getGoldenStorageDir(): Promise<string> {
  const res = await fetch("/api/golden-layouts");
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return (data.storage_dir as string) ?? "data/golden_layouts";
}

export async function getGoldenLayout(id: string): Promise<GoldenLayoutRecord> {
  const res = await fetch(`/api/golden-layouts/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function saveGoldenLayout(
  body: GoldenLayoutRecord
): Promise<GoldenLayoutRecord> {
  const res = await fetch("/api/golden-layouts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      id: body.id,
      label: body.label,
      room_type: body.room_type,
      width_m: body.width_m,
      length_m: body.length_m,
      architecture: body.architecture,
      few_shot: body.few_shot ?? true,
      draft: body.draft,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function validateGoldenDraft(body: {
  room_type: string;
  width_m: number;
  length_m: number;
  draft: GoldenLayoutRecord["draft"];
}): Promise<{
  valid: boolean;
  errors: string[];
  blocking_errors?: string[];
  draft: GoldenLayoutRecord["draft"];
}> {
  const res = await fetch("/api/golden-layouts/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function previewGoldenDraft(body: {
  room_type: string;
  width_m: number;
  length_m: number;
  architecture?: RoomArchitecture | null;
  draft: GoldenLayoutRecord["draft"];
}): Promise<{
  placements: KenneyPlacement[];
  layout: Record<string, unknown>;
  draft?: GoldenLayoutRecord["draft"];
}> {
  const res = await fetch("/api/golden-layouts/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface PreferencePairResponse {
  design_id: string;
  room_type: string;
  width_m: number;
  length_m: number;
  theta_A: Record<string, number>;
  theta_B: Record<string, number>;
  features_A: Record<string, number>;
  features_B: Record<string, number>;
  placements_A: KenneyPlacement[];
  placements_B: KenneyPlacement[];
  comparison_count: number;
  phase: string;
  picks_on_design: number;
  picks_until_rotation: number;
  fresh_llm: boolean;
}

export async function generatePreferencePair(
  roomType: string,
  options?: { timeLimitS?: number }
): Promise<PreferencePairResponse> {
  const body: Record<string, string | number> = { room_type: roomType };
  if (options?.timeLimitS != null) body.time_limit_s = options.timeLimitS;
  const res = await fetch("/api/preference/pair", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function submitPreferenceCompare(body: {
  design_id: string;
  theta_A: Record<string, number>;
  theta_B: Record<string, number>;
  winner: "A" | "B" | "tie";
  features_A: Record<string, number>;
  features_B: Record<string, number>;
}): Promise<{
  design_id: string;
  comparison_count: number;
  phase: string;
  top_deltas: { key: string; delta: number }[];
  picks_on_design: number;
  picks_until_rotation: number;
}> {
  const res = await fetch("/api/preference/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPreferenceState(roomType: string): Promise<{
  comparison_count: number;
  phase: string;
  top_deltas: { key: string; delta: number }[];
  design_id: string | null;
  width_m: number | null;
  length_m: number | null;
  picks_on_design: number;
  picks_until_rotation: number;
}> {
  const res = await fetch(
    `/api/preference/state?room_type=${encodeURIComponent(roomType)}`
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportLearnedYaml(roomType: string): Promise<{
  theta_path: string;
  constraints_path: string;
}> {
  const res = await fetch("/api/preference/export-yaml", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room_type: roomType }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
