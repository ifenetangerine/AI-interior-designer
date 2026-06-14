# Co-Layout-Inspired Per-Room Furniture Pipeline

Grid-based integer programming for furniture placement inside known rooms (type + dimensions). Each room is optimized independently. By default the LLM **places furniture with explicit positions** (anchor first, then relative pieces in meters); IP **refines** the draft with overlap/bounds as hard constraints and semantic relations as soft penalties. Placements map to Kenney OBJs by `model_id`.

Based on [Co-Layout (arXiv 2511.12474)](https://arxiv.org/abs/2511.12474), adapted without joint floor-plan optimization.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set OPENAI_API_KEY for live LLM
```

## Placement architecture (default: `llm_refine`)

```
Catalog → LLM layout draft (ordered placements in meters)
       → validate + snap to grid hints
       → IP refine (overlap/bounds hard; semantic soft; hint deviation objective)
       → Kenney viewer
```

| Mode | Behavior |
|------|----------|
| `llm_refine` (default) | LLM places → IP refines |
| `llm_only` | LLM places → grid snap only (no IP) |
| `ip_full` | Legacy: scene graph + full IP from scratch |

Set via `PLACEMENT_MODE` env or per-request `placement_mode` on `/api/pipeline/run`. The 3D viewer has an **LLM only (skip IP refine)** checkbox.

Catalog taxonomy: [`config/catalog/kenney_taxonomy.yaml`](config/catalog/kenney_taxonomy.yaml). Rebuild after edits:

```bash
python scripts/build_kenney_catalog.py
```

For each room, the LLM (default path):

1. Receives the **full Kenney catalog** (model ids, roles, footprints) in the prompt
2. Outputs a **layout draft** with `placements[]`: `placement_order`, `center_x_m`, `center_z_m`, `orientation` (0|1)
3. Passes validation (allowed models, bounds, piece counts, ~65% max floor coverage)
4. IP refine nudges pieces only to fix overlap while staying near LLM hints

**Coordinate contract:** origin `(0, 0)` = southwest corner; `center_x_m` east, `center_z_m` north; `orientation` 0 = width along +x, 1 = width along +z (matches IP `rot`).

Mock layouts: [`config/catalog/mock_room_layouts.yaml`](config/catalog/mock_room_layouts.yaml). Legacy mock kits: [`config/catalog/mock_room_kits.yaml`](config/catalog/mock_room_kits.yaml).

**Examples** (in `examples/studio.json` or `--preferences` on CLI):

- `"add desk and chair, remove wardrobe"`
- `"queen bed only, minimal furniture"`
- `"sofa facing TV, extra coffee table"`

**Mock mode** (`--mock-llm`): deterministic catalog kit per room type and density tier (no API).

**Live mode** (`OPENAI_API_KEY` set): OpenAI picks from the catalog; on repeated failure, falls back to the mock kit with a logged warning.

## Usage

Multi-room floor:

```bash
python scripts/run_floor.py --input examples/studio.json --out runs/demo/ --mock-llm
```

Single room with preferences:

```bash
python scripts/run_room.py --type bedroom --width 4 --length 3.5 \
  --preferences "add desk and chair" --out runs/bedroom/
```

Skip scene graph JSON files:

```bash
python scripts/run_floor.py -i examples/studio.json -o runs/demo/ --no-save-scene-graph
```

## Outputs

| File | Description |
|------|-------------|
| `layout.json` | 2D grid placements per room |
| `layout_draft_<room_id>.json` | LLM placement draft with meter centers (pre-refine) |
| `scene_graph_<room_id>.json` | Minimal scene graph derived from draft (for API compat) |
| `layout_<room_id>.png` | Top-down visualization |
| `scene_3d.json` | Matched catalog assets |

## Kenney model orientation

The [Kenney furniture kit](kenney_furniture-kit/) OBJ files do **not** include facing or front-direction metadata—only mesh geometry. The pipeline uses:

- **IP solver**: `rot` 0/1 and bed `against_wall` rules place the headboard edge on the wall ([`constraints.py`](src/colayout/ip/constraints.py)). Other wall pieces use a **one-cell inset** from the room boundary to reduce mesh bleed.
- **Viewer**: meshes are clamped inside their solver footprint and room bounds; storage pieces use **back-on-wall** anchoring when possible.
- **Labels**: manual `front_dir` vectors in [`config/catalog/kenney_orientation_labels.json`](config/catalog/kenney_orientation_labels.json) (see labeler below). Fallback: `asset_orientation` yaw in the catalog ([`orientation.py`](src/colayout/assets/orientation.py)).

### Visual orientation labeler

Label each placeable model’s **front direction** (one at a time; skip allowed):

```bash
python scripts/run_server.py          # port 8000
cd web && npm run dev                 # port 5173
```

Open **http://localhost:5173/labeler.html** (or link from the room viewer). Drag on the floor from the model toward the gold **+X** axis (solver front at `rot=0`). **Save & Next** writes to `kenney_orientation_labels.json`. No catalog rebuild required—rerun the pipeline to see updated facing.

Keyboard: **Enter** save & next, **S** skip, **←** previous.

## Local 3D viewer (Three.js)

Interactive room editor with Kenney OBJ models from [`kenney_furniture-kit/`](kenney_furniture-kit/).

1. Build the Kenney asset catalog (bbox sizes from OBJ files).
2. Start the API server (serves `/api` and `/kenney` static models).
3. Start the Vite dev UI (proxies API to port 8000).

```bash
python scripts/build_kenney_catalog.py
pip install -e ".[web,dev]"
python scripts/run_server.py          # http://localhost:8000
cd web && npm install && npm run dev  # http://localhost:5173
```

In the browser:

- Choose **room type**, **drag the east or north wall** (gold handles) to resize the room.
- Green footprint overlays show solver placement; Kenney models align to those rectangles.
- Enter **preferences** for LLM design (or enable **mock LLM** for offline catalog kits).
- **Random room** — random type and dimensions.
- **Run pipeline** — LLM scene graph → grid IP placement → Kenney models in the scene.

Production UI build (optional): `cd web && npm run build`, then open `http://localhost:8000/app/`.

**Orange boxes** mean the Kenney OBJ failed to load (not the real models). The viewer loads from `kenney_furniture-kit` via `/kenney/*.obj`. Both servers must be running (API on 8000, Vite on 5173) so the dev proxy can fetch models. Check the browser console and the status panel for load errors.

### Golden layout editor + preference training

The 3D viewer has three tabs: **Pipeline**, **Golden editor**, and **Preference**.

**Golden editor** — author few-shot reference layouts with live 3D Kenney models:

1. Set room type and aspect ratio (presets or wall drag).
2. Open **Catalog** — drag a model onto the floor, or click then click the floor.
3. Click furniture in 3D to select; drag to move; **R** or ↻ to rotate.
4. Toggle **Anchor** and set **zone** per piece; edit `relative_to` / `on_surface_of`.
5. Give each layout a **unique Golden ID** (e.g. `bedroom_4x3_5_v2`) — same ID overwrites the previous file.
6. Check **Use as LLM few-shot example** — all saved layouts with this checked (matching room type) feed the planner.
7. **Validate** / **Save golden** → `data/golden_layouts/` (unlimited files; **Load existing** lists all).

**LLM planner** (OpenAI path) — sequential placement with suggested anchors:

1. Few-shot goldens injected into the prompt when available.
2. Step 1: LLM places zone anchors (`composition_role: anchor`).
3. Step 2+: expand each anchor zone with linked children.
4. Anchor roles in YAML are **suggestions**, not hard-coded `placement_order` slots.

**Preference training** — hierarchical θ (~25 params/room: globals + kind bundles + metric targets):

1. Select a saved golden layout.
2. **Generate A/B pair** — block-perturbed θ (global / kind / metric); hints disabled.
3. Toggle **Show A / Show B**, then **Pick A**, **Pick B**, or **Tie**.
4. Phase A nudges `theta_current` (`θ += 0.15 × (θ_winner − θ_loser)`).
5. After 100 comparisons, Phase B fits `R(features)` on expanded layout metrics.
6. **Export learned YAML** writes `config/preference_theta.learned.yaml` and scales `config/furniture_anchor_relations.learned.yaml`.

State: `data/preference/theta_state.json`, `data/preference/comparisons.jsonl`.

## Tests

```bash
pip install -e ".[dev,web]"
pytest
```
