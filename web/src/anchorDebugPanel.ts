import type { AnchorDebugPayload } from "./api";

export function clearAnchorDebugPanel(container: HTMLElement): void {
  container.innerHTML = "";
}

export function formatAnchorDebugSummary(debug: AnchorDebugPayload): string {
  const lines = [
    `Anchor debug (${debug.tier} ${debug.room_type}, ${debug.anchor_count} zone(s)):`,
  ];
  for (const a of debug.anchors) {
    const childIds = a.children.map((c) => c.id).join(", ") || "(none)";
    lines.push(
      `  • ${a.id} [${a.role}] ${a.child_count}/${a.min_children} children: ${childIds}`
    );
  }
  return lines.join("\n");
}

export function renderAnchorDebugPanel(
  container: HTMLElement,
  debug: AnchorDebugPayload
): void {
  container.innerHTML = "";

  const summary = document.createElement("p");
  summary.className = "anchor-debug-summary";
  summary.textContent = `${debug.tier} ${debug.room_type} · ${debug.anchor_count} anchor zone(s)`;
  container.appendChild(summary);

  for (const anchor of debug.anchors) {
    const block = document.createElement("div");
    block.className = "anchor-debug-anchor";

    const header = document.createElement("div");
    header.className = "anchor-debug-anchor-header";

    const title = document.createElement("strong");
    title.textContent = anchor.id;
    header.appendChild(title);

    const role = document.createElement("span");
    role.className = "anchor-debug-role";
    role.textContent = anchor.role;
    header.appendChild(role);

    const count = document.createElement("span");
    count.className = "anchor-debug-count";
    const ok = anchor.child_count >= anchor.min_children;
    count.textContent = `${anchor.child_count}/${anchor.min_children} children`;
    count.classList.toggle("ok", ok);
    count.classList.toggle("short", !ok);
    header.appendChild(count);

    block.appendChild(header);

    const meta = document.createElement("p");
    meta.className = "anchor-debug-meta";
    const zone = anchor.zone ? `zone ${anchor.zone}` : "no zone";
    meta.textContent = `${zone} · (${anchor.center_x_m.toFixed(2)}, ${anchor.center_z_m.toFixed(2)}) m`;
    block.appendChild(meta);

    const list = document.createElement("ul");
    list.className = "anchor-debug-children";
    if (anchor.children.length === 0) {
      const empty = document.createElement("li");
      empty.className = "anchor-debug-empty";
      empty.textContent = "(no children)";
      list.appendChild(empty);
    } else {
      for (const child of anchor.children) {
        const item = document.createElement("li");
        const rel = child.relative_to ? ` → ${child.relative_to}` : "";
        item.textContent = `${child.id} [${child.role}]${rel}`;
        const pos = document.createElement("span");
        pos.className = "anchor-debug-pos";
        pos.textContent = `(${child.center_x_m.toFixed(2)}, ${child.center_z_m.toFixed(2)})`;
        item.appendChild(pos);
        list.appendChild(item);
      }
    }
    block.appendChild(list);
    container.appendChild(block);
  }
}
