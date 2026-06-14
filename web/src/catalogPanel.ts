import { fetchCatalog, type CatalogAsset } from "./api";
import { getCatalogThumbnail } from "./catalogThumbnail";

export interface CatalogPanelUI {
  toggle: HTMLButtonElement;
  panel: HTMLElement;
  close: HTMLButtonElement;
  filter: HTMLInputElement;
  list: HTMLElement;
  count: HTMLSpanElement;
}

export function bindCatalogPanel(): CatalogPanelUI {
  return {
    toggle: document.getElementById("btn-catalog") as HTMLButtonElement,
    panel: document.getElementById("catalog-panel") as HTMLElement,
    close: document.getElementById("catalog-close") as HTMLButtonElement,
    filter: document.getElementById("catalog-filter") as HTMLInputElement,
    list: document.getElementById("catalog-list") as HTMLElement,
    count: document.getElementById("catalog-count") as HTMLSpanElement,
  };
}

function groupByRole(assets: CatalogAsset[]): Map<string, CatalogAsset[]> {
  const map = new Map<string, CatalogAsset[]>();
  for (const a of assets) {
    const role = a.role || "other";
    const bucket = map.get(role) ?? [];
    bucket.push(a);
    map.set(role, bucket);
  }
  return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
}

function renderCatalogList(
  ui: CatalogPanelUI,
  assets: CatalogAsset[],
  query: string,
  onSelect: ((asset: CatalogAsset) => void) | null = null,
  catalogOpen = false
): void {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? assets.filter(
        (a) =>
          a.id.toLowerCase().includes(q) ||
          (a.role || "").toLowerCase().includes(q) ||
          (a.category || "").toLowerCase().includes(q)
      )
    : assets;

  ui.count.textContent = `${filtered.length} models`;
  ui.list.innerHTML = "";

  if (filtered.length === 0) {
    ui.list.innerHTML = '<p class="catalog-empty">No models match filter.</p>';
    return;
  }

  const goldenMode = onSelect !== null && catalogOpen;

  for (const [role, items] of groupByRole(filtered)) {
    const section = document.createElement("section");
    section.className = "catalog-role-group";
    const heading = document.createElement("h3");
    heading.textContent = `${role.replace(/_/g, " ")} (${items.length})`;
    section.appendChild(heading);

    const ul = document.createElement("ul");
    for (const a of items.sort((x, y) => x.id.localeCompare(y.id))) {
      const li = document.createElement("li");
      li.className = "catalog-item";
      if (goldenMode) {
        li.draggable = true;
        li.innerHTML = `<canvas class="catalog-thumb" data-model="${a.id}" width="40" height="40"></canvas>
          <span class="catalog-id">${a.id}</span>
          <span class="catalog-meta">${a.width_m.toFixed(2)}×${a.depth_m.toFixed(2)} m</span>`;
        li.addEventListener("dragstart", (e) => {
          e.dataTransfer?.setData("text/kenney-model", a.id);
          e.dataTransfer!.effectAllowed = "copy";
        });
      } else {
        li.innerHTML = `<span class="catalog-id">${a.id}</span>
          <span class="catalog-meta">${a.width_m.toFixed(2)}×${a.depth_m.toFixed(2)} m</span>`;
      }
      li.title = `category: ${a.category}`;
      if (onSelect) {
        li.style.cursor = "pointer";
        li.addEventListener("click", () => onSelect(a));
      }
      ul.appendChild(li);
    }
    section.appendChild(ul);
    ui.list.appendChild(section);
  }

  if (goldenMode) {
    ui.list.querySelectorAll<HTMLCanvasElement>(".catalog-thumb").forEach((canvas) => {
      const mid = canvas.dataset.model;
      if (!mid) return;
      getCatalogThumbnail(mid).then((url) => {
        if (!url) return;
        const img = new Image();
        img.onload = () => {
          const ctx = canvas.getContext("2d");
          if (ctx) ctx.drawImage(img, 0, 0, 40, 40);
        };
        img.src = url;
      });
    });
  }
}

export type CatalogPanelController = {
  refresh: () => void;
  setOnItemSelect: (cb: ((asset: CatalogAsset) => void) | null) => void;
};

export function wireCatalogPanel(
  ui: CatalogPanelUI,
  getRoomType: () => string,
  onCanvasResize: (catalogOpen: boolean) => void
): CatalogPanelController {
  let allAssets: CatalogAsset[] = [];
  let open = false;
  let onItemSelect: ((asset: CatalogAsset) => void) | null = null;

  const setOpen = (next: boolean) => {
    open = next;
    ui.panel.classList.toggle("open", open);
    ui.panel.setAttribute("aria-hidden", open ? "false" : "true");
    onCanvasResize(open);
    refresh();
  };

  const refresh = () => {
    const placeable = allAssets.filter((a) => a.role !== "excluded");
    renderCatalogList(ui, placeable, ui.filter.value, onItemSelect, open);
  };

  const setOnItemSelect = (cb: ((asset: CatalogAsset) => void) | null) => {
    onItemSelect = cb;
    refresh();
  };

  ui.toggle.addEventListener("click", () => setOpen(!open));
  ui.close.addEventListener("click", () => setOpen(false));
  ui.filter.addEventListener("input", refresh);

  fetchCatalog()
    .then((cat) => {
      allAssets = cat.assets;
      refresh();
    })
    .catch((err) => {
      ui.list.innerHTML = `<p class="catalog-empty">Failed to load catalog: ${err}</p>`;
    });

  return { refresh, setOnItemSelect };
}
