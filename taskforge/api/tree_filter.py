"""Jenkins-compatible Remote API tree filter (?tree=...) parser and filter."""

from __future__ import annotations

from typing import Any


def parse_tree_expression(expr: str) -> dict[str, Any]:
    """Parse a tree expression string like 'id,name,jobs[id,name,steps[name]]' into a nested dict."""
    result: dict[str, Any] = {}
    tokens = []
    depth = 0
    current = []

    for char in expr:
        if char == "[":
            depth += 1
            current.append(char)
        elif char == "]":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        tokens.append("".join(current).strip())

    for token in tokens:
        if not token:
            continue
        if "[" in token and token.endswith("]"):
            key, sub = token.split("[", 1)
            sub = sub[:-1]  # remove trailing ']'
            result[key.strip()] = parse_tree_expression(sub)
        else:
            result[token.strip()] = None

    return result


def filter_with_tree(data: Any, spec: dict[str, Any]) -> Any:
    """Recursively filter data using the parsed tree specification."""
    if data is None:
        return None

    if isinstance(data, list):
        return [filter_with_tree(item, spec) for item in data]

    if isinstance(data, dict):
        filtered: dict[str, Any] = {}
        for key, subspec in spec.items():
            if key in data:
                if subspec is None:
                    filtered[key] = data[key]
                else:
                    filtered[key] = filter_with_tree(data[key], subspec)
        return filtered

    return data


def apply_tree_filter(data: Any, tree_expr: str | None) -> Any:
    """Apply a Jenkins-style ?tree=... expression filter to data."""
    if not tree_expr or not tree_expr.strip():
        return data
    try:
        spec = parse_tree_expression(tree_expr.strip())
        return filter_with_tree(data, spec)
    except Exception:
        # On malformed tree expression, fallback to full data
        return data
