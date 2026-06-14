"""Furniture role → anchor relation config and resolver."""

__all__ = [
    "apply_anchor_relation_constraints",
    "get_rules_for_role",
    "load_relation_config",
]


def __getattr__(name: str):
    if name == "apply_anchor_relation_constraints":
        from colayout.relations.apply import apply_anchor_relation_constraints

        return apply_anchor_relation_constraints
    if name == "get_rules_for_role":
        from colayout.relations.loader import get_rules_for_role

        return get_rules_for_role
    if name == "load_relation_config":
        from colayout.relations.loader import load_relation_config

        return load_relation_config
    raise AttributeError(name)
