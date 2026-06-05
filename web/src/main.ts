import { runPipeline } from "./api";
import { loadPlacements } from "./furnitureLoader";
import { clearPlacementOverlay, showPlacementFootprints } from "./placementOverlay";
import { RoomEditor, defaultArchitecture, randomRoom } from "./roomEditor";
import { createScene, setOrbitTarget } from "./scene";
import { bindUI, setRunning, setStatus, updateDimLabels } from "./ui";

const container = document.getElementById("canvas-container")!;
const ui = bindUI();
const ctx = createScene(container);

let roomState = {
  width_m: 4,
  length_m: 3.5,
  architecture: defaultArchitecture(4, 3.5),
};

const editor = new RoomEditor(
  ctx.scene,
  ctx.camera,
  ctx.renderer.domElement,
  ctx.controls,
  (state) => {
    roomState = state;
    updateDimLabels(ui, state);
    setOrbitTarget(ctx.controls, ctx.camera, state.width_m, state.length_m);
  },
  roomState
);

updateDimLabels(ui, roomState);

ui.btnRandom.addEventListener("click", () => {
  const r = randomRoom();
  ui.roomType.value = r.type;
  editor.setDimensions(r.width_m, r.length_m);
  roomState.architecture = defaultArchitecture(r.width_m, r.length_m, r.type);
  setStatus(ui, `Random: ${r.type} ${r.width_m}×${r.length_m} m`);
});

ui.btnRun.addEventListener("click", async () => {
  setRunning(ui, true);
  clearPlacementOverlay(ctx.scene);
  const llmOnly = ui.llmOnly.checked;
  setStatus(
    ui,
    llmOnly
      ? "Running pipeline (LLM only, no IP)…"
      : "Running pipeline (LLM → IP refine)…"
  );
  try {
    const res = await runPipeline({
      room_id: "viewer_room",
      type: ui.roomType.value,
      width_m: roomState.width_m,
      length_m: roomState.length_m,
      preferences: ui.preferences.value.trim(),
      architecture: roomState.architecture,
      mock_llm: ui.mockLlm.checked,
      placement_mode: llmOnly ? "llm_only" : "llm_refine",
      modulor_cell_m: 0.25,
    });
    const layout = res.layout as {
      furniture?: { id: string }[];
      width_m?: number;
      length_m?: number;
    };
    const n = layout.furniture?.length ?? 0;
    const mode = res.placement_mode ?? (llmOnly ? "llm_only" : "llm_refine");
    const notes = (res.errors as string[] | undefined)?.filter(Boolean) ?? [];
    const noteLine =
      notes.length > 0 ? `\nNotes: ${notes.slice(0, 4).join("; ")}` : "";
    setStatus(
      ui,
      `OK (${mode}) — ${n} pieces placed.\nFurniture: ${layout.furniture?.map((f) => f.id).join(", ")}${noteLine}`
    );
    showPlacementFootprints(ctx.scene, res.placements);
    await loadPlacements(
      ctx.furnitureGroup,
      res.placements,
      (m) => setStatus(ui, m),
      {
        room_width_m: layout.width_m ?? roomState.width_m,
        room_length_m: layout.length_m ?? roomState.length_m,
      }
    );
  } catch (e) {
    setStatus(ui, `Error: ${e}`);
  } finally {
    setRunning(ui, false);
  }
});
