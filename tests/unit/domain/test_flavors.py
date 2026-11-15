"""The same behavior must hold for every way of declaring state and snapshot.

Flavors: attrs or dataclass, with the optional base classes or purely
structural (the user declares `id` himself), and both mixed pairs.
"""

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, NamedTuple

import attrs
import pytest

from fast_ddd.domain.aggregate import Aggregate
from fast_ddd.domain.entity import (
    Entity,
    Snapshot,
    State,
)
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState

NO_DEFAULT = object()


def _attrs_field(tp: Any, default: Any) -> Any:
    if default is NO_DEFAULT:
        return attrs.field(type=tp)
    mode, value = default
    return attrs.field(type=tp, **{"default" if mode == "value" else "factory": value})


def _dc_field(name: str, tp: Any, default: Any) -> Any:
    if default is NO_DEFAULT:
        return (name, tp)
    mode, value = default
    kwargs = {"default" if mode == "value" else "default_factory": value}
    return (name, tp, dataclasses.field(**kwargs))


def make_model(
    kind: str,
    name: str,
    fields: list[tuple[str, Any, Any]],
    *,
    frozen: bool,
    base: type | None,
) -> type:
    """Build an attrs class or dataclass, with or without the optional base."""
    if base is None:  # structural: the user declares `id` themselves
        fields = [("id", int, NO_DEFAULT), *fields]
    bases = (base,) if base is not None else ()
    if kind == "attrs":
        return attrs.make_class(
            name,
            {n: _attrs_field(tp, d) for n, tp, d in fields},
            bases=bases,
            kw_only=True,
            frozen=frozen,
        )
    return dataclasses.make_dataclass(
        name,
        [_dc_field(n, tp, d) for n, tp, d in fields],
        bases=bases,
        kw_only=True,
        frozen=frozen,
    )


class Domain(NamedTuple):
    Line: type
    LineSnapshot: type
    Order: type
    OrderSnapshot: type
    protects_state_id: bool


def build_domain(state_kind: str, snapshot_kind: str, with_bases: bool) -> Domain:
    state_base = (
        (State if state_kind == "attrs" else DataclassState) if with_bases else None
    )
    snap_base = (
        (Snapshot if snapshot_kind == "attrs" else DataclassSnapshot)
        if with_bases
        else None
    )

    line_state = make_model(
        state_kind,
        "LineState",
        [
            ("sku", str, NO_DEFAULT),
            ("quantity", int, NO_DEFAULT),
            ("cache", int | None, ("value", None)),  # state-only
        ],
        frozen=False,
        base=state_base,
    )
    line_snapshot = make_model(
        snapshot_kind,
        "LineSnapshot",
        [("sku", str, NO_DEFAULT), ("quantity", int, NO_DEFAULT)],
        frozen=True,
        base=snap_base,
    )

    class Line(Entity[int, line_snapshot, line_state]):  # type: ignore[valid-type]
        def change_quantity(self, quantity: int) -> None:
            self._state.quantity = quantity

    order_state = make_model(
        state_kind,
        "OrderState",
        [
            ("customer", str, ("value", "c")),
            ("lines", list[Line], ("factory", list)),
            ("tags", list[str], ("factory", list)),
            ("by_sku", dict[str, Line], ("factory", dict)),
            ("blob", object, ("value", None)),  # state-only
        ],
        frozen=False,
        base=state_base,
    )
    order_snapshot = make_model(
        snapshot_kind,
        "OrderSnapshot",
        [
            ("customer", str, ("value", "c")),
            ("lines", tuple[line_snapshot, ...], ("value", ())),  # type: ignore[valid-type]
            ("tags", tuple[str, ...], ("value", ())),
            ("by_sku", Mapping[str, line_snapshot], ("factory", lambda: MappingProxyType({}))),  # type: ignore[valid-type]
        ],
        frozen=True,
        base=snap_base,
    )

    class Order(Aggregate[int, order_snapshot, order_state]):  # type: ignore[valid-type]
        def add_line(self, sku: str, quantity: int = 1) -> Line:
            line = Line(
                line_snapshot(id=len(self._state.lines) + 1, sku=sku, quantity=quantity)
            )
            self._state.lines.append(line)
            self._state.by_sku[sku] = line
            return line

        def validate_invariants(self) -> None:
            if not self._state.customer:
                raise ValueError("customer required")

    return Domain(
        Line, line_snapshot, Order, order_snapshot, protects_state_id=with_bases
    )


FLAVORS = [
    ("attrs", "attrs", True),
    ("attrs", "attrs", False),
    ("dataclass", "dataclass", True),
    ("dataclass", "dataclass", False),
    ("attrs", "dataclass", True),
    ("dataclass", "attrs", True),
]


@pytest.fixture(
    params=FLAVORS,
    ids=lambda f: f"{f[0]}-state/{f[1]}-snapshot/{'bases' if f[2] else 'structural'}",
)
def d(request: pytest.FixtureRequest) -> Domain:
    return build_domain(*request.param)


def new_order(d: Domain, id: int = 1) -> Any:
    return d.Order(d.OrderSnapshot(id=id))


def filled_order(d: Domain) -> Any:
    order = new_order(d)
    order.add_line("a", 1)
    order.add_line("b", 2)
    order._state.tags.append("x")
    return order


class TestEveryFlavor:
    def test_nested_round_trip(self, d: Domain) -> None:
        first = filled_order(d).to_snapshot()
        assert d.Order(first).to_snapshot() == first

    def test_snapshot_shapes(self, d: Domain) -> None:
        snapshot = filled_order(d).to_snapshot()
        assert type(snapshot) is d.OrderSnapshot
        assert type(snapshot.lines) is tuple
        assert all(type(s) is d.LineSnapshot for s in snapshot.lines)
        assert type(snapshot.by_sku) is MappingProxyType
        assert snapshot.tags == ("x",)
        assert [s.sku for s in snapshot.lines] == ["a", "b"]

    def test_restored_containers_follow_state_annotations(self, d: Domain) -> None:
        state = d.Order(filled_order(d).to_snapshot())._state
        assert type(state.lines) is list
        assert all(type(line) is d.Line for line in state.lines)
        assert type(state.tags) is list
        assert type(state.by_sku) is dict
        assert type(state.by_sku["a"]) is d.Line

    def test_snapshot_is_frozen(self, d: Domain) -> None:
        snapshot = filled_order(d).to_snapshot()
        with pytest.raises(AttributeError):  # FrozenInstanceError subclasses it
            snapshot.customer = "other"

    def test_earlier_snapshot_is_not_affected_by_later_changes(self, d: Domain) -> None:
        order = filled_order(d)
        before = order.to_snapshot()
        order._state.lines[0].change_quantity(99)
        order.add_line("c")
        assert before.lines[0].quantity == 1
        assert len(before.lines) == 2

    def test_state_only_fields_are_reset_and_absent_from_snapshot(
        self, d: Domain
    ) -> None:
        order = filled_order(d)
        order._state.blob = object()
        order._state.lines[0]._state.cache = 5
        snapshot = order.to_snapshot()
        assert not hasattr(snapshot, "blob")
        restored = d.Order(snapshot)._state
        assert restored.blob is None
        assert restored.lines[0]._state.cache is None

    def test_entity_id_is_read_only(self, d: Domain) -> None:
        with pytest.raises(AttributeError):
            new_order(d).id = 2

    def test_state_id_protection_comes_with_the_optional_bases(self, d: Domain) -> None:
        order = new_order(d)
        if d.protects_state_id:
            with pytest.raises(AttributeError):
                order._state.id = 2
            assert order.id == 1
        else:
            # Structural states are not protected; the docs say so.
            order._state.id = 2
            assert order.id == 2

    def test_mutable_state_value_is_rejected_when_snapshotting(self, d: Domain) -> None:
        order = new_order(d)
        order._state.tags.append(bytearray(b"x"))
        with pytest.raises(TypeError, match="mutable bytearray"):
            order.to_snapshot()

    def test_live_entity_inside_a_snapshot_is_rejected(self, d: Domain) -> None:
        line = filled_order(d)._state.lines[0]
        snapshot = d.OrderSnapshot(id=1, lines=(line,))
        with pytest.raises(TypeError, match=r"OrderSnapshot\.lines\[0\] holds"):
            d.Order(snapshot)

    def test_identity_semantics(self, d: Domain) -> None:
        a, b = new_order(d, 1), filled_order(d)
        assert a == b and hash(a) == hash(b)
        assert a != new_order(d, 2)
        assert a != a.to_snapshot()

    def test_aggregate_events_and_invariants(self, d: Domain) -> None:
        order = new_order(d)
        order.record_event("something happened")
        assert order.pull_domain_events() == ["something happened"]
        assert order.pull_domain_events() == []
        order._state.customer = ""
        with pytest.raises(ValueError, match="customer required"):
            order.to_snapshot()

    def test_entity_state_is_independent_of_the_source_snapshot(
        self, d: Domain
    ) -> None:
        snapshot = filled_order(d).to_snapshot()
        restored = d.Order(snapshot)
        restored._state.lines[0].change_quantity(42)
        restored._state.tags.append("y")
        assert snapshot.lines[0].quantity == 1
        assert snapshot.tags == ("x",)


class TestMixedFlavorErrors:
    def test_aggregate_accepts_a_pair_from_different_libraries(self) -> None:
        # Covered by the mixed flavors above; this documents the intent.
        d = build_domain("attrs", "dataclass", True)
        assert dataclasses.is_dataclass(d.OrderSnapshot)
        assert attrs.has(type(new_order(d)._state))

    @pytest.mark.parametrize("kind", ["attrs", "dataclass"])
    def test_non_frozen_snapshot_is_rejected_for_both_libraries(
        self, kind: str
    ) -> None:
        state = make_model(kind, "S", [], frozen=False, base=None)
        snapshot = make_model(kind, "M", [], frozen=False, base=None)
        with pytest.raises(
            TypeError, match=r"snapshot type M must be frozen \(frozen=True\)"
        ):

            class Bad(Entity[int, snapshot, state]):  # type: ignore[valid-type]
                pass

    @pytest.mark.parametrize("kind", ["attrs", "dataclass"])
    def test_stray_field_check_only_concerns_attrs(self, kind: str) -> None:
        if kind == "attrs":

            @attrs.define(kw_only=True)
            class StrayState:
                id: int
                tags: list[str] = dataclasses.field(default_factory=list)  # type: ignore[assignment]

            @attrs.frozen(kw_only=True)
            class PlainSnapshot:
                id: int

            with pytest.raises(TypeError, match="dataclasses.Field"):

                class Bad(Entity[int, PlainSnapshot, StrayState]):
                    pass

        else:

            @dataclass(kw_only=True)
            class OkState:
                id: int
                tags: list[str] = dataclasses.field(default_factory=list)

            @dataclass(frozen=True, kw_only=True)
            class PlainSnapshot:
                id: int

            class Ok(Entity[int, PlainSnapshot, OkState]):
                pass

            assert Ok(PlainSnapshot(id=1))._state.tags == []
