"""Strict YAML reading for the config file (CF-012).

Differences from PyYAML's safe loader:

- duplicate mapping keys are an error;
- only YAML 1.2 core scalars are resolved implicitly: ``true``/``false``, decimal integers,
  decimal floats and ``null``. YAML 1.1 forms such as ``yes``, ``on``, ``1:30`` or dates stay
  strings, so a type mismatch is reported instead of silently coerced.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from tokli.config.errors import ConfigError

_BOOL = "tag:yaml.org,2002:bool"
_INT = "tag:yaml.org,2002:int"
_FLOAT = "tag:yaml.org,2002:float"
_TIMESTAMP = "tag:yaml.org,2002:timestamp"


class _StrictLoader(yaml.SafeLoader):
    pass


_StrictLoader.yaml_implicit_resolvers = {
    first: [(tag, rx) for tag, rx in resolvers if tag not in (_BOOL, _INT, _FLOAT, _TIMESTAMP)]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictLoader.add_implicit_resolver(
    _BOOL, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
_StrictLoader.add_implicit_resolver(_INT, re.compile(r"^[-+]?[0-9]+$"), list("-+0123456789"))
_StrictLoader.add_implicit_resolver(
    _FLOAT,
    re.compile(
        r"^[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?$|^[-+]?[0-9]+[eE][-+]?[0-9]+$"
    ),
    list("-+0123456789."),
)


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in result:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        result[key] = loader.construct_object(value_node, deep=True)
    return result


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_strict_yaml(text: str, source: str) -> object:
    """Parse ``text``. Errors name ``source`` and the position."""
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        where = ""
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        if mark is not None:
            where = f" (line {mark.line + 1}, column {mark.column + 1})"
        problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        raise ConfigError(
            cause=f"{source}: invalid YAML{where}: {problem}",
            fix="fix the file; duplicate keys are not allowed",
        ) from exc
