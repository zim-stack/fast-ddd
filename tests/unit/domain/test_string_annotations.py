from __future__ import annotations

# With postponed evaluation every annotation is a string. The adapters resolve
# them with typing.get_type_hints, so the container kind is still honored.
from dataclasses import dataclass, field

import attrs

from fast_ddd.domain.entity import (
    Entity,
)
from fast_ddd.domain.flavors.attrs_models import Snapshot, State
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


@dataclass(kw_only=True)
class DcLineState(DataclassState[int]):
    sku: str = ""


@dataclass(frozen=True, kw_only=True)
class DcLineSnapshot(DataclassSnapshot[int]):
    sku: str = ""


class DcLine(Entity[int, DcLineSnapshot, DcLineState]):
    pass


@dataclass(kw_only=True)
class DcBoxState(DataclassState[int]):
    lines: list[DcLine] = field(default_factory=list)
    kinds: set[str] = field(default_factory=set)


@dataclass(frozen=True, kw_only=True)
class DcBoxSnapshot(DataclassSnapshot[int]):
    lines: tuple[DcLineSnapshot, ...] = ()
    kinds: frozenset[str] = frozenset()


class DcBox(Entity[int, DcBoxSnapshot, DcBoxState]):
    pass


@attrs.define(kw_only=True)
class AtLineState(State[int]):
    sku: str = ""


@attrs.frozen(kw_only=True)
class AtLineSnapshot(Snapshot[int]):
    sku: str = ""


class AtLine(Entity[int, AtLineSnapshot, AtLineState]):
    pass


@attrs.define(kw_only=True)
class AtBoxState(State[int]):
    lines: list[AtLine] = attrs.field(factory=list)


@attrs.frozen(kw_only=True)
class AtBoxSnapshot(Snapshot[int]):
    lines: tuple[AtLineSnapshot, ...] = ()


class AtBox(Entity[int, AtBoxSnapshot, AtBoxState]):
    pass


def test_dataclass_string_annotations_are_resolved() -> None:
    box = DcBox(
        DcBoxSnapshot(
            id=1,
            lines=(DcLineSnapshot(id=1, sku="a"),),
            kinds=frozenset({"x"}),
        )
    )
    assert type(box._state.lines) is list
    assert type(box._state.lines[0]) is DcLine
    assert type(box._state.kinds) is set


def test_attrs_string_annotations_are_resolved() -> None:
    box = AtBox(AtBoxSnapshot(id=1, lines=(AtLineSnapshot(id=1, sku="a"),)))
    assert type(box._state.lines) is list
    assert type(box._state.lines[0]) is AtLine
