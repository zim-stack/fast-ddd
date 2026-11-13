"""Scenarios executed in a fresh interpreter where ``attrs`` is unavailable.

This module must not import ``attrs`` (directly or through fast_ddd) at
import time that could run before the test harness blocks it. Everything
here runs only when a scenario function is called.
"""

from dataclasses import dataclass, field

from fast_ddd.domain.aggregate import Aggregate
from fast_ddd.domain.entity import (
    Entity,
)
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class LineState(DataclassState[int]):
    sku: str = ""


@dataclass(frozen=True, kw_only=True)
class LineSnapshot(DataclassSnapshot[int]):
    sku: str = ""


class Line(Entity[int, LineSnapshot, LineState]): ...


@dataclass(kw_only=True)
class OrderState(DataclassState[int]):
    lines: list[Line] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class OrderSnapshot(DataclassSnapshot[int]):
    lines: tuple[LineSnapshot, ...] = ()


class Order(Aggregate[int, OrderSnapshot, OrderState]): ...


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def dataclass_only_usage() -> None:
    order = Order(OrderSnapshot(id=1, lines=(LineSnapshot(id=1, sku="a"),)))
    restored = Order(order.to_snapshot())
    assert type(restored._state.lines) is list
    assert restored.to_snapshot().lines[0].sku == "a"
    print("ok")


def attrs_flavor_error() -> None:
    try:
        from fast_ddd.domain.entity import State  # noqa: F401
    except ImportError as exc:
        print(exc)
