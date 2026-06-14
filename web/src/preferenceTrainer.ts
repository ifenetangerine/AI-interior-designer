import {
  generatePreferencePair,
  submitPreferenceCompare,
  getPreferenceState,
  exportLearnedYaml,
  type PreferencePairResponse,
} from "./api";
import type { DualPreferenceView } from "./preferenceView";
import { setStatus, type UIElements } from "./ui";

const PICKS_PER_DESIGN = 7;

export interface PreferenceTrainerDeps {
  ui: UIElements;
  prefView: DualPreferenceView;
}

export class PreferenceTrainerPanel {
  private pair: PreferencePairResponse | null = null;
  private picking = false;
  private generating = false;

  constructor(private deps: PreferenceTrainerDeps) {
    this.bindDom();
  }

  private el<T extends HTMLElement>(id: string): T {
    return document.getElementById(id) as T;
  }

  private bindDom(): void {
    this.el<HTMLSelectElement>("pref-room-type").addEventListener("change", () =>
      this.onRoomTypeChange()
    );
    this.el<HTMLButtonElement>("btn-pref-pick-a").addEventListener("click", () =>
      void this.submitWinner("A")
    );
    this.el<HTMLButtonElement>("btn-pref-pick-b").addEventListener("click", () =>
      void this.submitWinner("B")
    );
    this.el<HTMLButtonElement>("btn-pref-tie").addEventListener("click", () =>
      void this.submitWinner("tie")
    );
    this.el<HTMLButtonElement>("btn-pref-export").addEventListener("click", () =>
      void this.exportYaml()
    );
  }

  activate(): void {
    document.body.classList.add("pref-mode");
    this.deps.prefView.show();
    void this.onRoomTypeChange();
  }

  deactivate(): void {
    document.body.classList.remove("pref-mode");
    this.deps.prefView.hide();
    this.pair = null;
    this.deps.prefView.clear();
  }

  private currentRoomType(): string {
    return this.el<HTMLSelectElement>("pref-room-type").value || "bedroom";
  }

  private setPickButtonsEnabled(on: boolean): void {
    for (const id of ["btn-pref-pick-a", "btn-pref-pick-b", "btn-pref-tie"]) {
      (this.el<HTMLButtonElement>(id)).disabled = !on;
    }
  }

  private async onRoomTypeChange(): Promise<void> {
    const roomType = this.currentRoomType();
    await this.refreshState(roomType);
    await this.generatePair();
  }

  private async refreshState(roomType: string): Promise<void> {
    const st = await getPreferenceState(roomType);
    this.el<HTMLParagraphElement>("pref-phase-info").textContent =
      `Phase ${st.phase} — ${st.comparison_count} / 100 comparisons`;
    const deltas = st.top_deltas
      .map((d) => `${d.key}: ${d.delta >= 0 ? "+" : ""}${d.delta.toFixed(2)}`)
      .join("\n");
    this.el<HTMLPreElement>("pref-theta-deltas").textContent =
      deltas || "(no θ deltas yet)";
  }

  private async generatePair(): Promise<void> {
    if (this.generating) return;
    const roomType = this.currentRoomType();
    this.generating = true;
    this.setPickButtonsEnabled(false);
    this.pair = null;
    this.deps.prefView.clear();
    setStatus(
      this.deps.ui,
      "Loading next A/B pair (LLM + IP solve may take ~10–20s)…"
    );
    try {
      this.pair = await generatePreferencePair(roomType, { timeLimitS: 8 });
      const {
        width_m,
        length_m,
        design_id,
        picks_on_design,
        fresh_llm,
      } = this.pair;
      this.deps.prefView.setRoomDimensions(width_m, length_m);
      await this.deps.prefView.showPair(
        this.pair.placements_A,
        this.pair.placements_B
      );
      const pickNum = picks_on_design + 1;
      this.el<HTMLParagraphElement>("pref-room-info").textContent =
        `${width_m}×${length_m} m — pick ${pickNum}/${PICKS_PER_DESIGN} on this layout`;
      await this.refreshState(roomType);
      setStatus(
        this.deps.ui,
        fresh_llm
          ? `New room from LLM (${design_id}). Compare A (left) vs B (right).`
          : `Compare A (left) vs B (right), then pick a winner.`
      );
      this.setPickButtonsEnabled(true);
    } catch (e) {
      setStatus(this.deps.ui, `Error: ${e}`);
      this.setPickButtonsEnabled(false);
    } finally {
      this.generating = false;
    }
  }

  private async submitWinner(winner: "A" | "B" | "tie"): Promise<void> {
    if (!this.pair || this.picking || this.generating) return;
    this.picking = true;
    this.setPickButtonsEnabled(false);
    const roomType = this.pair.room_type;
    const designId = this.pair.design_id;
    try {
      const res = await submitPreferenceCompare({
        design_id: designId,
        theta_A: this.pair.theta_A,
        theta_B: this.pair.theta_B,
        winner,
        features_A: this.pair.features_A,
        features_B: this.pair.features_B,
      });
      this.pair = null;
      await this.refreshState(roomType);
      const rotateSoon =
        res.picks_until_rotation === 0
          ? " Next pair will use a new random room."
          : "";
      setStatus(
        this.deps.ui,
        `Recorded ${winner}. (${res.comparison_count} / 100)${rotateSoon}`
      );
      await this.generatePair();
    } catch (e) {
      setStatus(this.deps.ui, `Error: ${e}`);
      this.setPickButtonsEnabled(!!this.pair);
    } finally {
      this.picking = false;
    }
  }

  private async exportYaml(): Promise<void> {
    const roomType = this.currentRoomType();
    const res = await exportLearnedYaml(roomType);
    setStatus(
      this.deps.ui,
      `Exported θ → ${res.theta_path} and constraints → ${res.constraints_path}`
    );
  }
}
