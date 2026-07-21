from __future__ import annotations

import ast
import re
from types import SimpleNamespace
from typing import Any


class PredicateError(ValueError):
    pass


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def _object(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{str(key): _object(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_object(item) for item in value]
    return value


def _to_python(predicate: str) -> str:
    text = predicate.strip()
    text = text.replace("&&", " and ").replace("||", " or ")
    text = re.sub(r"!(?!=)", " not ", text)
    text = re.sub(r"\btrue\b", "True", text)
    text = re.sub(r"\bfalse\b", "False", text)
    text = re.sub(r"\bnull\b", "None", text)
    return text


def evaluate_predicate(predicate: str, context: dict[str, Any]) -> bool:
    try:
        tree = ast.parse(_to_python(predicate), mode="eval")
    except SyntaxError as exc:
        raise PredicateError("Invalid predicate syntax.") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise PredicateError(f"Unsupported predicate expression: {type(node).__name__}.")

    names = {str(key): _object(value) for key, value in context.items()}
    try:
        return bool(eval(compile(tree, "<predicate>", "eval"), {"__builtins__": {}}, names))
    except Exception as exc:
        raise PredicateError("Predicate could not be evaluated.") from exc
