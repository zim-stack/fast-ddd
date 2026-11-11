import dataclasses
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

import attrs
import pytest

from fast_ddd.domain.aggregate import Aggregate, AggregateSnapshot, AggregateState
from fast_ddd.domain.event import DomainEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    CANCELLED = "cancelled"


@dataclasses.dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    order_id: UUID


@dataclasses.dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    order_id: UUID
    reason: str


@attrs.define(kw_only=True)
class OrderFields:
    customer_id: UUID
    status: OrderStatus = OrderStatus.DRAFT
    shipping_address: str | None = None


@attrs.define(kw_only=True)
class OrderState(OrderFields, AggregateState[UUID]):
    notes: list[str] = attrs.field(factory=list, converter=list)
    revision: int = 0  # state-only field


@attrs.frozen(kw_only=True)
# pyrefly: ignore[invalid-inheritance]
class OrderSnapshot(OrderFields, AggregateSnapshot[UUID]):
    # Any field with an immutable counterpart (list/tuple, dict/Mapping, set/frozenset) is declared twice.
    notes: tuple[str, ...] = attrs.field(default=(), converter=tuple)


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    @classmethod
    def create(cls, customer_id: UUID) -> Self:
        return cls(
            OrderSnapshot(id=uuid4(), customer_id=customer_id, status=OrderStatus.DRAFT)
        )

    def add_note(self, note: str) -> None:
        self._state.notes.append(note)

    def set_shipping_address(self, address: str) -> None:
        self._state.shipping_address = address

    def place(self) -> None:
        if self._state.status is not OrderStatus.DRAFT:
            raise ValueError("only draft orders can be placed")
        self._state.status = OrderStatus.PLACED
        self._record_event(OrderPlaced(order_id=self.id))

    def cancel(self, reason: str) -> None:
        self._state.status = OrderStatus.CANCELLED
        self._record_event(OrderCancelled(order_id=self.id, reason=reason))

    def _validate_invariants(self) -> None:
        if (
            self._state.status is OrderStatus.PLACED
            and self._state.shipping_address is None
        ):
            raise ValueError("placed order requires a shipping address")


@attrs.define(kw_only=True)
class CartState(AggregateState[UUID]):
    customer_id: UUID


@attrs.frozen(kw_only=True)
class CartSnapshot(AggregateSnapshot[UUID]):
    customer_id: UUID


class Cart(Aggregate[UUID, CartSnapshot, CartState]):
    pass


def make_order(**overrides: object) -> Order:
    data: dict[str, object] = {
        "id": uuid4(),
        "customer_id": uuid4(),
        "status": OrderStatus.DRAFT,
    }
    data.update(overrides)
    return Order(OrderSnapshot(**data))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# --- Construction and snapshot round trip --------------------------------


class TestConstruction:
    def test_state_is_rebuilt_from_snapshot(self) -> None:
        oid, cid = uuid4(), uuid4()
        order = Order(
            OrderSnapshot(
                id=oid,
                customer_id=cid,
                status=OrderStatus.PLACED,
                shipping_address="1 Main St",
                notes=("gift",),
            )
        )
        assert order.id == oid
        assert order._state.customer_id == cid
        assert order._state.status is OrderStatus.PLACED
        assert order._state.shipping_address == "1 Main St"
        assert order._state.notes == ["gift"]  # tuple -> list via state converter

    def test_state_only_fields_use_their_defaults(self) -> None:
        assert make_order()._state.revision == 0

    def test_create_factory_starts_with_no_events(self) -> None:
        assert Order.create(uuid4()).pull_domain_events() == []


class TestToSnapshot:
    def test_fresh_aggregate_round_trips_to_equal_snapshot(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(), customer_id=uuid4(), status=OrderStatus.DRAFT, notes=("a",)
        )
        assert Order(snapshot).to_snapshot() == snapshot

    def test_snapshot_reflects_current_state(self) -> None:
        order = make_order()
        order.add_note("fragile")
        order.set_shipping_address("1 Main St")
        order.place()
        snapshot = order.to_snapshot()
        assert isinstance(snapshot, OrderSnapshot)
        assert snapshot.status is OrderStatus.PLACED
        assert snapshot.notes == ("fragile",)
        assert snapshot.shipping_address == "1 Main St"

    def test_state_only_fields_are_not_in_snapshot(self) -> None:
        assert not hasattr(make_order().to_snapshot(), "revision")

    def test_earlier_snapshot_is_not_affected_by_later_changes(self) -> None:
        order = make_order()
        before = order.to_snapshot()
        order.add_note("late note")
        after = order.to_snapshot()
        assert before.notes == ()
        assert after.notes == ("late note",)

    def test_aggregate_state_is_independent_of_source_snapshot(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(), customer_id=uuid4(), status=OrderStatus.DRAFT, notes=("a",)
        )
        order = Order(snapshot)
        order.add_note("b")
        assert snapshot.notes == ("a",)

    def test_invariants_are_checked_before_snapshot(self) -> None:
        order = make_order()
        order.place()  # placed without shipping address
        with pytest.raises(ValueError, match="shipping address"):
            order.to_snapshot()
        order.set_shipping_address("1 Main St")
        assert order.to_snapshot().status is OrderStatus.PLACED


# --- Snapshot immutability -----------------------------------------------


@attrs.frozen(kw_only=True)
class PayloadSnapshot(AggregateSnapshot[UUID]):
    payload: object = None


class TestSnapshotImmutability:
    def test_snapshot_fields_cannot_be_reassigned(self) -> None:
        snapshot = make_order().to_snapshot()
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            snapshot.status = OrderStatus.CANCELLED  # type: ignore[misc]

    def test_converter_turns_list_into_tuple(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(), customer_id=uuid4(), status=OrderStatus.DRAFT, notes=["a"]  # type: ignore[arg-type]
        )
        assert snapshot.notes == ("a",)

    @pytest.mark.parametrize(
        "value",
        [[1], {"a": 1}, {1}, bytearray(b"x"), ([1],), (1, (2, [3]))],
        ids=["list", "dict", "set", "bytearray", "list-in-tuple", "deeply-nested"],
    )
    def test_mutable_containers_are_rejected(self, value: object) -> None:
        with pytest.raises(TypeError, match="mutable"):
            PayloadSnapshot(id=uuid4(), payload=value)

    @pytest.mark.parametrize(
        "value",
        [None, 1, "text", (), (1, 2), frozenset({1}), ((1, 2), (3,))],
    )
    def test_immutable_values_are_accepted(self, value: object) -> None:
        assert PayloadSnapshot(id=uuid4(), payload=value).payload == value

    def test_error_message_names_the_offending_path(self) -> None:
        with pytest.raises(TypeError, match=r"PayloadSnapshot\.payload\[1\]"):
            PayloadSnapshot(id=uuid4(), payload=(1, [2]))


# --- Identity ------------------------------------------------------------


class TestIdentity:
    def test_same_type_same_id_is_equal_regardless_of_state(self) -> None:
        oid = uuid4()
        a = make_order(id=oid)
        b = make_order(id=oid, status=OrderStatus.CANCELLED)
        assert a == b
        assert a != make_order()

    def test_hash_combines_identity_root_and_id(self) -> None:
        order = make_order()
        assert hash(order) == hash((Order, order.id))

    def test_set_deduplicates_by_identity(self) -> None:
        oid = uuid4()
        assert len({make_order(id=oid), make_order(id=oid)}) == 1

    def test_hash_is_stable_after_state_changes(self) -> None:
        order = make_order()
        before = hash(order)
        order.add_note("x")
        order.set_shipping_address("1 Main St")
        assert hash(order) == before

    def test_different_aggregate_types_with_same_id_are_not_equal(self) -> None:
        shared = uuid4()
        order = make_order(id=shared)
        cart = Cart(CartSnapshot(id=shared, customer_id=uuid4()))
        assert order != cart
        assert Aggregate._identity_root is None  # Aggregate itself is not a root

    def test_aggregate_is_not_equal_to_its_raw_id_or_snapshot(self) -> None:
        order = make_order()
        assert order != order.id
        assert order != order.to_snapshot()

    def test_each_concrete_aggregate_is_its_own_root(self) -> None:
        assert Order._identity_root is Order
        assert Cart._identity_root is Cart

    def test_subclass_of_concrete_aggregate_shares_identity_space(self) -> None:
        class GiftOrder(Order):
            pass

        oid = uuid4()
        gift = GiftOrder(
            OrderSnapshot(id=oid, customer_id=uuid4(), status=OrderStatus.DRAFT)
        )
        assert gift == make_order(id=oid)
        assert hash(gift) == hash(make_order(id=oid))
        assert GiftOrder._identity_root is Order
        assert isinstance(gift.to_snapshot(), OrderSnapshot)  # binding inherited

    def test_abstract_base_does_not_merge_its_children(self) -> None:
        class BaseBasket(Aggregate[UUID, CartSnapshot, CartState], abstract=True):
            pass

        class WishList(BaseBasket):
            pass

        class Basket(BaseBasket):
            pass

        shared = uuid4()
        snapshot = CartSnapshot(id=shared, customer_id=uuid4())
        assert WishList(snapshot) != Basket(snapshot)
        assert BaseBasket._identity_root is None


# --- Id rules ------------------------------------------------------------


class TestIdRules:
    def test_none_id_is_rejected_at_construction(self) -> None:
        snapshot = OrderSnapshot(
            id=None, customer_id=uuid4(), status=OrderStatus.DRAFT  # type: ignore[arg-type]
        )
        with pytest.raises(TypeError, match="must not be None"):
            Order(snapshot)

    def test_state_id_cannot_be_reassigned(self) -> None:
        order = make_order()
        original = order.id
        with pytest.raises(AttributeError):  # attrs FrozenAttributeError
            # pyrefly: ignore[read-only]
            order._state.id = uuid4()
        assert order.id == original

    def test_aggregate_id_property_is_read_only(self) -> None:
        order = make_order()
        with pytest.raises(AttributeError):
            order.id = uuid4()  # type: ignore[misc]

    def test_identity_equality_id_type_is_rejected(self) -> None:
        class RawId:  # hashable, but equal only by reference
            pass

        @attrs.define(kw_only=True)
        class RawState(AggregateState[RawId]):
            pass

        @attrs.frozen(kw_only=True)
        class RawSnapshot(AggregateSnapshot[RawId]):
            pass

        class RawAggregate(Aggregate[RawId, RawSnapshot, RawState]):
            pass

        with pytest.raises(TypeError, match="uses identity equality"):
            RawAggregate(RawSnapshot(id=RawId()))


# --- Domain events -------------------------------------------------------


class TestDomainEvents:
    def test_command_records_event(self) -> None:
        order = make_order()
        order.set_shipping_address("1 Main St")
        order.place()

        events = order.pull_domain_events()

        assert len(events) == 1
        assert isinstance(events[0], OrderPlaced)
        assert events[0].order_id == order.id

    def test_pull_clears_recorded_events(self) -> None:
        order = make_order()
        order.cancel("changed mind")
        assert len(order.pull_domain_events()) == 1
        assert order.pull_domain_events() == []

    def test_events_keep_recording_order(self) -> None:
        order = make_order()
        order.place()
        order.cancel("out of stock")
        assert [type(e) for e in order.pull_domain_events()] == [
            OrderPlaced,
            OrderCancelled,
        ]

    def test_returned_list_is_a_copy(self) -> None:
        order = make_order()
        order.place()
        events = order.pull_domain_events()
        events.clear()
        order.cancel("x")
        assert len(order.pull_domain_events()) == 1

    def test_events_are_per_instance(self) -> None:
        a, b = make_order(), make_order()
        a.place()
        assert b.pull_domain_events() == []

    def test_to_snapshot_does_not_consume_events(self) -> None:
        order = make_order()
        order.place()
        order.set_shipping_address("1 Main St")
        order.to_snapshot()
        assert len(order.pull_domain_events()) == 1


# --- Definition-time rules -----------------------------------------------


class TestBindingRules:
    def test_unparametrized_aggregate_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="must parametrize Aggregate directly"):

            class Bad(Aggregate):  # type: ignore[type-arg]
                pass

    def test_unresolved_type_variable_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="unresolved"):

            class Bad[S: OrderState](Aggregate[UUID, OrderSnapshot, S]):
                pass

    def test_unresolved_type_variable_is_allowed_when_abstract(self) -> None:
        class Generic_[S: OrderState](Aggregate[UUID, OrderSnapshot, S], abstract=True):
            pass

        assert Generic_._identity_root is None

    def test_indirect_parametrization_is_not_supported_yet(self) -> None:
        # Documents a known limitation. Flip this test when the TypeVar
        # substitution map is implemented.
        class Intermediate[M: AggregateSnapshot](
            Aggregate[UUID, M, OrderState], abstract=True
        ):
            pass

        with pytest.raises(TypeError, match="must parametrize Aggregate directly"):

            class Concrete(Intermediate[OrderSnapshot]):
                pass

    def test_state_type_must_be_an_attrs_aggregate_state(self) -> None:
        with pytest.raises(TypeError, match="state type must be an attrs class"):

            class Bad(Aggregate[UUID, OrderSnapshot, dict]):  # type: ignore[type-var]
                pass

    def test_snapshot_type_must_be_an_attrs_aggregate_snapshot(self) -> None:
        with pytest.raises(TypeError, match="snapshot type must be an attrs class"):

            class Bad(Aggregate[UUID, dict, OrderState]):  # type: ignore[type-var]
                pass

    def test_snapshot_field_missing_on_state_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class ThinState(AggregateState[UUID]):
            pass

        @attrs.frozen(kw_only=True)
        class WideSnapshot(AggregateSnapshot[UUID]):
            total: int

        with pytest.raises(TypeError, match=r"missing fields.*\['total'\]"):

            class Bad(Aggregate[UUID, WideSnapshot, ThinState]):
                pass

    def test_required_state_field_missing_on_snapshot_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class WideState(AggregateState[UUID]):
            total: int

        @attrs.frozen(kw_only=True)
        class ThinSnapshot(AggregateSnapshot[UUID]):
            pass

        with pytest.raises(TypeError, match=r"no default.*\['total'\]"):

            class Bad(Aggregate[UUID, ThinSnapshot, WideState]):
                pass

    def test_stray_dataclasses_field_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class StrayState(AggregateState[UUID]):
            tags: list[str] = dataclasses.field(default_factory=list)

        @attrs.frozen(kw_only=True)
        class PlainSnapshot(AggregateSnapshot[UUID]):
            pass

        with pytest.raises(TypeError, match="dataclasses.Field"):

            class Bad(Aggregate[UUID, PlainSnapshot, StrayState]):
                pass


# --- Representation ------------------------------------------------------


class TestRepresentation:
    def test_str_uses_class_name_and_id(self) -> None:
        order = make_order()
        assert str(order) == f"Order({order.id})"

    def test_repr_starts_with_class_and_state(self) -> None:
        assert repr(make_order()).startswith("Order(state=")


# -- Inheritance behavior -----------------------------------------------


def test_mixin_fields_exist_on_both_state_and_snapshot() -> None:
    shared = {f.name for f in attrs.fields(OrderFields)}
    assert shared <= {f.name for f in attrs.fields(OrderState)}
    assert shared <= {f.name for f in attrs.fields(OrderSnapshot)}
    assert Order._shared_field_names.count("customer_id") == 1
