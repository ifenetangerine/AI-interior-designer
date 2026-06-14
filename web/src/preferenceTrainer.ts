import {
  generatePreferencePair,
  submitPreferenceCompare,
  getPreferenceState,
  exportLearnedYaml,
  type PreferencePairResponse,
} from "./api";
import type { DualPreferenceView } from "./preferenceView";
import { setStatus, type UIElements } from "./ui";

export interface PreferenceTrainerDeps {
  ui: UIElements;
  prefView: DualPreferenceView;
}

export class PreferenceTrainerPanel {
  private pair: PreferencePairResponse | null = null;
  private picking = false;
  private generating = false;
  private activeDesignId: string | null = null;

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
    this.activeDesignId = null;
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
    const designHint = this.activeDesignId ?? "cached layout";
    setStatus(
      this.deps.ui,
      `IP-solving A/B on ${designHint} (same frozen LLM draft, ~10–20s)…`
    );
    try {
      this.pair = await generatePreferencePair(roomType, {
        designId: this.activeDesignId ?? undefined,
        timeLimitS: 8,
      });
      const { width_m, length_m, design_id } = this.pair;
      this.activeDesignId = design_id;
      this.deps.prefView.setRoomDimensions(width_m, length_m);
      await this.deps.prefView.showPair(
        this.pair.placements_A,
        this.pair.placements_B
      );
      this.el<HTMLParagraphElement>("pref-room-info").textContent =
        `${design_id} — ${width_m}×${length_m} m (frozen LLM draft, θ variants only)`;
      await this.refreshState(roomType);
      setStatus(
        this.deps.ui,
        `Compare A (left) vs B (right), then pick a winner.`
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
      this.activeDesignId = designId;
      this.pair = null;
      await this.refreshState(roomType);
      setStatus(
        this.deps.ui,
        `Recorded ${winner}. Loading next θ pair on ${designId}… (${res.comparison_count} / 100)`
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
      `Exported ${res.updated_rules} rules to ${res.theta_path}`
    );
  }
}
