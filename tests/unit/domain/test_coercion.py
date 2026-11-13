"""The container kind restored into state follows the state field's annotation."""

from collections.abc import MutableSequence, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Annotated, Any

from fast_ddd.domain.entity import (
    Entity,
)
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


@dataclass(kw_only=True)
class ItemState(DataclassState[int]):
    name: str = ""


@dataclass(frozen=True, kw_only=True)
class ItemSnapshot(DataclassSnapshot[int]):
    name: str = ""


class Item(Entity[int, ItemSnapshot, ItemState]):
    pass


@dataclass(kw_only=True)
class HolderState(DataclassState[int]):
    as_list: list[Item] = field(default_factory=list)
    as_set: set[Item] = field(default_factory=set)
    as_frozenset: frozenset[Item] = frozenset()
    as_tuple: tuple[Item, ...] = ()
    as_dict: dict[str, Item] = field(default_factory=dict)
    optional_list: list[Item] | None = None
    typing_optional: set[Item] | None = None
    mutable_seq: MutableSequence[Item] = field(default_factory=list)
    read_only_seq: Sequence[Item] = ()
    annotated: Annotated[list[Item], "meta"] = field(default_factory=list)
    dict_of_lists: dict[str, list[Item]] = field(default_factory=dict)
    list_of_tuples: list[tuple[Item, ...]] = field(default_factory=list)
    untyped: Any = ()
    ambiguous: list[Item] | tuple[Item, ...] = ()
    tags: list[str] = field(default_factory=list)


def _empty_map() -> Any:
    return MappingProxyType({})


@dataclass(frozen=True, kw_only=True)
class HolderSnapshot(DataclassSnapshot[int]):
    as_list: tuple[ItemSnapshot, ...] = ()
    as_set: frozenset[ItemSnapshot] = frozenset()
    as_frozenset: frozenset[ItemSnapshot] = frozenset()
    as_tuple: tuple[ItemSnapshot, ...] = ()
    as_dict: Any = field(default_factory=_empty_map)
    optional_list: tuple[ItemSnapshot, ...] | None = None
    typing_optional: frozenset[ItemSnapshot] | None = None
    mutable_seq: tuple[ItemSnapshot, ...] = ()
    read_only_seq: tuple[ItemSnapshot, ...] = ()
    annotated: tuple[ItemSnapshot, ...] = ()
    dict_of_lists: Any = field(default_factory=_empty_map)
    list_of_tuples: tuple[tuple[ItemSnapshot, ...], ...] = ()
    untyped: Any = ()
    ambiguous: tuple[ItemSnapshot, ...] = ()
    tags: tuple[str, ...] = ()


class Holder(Entity[int, HolderSnapshot, HolderState]):
    pass


def item(i: int) -> Item:
    return Item(ItemSnapshot(id=i, name=f"item-{i}"))


def round_trip() -> HolderState:
    one, two = item(1), item(2)
    holder = Holder(HolderSnapshot(id=1))
    s = holder._state
    s.as_list = [one, two]
    s.as_set = {one, two}
    s.as_frozenset = frozenset({one})
    s.as_tuple = (one, two)
    s.as_dict = {"a": one}
    s.optional_list = [one]
    s.typing_optional = {one}
    s.mutable_seq = [one]
    s.read_only_seq = (one,)
    s.annotated = [one]
    s.dict_of_lists = {"k": [one, two]}
    s.list_of_tuples = [(one,), (two,)]
    s.untyped = (one,)
    s.ambiguous = (one,)
    s.tags = ["t"]
    return Holder(holder.to_snapshot())._state


def test_concrete_containers_are_restored() -> None:
    s = round_trip()
    assert type(s.as_list) is list and len(s.as_list) == 2
    assert type(s.as_set) is set and len(s.as_set) == 2
    assert type(s.as_frozenset) is frozenset
    assert type(s.as_tuple) is tuple
    assert type(s.as_dict) is dict
    assert type(s.tags) is list


def test_restored_items_are_entities() -> None:
    s = round_trip()
    assert all(type(i) is Item for i in s.as_list)
    assert all(type(i) is Item for i in s.as_set)
    assert type(s.as_dict["a"]) is Item


def test_optional_and_annotated_wrappers_are_unwrapped() -> None:
    s = round_trip()
    assert type(s.optional_list) is list
    assert type(s.typing_optional) is set
    assert type(s.annotated) is list


def test_mutable_abstract_annotations_become_concrete_mutables() -> None:
    assert type(round_trip().mutable_seq) is list


def test_read_only_abstract_annotation_keeps_the_snapshot_kind() -> None:
    assert type(round_trip().read_only_seq) is tuple


def test_nested_containers_follow_nested_annotations() -> None:
    s = round_trip()
    assert type(s.dict_of_lists) is dict
    assert type(s.dict_of_lists["k"]) is list
    assert all(type(i) is Item for i in s.dict_of_lists["k"])
    assert type(s.list_of_tuples) is list
    assert all(type(t) is tuple for t in s.list_of_tuples)


def test_unusable_annotations_keep_the_snapshot_kind() -> None:
    s = round_trip()
    assert type(s.untyped) is tuple  # Any
    assert type(s.ambiguous) is tuple  # union of two containers


def test_none_is_kept() -> None:
    holder = Holder(Holder(HolderSnapshot(id=1)).to_snapshot())
    assert holder._state.optional_list is None
    assert holder._state.typing_optional is None


def test_state_default_factories_still_apply_when_snapshot_is_empty() -> None:
    s = Holder(HolderSnapshot(id=1))._state
    assert s.as_list == [] and type(s.as_list) is list
    assert s.as_dict == {} and type(s.as_dict) is dict
