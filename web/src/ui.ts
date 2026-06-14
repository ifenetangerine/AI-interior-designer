import type { RoomState } from "./roomEditor";

export interface UIElements {
  roomType: HTMLSelectElement;
  widthLabel: HTMLSpanElement;
  lengthLabel: HTMLSpanElement;
  preferences: HTMLTextAreaElement;
  mockLlm: HTMLInputElement;
  llmOnly: HTMLInputElement;
  anchorDebug: HTMLInputElement;
  anchorDebugPanel: HTMLElement;
  anchorDebugContent: HTMLElement;
  btnRandom: HTMLButtonElement;
  btnRun: HTMLButtonElement;
  status: HTMLPreElement;
}

export function bindUI(): UIElements {
  return {
    roomType: document.getElementById("room-type") as HTMLSelectElement,
    widthLabel: document.getElementById("width-label") as HTMLSpanElement,
    lengthLabel: document.getElementById("length-label") as HTMLSpanElement,
    preferences: document.getElementById("preferences") as HTMLTextAreaElement,
    mockLlm: document.getElementById("mock-llm") as HTMLInputElement,
    llmOnly: document.getElementById("llm-only") as HTMLInputElement,
    anchorDebug: document.getElementById("anchor-debug") as HTMLInputElement,
    anchorDebugPanel: document.getElementById("anchor-debug-panel") as HTMLElement,
    anchorDebugContent: document.getElementById("anchor-debug-content") as HTMLElement,
    btnRandom: document.getElementById("btn-random") as HTMLButtonElement,
    btnRun: document.getElementById("btn-run") as HTMLButtonElement,
    status: document.getElementById("status") as HTMLPreElement,
  };
}

export function updateDimLabels(ui: UIElements, state: RoomState): void {
  ui.widthLabel.textContent = state.width_m.toFixed(1);
  ui.lengthLabel.textContent = state.length_m.toFixed(1);
}

export function setStatus(ui: UIElements, msg: string): void {
  ui.status.textContent = msg;
}

export function setRunning(ui: UIElements, running: boolean): void {
  ui.btnRun.disabled = running;
  ui.btnRandom.disabled = running;
}
