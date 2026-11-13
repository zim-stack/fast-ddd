"""Model adapters: one uniform view over attrs classes and dataclasses.

The rest of the library never calls `attrs.*` or `dataclasses.*` directly. It
asks `adapter_for(cls)` for an adapter and uses only the interface below, so
state and snapshot classes can be declared with either library, and mixed
pairs work.

attrs is an optional dependency: the attrs adapter is registered only when
the attrs package is installed.
"""

import dataclasses
import typing
from dataclasses import dataclass
from functools import cache
from typing import Any, Protocol

from fast_ddd.optional import HAS_ATTRS, require_attrs


@dataclass(frozen=True, slots=True)
class FieldInfo:
    """Library-neutral description of one declared field."""

    name: str  # attribute name on instances
    init_name: str  # keyword accepted by __init__ (attrs strips leading "_")
    init: bool  # whether __init__ accepts it
    has_default: bool  # default value or default factory declared
    annotation: Any  # resolved type hint when possible, else the raw annotation


class ModelAdapter(Protocol):
    label: str  # used in messages, e.g. "a dataclass"
    frozen_hint: str  # how to make a class of this kind frozen

    def matches(self, cls: type) -> bool: ...

    def fields(self, cls: type) -> tuple[FieldInfo, ...]: ...

    def is_frozen(self, cls: type) -> bool: ...

    def definition_issues(self, cls: type) -> list[str]:
        """Library-specific mistakes in the class definition, as field paths."""
        ...


def _hints(cls: type) -> dict[str, Any]:
    try:
        return typing.get_type_hints(cls)
    except Exception:  # unresolved forward references etc.
        return {}


class _DataclassAdapter:
    label = "a dataclass"
    frozen_hint = "frozen=True"

    def matches(self, cls: type) -> bool:
        return dataclasses.is_dataclass(cls)

    def fields(self, cls: type) -> tuple[FieldInfo, ...]:
        hints = _hints(cls)
        return tuple(
            FieldInfo(
                name=f.name,
                init_name=f.name,
                init=f.init,
                has_default=(
                    f.default is not dataclasses.MISSING
                    or f.default_factory is not dataclasses.MISSING
                ),
                annotation=hints.get(f.name, f.type),
            )
            for f in dataclasses.fields(cls)
        )

    def is_frozen(self, cls: type) -> bool:
        return bool(cls.__dataclass_params__.frozen)  # type: ignore[attr-defined]

    def definition_issues(self, cls: type) -> list[str]:
        return []


class _AttrsAdapter:
    label = "an attrs class"
    frozen_hint = "frozen=True"

    def matches(self, cls: type) -> bool:
        return require_attrs().has(cls)

    def fields(self, cls: type) -> tuple[FieldInfo, ...]:
        attrs = require_attrs()
        hints = _hints(cls)
        return tuple(
            FieldInfo(
                name=f.name,
                # `alias` exists since attrs 22.2; older versions strip "_".
                init_name=getattr(f, "alias", None) or f.name.lstrip("_"),
                init=f.init,
                has_default=f.default is not attrs.NOTHING,
                annotation=hints.get(f.name, f.type),
            )
            for f in attrs.fields(cls)
        )

    def is_frozen(self, cls: type) -> bool:
        props = getattr(cls, "__attrs_props__", None)  # attrs >= 25.4
        if props is not None:
            return bool(props.is_frozen)
        return getattr(cls.__setattr__, "__name__", "") == "_frozen_setattrs"

    def definition_issues(self, cls: type) -> list[str]:
        """Detect `dataclasses.field(...)` used inside an attrs class.

        attrs silently stores the raw `dataclasses.Field` object as the
        default value, and the bug only surfaces much later.
        """
        return [
            f"{cls.__name__}.{f.name}"
            for f in require_attrs().fields(cls)
            if isinstance(f.default, dataclasses.Field)
        ]


# The attrs adapter is only instantiated when attrs is installed, so the rest
# of the module never has to check for it.
_ADAPTERS: tuple[ModelAdapter, ...] = (
    (_AttrsAdapter(), _DataclassAdapter()) if HAS_ATTRS else (_DataclassAdapter(),)
)


@cache
def adapter_for(cls: type) -> ModelAdapter | None:
    """Return the adapter for a dataclass or attrs class, or None."""
    if not isinstance(cls, type):
        return None
    for adapter in _ADAPTERS:
        if adapter.matches(cls):
            return adapter
    return None
