"""Test helpers for hierarchical zone-prefixed furniture ids."""


def find_furniture(furniture, local_id: str):
    for f in furniture:
        if f.id == local_id or f.id.endswith(f"__{local_id}"):
            return f
    raise StopIteration(f"no furniture with id {local_id!r}")


def find_draft_placement(placements, local_id: str):
    for p in placements:
        if p.id == local_id or p.id.endswith(f"__{local_id}"):
            return p
    raise StopIteration(f"no placement with id {local_id!r}")


def has_stack_pair(on_top: set[tuple[str, str]], child: str, parent: str) -> bool:
    for a, b in on_top:
        if (a == child or a.endswith(f"__{child}")) and (
            b == parent or b.endswith(f"__{parent}")
        ):
            return True
    return False


def graph_has_furniture(graph, local_id: str) -> bool:
    return any(
        f.id == local_id or f.id.endswith(f"__{local_id}") for f in graph.furniture
    )
