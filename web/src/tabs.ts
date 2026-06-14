export type TabId = "pipeline" | "golden" | "preference";

export function initTabs(onChange: (tab: TabId) => void): void {
  const buttons = document.querySelectorAll<HTMLButtonElement>(".tab-btn");
  const panels = document.querySelectorAll<HTMLElement>(".tab-panel");

  const show = (id: TabId) => {
    buttons.forEach((b) => {
      const active = b.dataset.tab === id;
      b.classList.toggle("active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    panels.forEach((p) => {
      const active = p.id === `tab-${id}`;
      p.classList.toggle("active", active);
      p.hidden = !active;
    });
    onChange(id);
  };

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.tab as TabId;
      if (id) show(id);
    });
  });

  show("pipeline");
}
