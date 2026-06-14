import { runPipeline, type AnchorDebugPayload } from "./api";
import {
  clearAnchorDebugPanel,
  renderAnchorDebugPanel,
} from "./anchorDebugPanel";
import { bindCatalogPanel, wireCatalogPanel } from "./catalogPanel";
import { GoldenEditor } from "./goldenEditor";
import { loadPlacements } from "./furnitureLoader";
import { clearPlacementOverlay, showPlacementFootprints } from "./placementOverlay";
import { PreferenceTrainerPanel } from "./preferenceTrainer";
import { DualPreferenceView } from "./preferenceView";
import { RoomEditor, defaultArchitecture, randomRoom } from "./roomEditor";
import { createScene, setOrbitTarget } from "./scene";
import { initTabs, type TabId } from "./tabs";
import { bindUI, setRunning, setStatus, updateDimLabels } from "./ui";

const container = document.getElementById("canvas-container")!;
const ui = bindUI();
const catalogUi = bindCatalogPanel();
const ctx = createScene(container);

const catalog = wireCatalogPanel(
  catalogUi,
  () => {
    const goldenTab = document.getElementById("tab-golden");
    if (goldenTab && !goldenTab.hidden) {
      return (document.getElementById("golden-room-type") as HTMLSelectElement)
        .value;
    }
    return ui.roomType.value;
  },
  (open) => document.body.classList.toggle("catalog-open", open)
);

ui.roomType.addEventListener("change", () => catalog.refresh());

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

const goldenEditor = new GoldenEditor({
  ui,
  editor,
  furnitureGroup: ctx.furnitureGroup,
  scene: ctx.scene,
  camera: ctx.camera,
  domElement: ctx.renderer.domElement,
  controls: ctx.controls,
  catalog,
  getRoomState: () => roomState,
  setRoomState: (s) => {
    roomState = s;
  },
});

const prefView = new DualPreferenceView(
  "pref-view",
  "pref-canvas-a",
  "pref-canvas-b"
);

const preferencePanel = new PreferenceTrainerPanel({
  ui,
  prefView,
});

let lastAnchorDebug: AnchorDebugPayload | null = null;
let activeTab: TabId = "pipeline";

function updateAnchorDebugPanel(): void {
  if (ui.anchorDebug.checked && lastAnchorDebug) {
    renderAnchorDebugPanel(ui.anchorDebugContent, lastAnchorDebug);
    ui.anchorDebugPanel.classList.remove("hidden");
  } else {
    clearAnchorDebugPanel(ui.anchorDebugContent);
    ui.anchorDebugPanel.classList.add("hidden");
  }
}

ui.anchorDebug.addEventListener("change", updateAnchorDebugPanel);

initTabs((tab) => {
  activeTab = tab;
  goldenEditor.deactivate();
  preferencePanel.deactivate();
  if (tab === "preference") {
    ctx.stop();
    preferencePanel.activate();
  } else {
    ctx.start();
    if (tab === "golden") {
      goldenEditor.activate();
      const rt = (document.getElementById("golden-room-type") as HTMLSelectElement)
        .value;
      (document.getElementById("golden-room-type") as HTMLSelectElement).value =
        rt || ui.roomType.value;
    }
  }
});

ui.btnRandom.addEventListener("click", () => {
  const r = randomRoom();
  ui.roomType.value = r.type;
  editor.setDimensions(r.width_m, r.length_m);
  roomState.architecture = defaultArchitecture(r.width_m, r.length_m, r.type);
  setStatus(ui, `Random: ${r.type} ${r.width_m}×${r.length_m} m`);
});

ui.btnRun.addEventListener("click", async () => {
  if (activeTab !== "pipeline") return;
  setRunning(ui, true);
  clearPlacementOverlay(ctx.scene);
  lastAnchorDebug = null;
  clearAnchorDebugPanel(ui.anchorDebugContent);
  ui.anchorDebugPanel.classList.add("hidden");
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
    lastAnchorDebug = res.anchor_debug ?? null;
    updateAnchorDebugPanel();
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
