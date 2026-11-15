import dataclasses
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

import attrs
import pytest

from fast_ddd.domain.aggregate import Aggregate
from fast_ddd.domain.entity import Entity
from fast_ddd.domain.flavors.attrs_models import Snapshot, State

# --- Fixtures (e-commerce) -----------------------------------------------
# Domain events are plain attrs classes: the tests only need them to be
# recorded and returned.


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    CANCELLED = "cancelled"


@attrs.frozen
class OrderPlaced:
    order_id: UUID


@attrs.frozen
class OrderCancelled:
    order_id: UUID
    reason: str


@attrs.define(kw_only=True)
class LineState(State[int]):
    sku: str
    quantity: int
    price_cache: int | None = None  # state-only


@attrs.frozen(kw_only=True)
class LineSnapshot(Snapshot[int]):
    sku: str
    quantity: int


class Line(Entity[int, LineSnapshot, LineState]):
    def change_quantity(self, quantity: int) -> None:
        self._state.quantity = quantity


@attrs.define(kw_only=True)
class OrderState(State[UUID]):
    customer_id: UUID
    status: OrderStatus = OrderStatus.DRAFT
    shipping_address: str | None = None
    lines: list[Line] = attrs.field(factory=list, converter=list)
    notes: list[str] = attrs.field(factory=list, converter=list)
    revision: int = 0  # state-only field: has a default, absent from the snapshot


@attrs.frozen(kw_only=True)
class OrderSnapshot(Snapshot[UUID]):
    customer_id: UUID
    status: OrderStatus
    shipping_address: str | None = None
    lines: tuple[LineSnapshot, ...] = attrs.field(default=(), converter=tuple)
    notes: tuple[str, ...] = attrs.field(default=(), converter=tuple)


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    @classmethod
    def create(cls, customer_id: UUID) -> Self:
        return cls(
            OrderSnapshot(id=uuid4(), customer_id=customer_id, status=OrderStatus.DRAFT)
        )

    def add_line(self, sku: str, quantity: int) -> Line:
        line = Line(
            LineSnapshot(id=len(self._state.lines) + 1, sku=sku, quantity=quantity)
        )
        self._state.lines.append(line)
        return line

    def add_note(self, note: str) -> None:
        self._state.notes.append(note)

    def set_shipping_address(self, address: str) -> None:
        self._state.shipping_address = address

    def place(self) -> None:
        if self._state.status is not OrderStatus.DRAFT:
            raise ValueError("only draft orders can be placed")
        self._state.status = OrderStatus.PLACED
        # pyrefly: ignore[bad-argument-type]
        self.record_event(OrderPlaced(order_id=self.id))

    def cancel(self, reason: str) -> None:
        self._state.status = OrderStatus.CANCELLED
        # pyrefly: ignore[bad-argument-type]
        self.record_event(OrderCancelled(order_id=self.id, reason=reason))

    def validate_invariants(self) -> None:
        if self._state.status is OrderStatus.PLACED:
            if self._state.shipping_address is None:
                raise ValueError("placed order requires a shipping address")
            if not self._state.lines:
                raise ValueError("placed order requires at least one line")


@attrs.define(kw_only=True)
class CartState(State[UUID]):
    customer_id: UUID


@attrs.frozen(kw_only=True)
class CartSnapshot(Snapshot[UUID]):
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


def make_placeable_order() -> Order:
    order = make_order()
    order.add_line("sku-1", 2)
    order.set_shipping_address("1 Main St")
    return order


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
                lines=(LineSnapshot(id=1, sku="a", quantity=2),),
            )
        )
        assert order.id == oid
        assert order._state.customer_id == cid
        assert order._state.status is OrderStatus.PLACED
        assert order._state.shipping_address == "1 Main St"
        assert order._state.notes == ["gift"]  # tuple -> list via state converter
        assert len(order._state.lines) == 1
        assert type(order._state.lines[0]) is Line

    def test_state_only_fields_use_their_defaults(self) -> None:
        assert make_order()._state.revision == 0

    def test_create_factory_starts_with_no_events(self) -> None:
        assert Order.create(uuid4()).pull_domain_events() == []

    def test_aggregate_is_an_entity(self) -> None:
        assert issubclass(Aggregate, Entity)
        assert isinstance(make_order(), Entity)

    def test_construction_records_no_events(self) -> None:
        assert make_order().pull_domain_events() == []


class TestToSnapshot:
    def test_returns_exact_snapshot_type(self) -> None:
        assert type(make_order().to_snapshot()) is OrderSnapshot

    def test_fresh_aggregate_round_trips_to_equal_snapshot(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(),
            customer_id=uuid4(),
            status=OrderStatus.DRAFT,
            notes=("a",),
            lines=(LineSnapshot(id=1, sku="a", quantity=1),),
        )
        assert Order(snapshot).to_snapshot() == snapshot

    def test_snapshot_reflects_current_state(self) -> None:
        order = make_placeable_order()
        order.add_note("fragile")
        order.place()
        snapshot = order.to_snapshot()
        assert snapshot.status is OrderStatus.PLACED
        assert snapshot.notes == ("fragile",)
        assert snapshot.shipping_address == "1 Main St"

    def test_inner_entities_become_snapshots(self) -> None:
        order = make_order()
        order.add_line("a", 1)
        order.add_line("b", 2)
        lines = order.to_snapshot().lines
        assert type(lines) is tuple
        assert [type(s) for s in lines] == [LineSnapshot, LineSnapshot]
        assert [(s.sku, s.quantity) for s in lines] == [("a", 1), ("b", 2)]

    def test_changes_to_inner_entities_reach_the_snapshot(self) -> None:
        order = make_order()
        line = order.add_line("a", 1)
        line.change_quantity(7)
        assert order.to_snapshot().lines[0].quantity == 7

    def test_state_only_fields_are_not_in_snapshot(self) -> None:
        assert not hasattr(make_order().to_snapshot(), "revision")

    def test_earlier_snapshot_is_not_affected_by_later_changes(self) -> None:
        order = make_order()
        line = order.add_line("a", 1)
        before = order.to_snapshot()
        line.change_quantity(9)
        order.add_line("b", 1)
        order.add_note("late")
        after = order.to_snapshot()
        assert before.lines[0].quantity == 1
        assert len(before.lines) == 1 and before.notes == ()
        assert len(after.lines) == 2 and after.notes == ("late",)

    def test_aggregate_state_is_independent_of_source_snapshot(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(),
            customer_id=uuid4(),
            status=OrderStatus.DRAFT,
            lines=(LineSnapshot(id=1, sku="a", quantity=1),),
            notes=("a",),
        )
        order = Order(snapshot)
        order.add_note("b")
        order._state.lines[0].change_quantity(5)
        assert snapshot.notes == ("a",)
        assert snapshot.lines[0].quantity == 1

    def test_state_only_fields_of_inner_entities_are_reset_on_load(self) -> None:
        order = make_order()
        order.add_line("a", 1)._state.price_cache = 100
        restored = Order(order.to_snapshot())
        assert restored._state.lines[0]._state.price_cache is None

    def test_full_round_trip_with_nested_entities(self) -> None:
        order = make_placeable_order()
        first = order.to_snapshot()
        assert Order(first).to_snapshot() == first


# --- Invariants ----------------------------------------------------------


class TestInvariants:
    def test_invariants_are_checked_before_snapshot(self) -> None:
        order = make_order()
        order.place()  # placed without address and lines
        with pytest.raises(ValueError, match="shipping address"):
            order.to_snapshot()
        order.set_shipping_address("1 Main St")
        with pytest.raises(ValueError, match="at least one line"):
            order.to_snapshot()
        order.add_line("a", 1)
        assert order.to_snapshot().status is OrderStatus.PLACED

    def test_default_hook_accepts_everything(self) -> None:
        cart = Cart(CartSnapshot(id=uuid4(), customer_id=uuid4()))
        cart.validate_invariants()  # does not raise
        assert isinstance(cart.to_snapshot(), CartSnapshot)

    def test_failed_validation_produces_no_snapshot_and_keeps_events(self) -> None:
        order = make_order()
        order.place()
        with pytest.raises(ValueError):
            order.to_snapshot()
        assert len(order.pull_domain_events()) == 1

    def test_invariants_are_not_checked_on_load(self) -> None:
        # Documents current behavior: loading an inconsistent snapshot works.
        order = make_order(status=OrderStatus.PLACED)
        with pytest.raises(ValueError):
            order.to_snapshot()


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
        order.add_line("a", 1)
        order.set_shipping_address("1 Main St")
        assert hash(order) == before

    def test_different_aggregate_types_with_same_id_are_not_equal(self) -> None:
        shared = uuid4()
        cart = Cart(CartSnapshot(id=shared, customer_id=uuid4()))
        assert make_order(id=shared) != cart

    def test_aggregate_is_not_equal_to_its_raw_id_or_snapshot(self) -> None:
        order = make_order()
        assert order != order.id
        assert order != order.to_snapshot()

    def test_aggregate_bases_are_not_identity_roots(self) -> None:
        assert Aggregate._identity_root is None
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
        assert type(gift.to_snapshot()) is OrderSnapshot  # binding inherited

    def test_abstract_base_does_not_merge_its_children(self) -> None:
        @attrs.define(kw_only=True)
        class BasketState(State[UUID]):
            pass

        @attrs.frozen(kw_only=True)
        class BasketSnapshot(Snapshot[UUID]):
            pass

        class BaseBasket(Aggregate[UUID, BasketSnapshot, BasketState], abstract=True):
            pass

        class WishList(BaseBasket):
            pass

        class Basket(BaseBasket):
            pass

        snapshot = BasketSnapshot(id=uuid4())
        assert WishList(snapshot) != Basket(snapshot)
        assert BaseBasket._identity_root is None

    def test_overriding_eq_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="overrides __eq__"):

            class Bad(Order):
                def __eq__(self, other: object) -> bool:
                    return True


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
        with pytest.raises(AttributeError):
            make_order().id = uuid4()  # type: ignore[misc]

    def test_identity_equality_id_type_is_rejected(self) -> None:
        class RawId:  # hashable, but equal only by reference
            pass

        @attrs.define(kw_only=True)
        class RawState(State[RawId]):
            pass

        @attrs.frozen(kw_only=True)
        class RawSnapshot(Snapshot[RawId]):
            pass

        class RawAggregate(Aggregate[RawId, RawSnapshot, RawState]):
            pass

        with pytest.raises(TypeError, match="uses identity equality"):
            RawAggregate(RawSnapshot(id=RawId()))


# --- Domain events -------------------------------------------------------


class TestDomainEvents:
    def test_command_records_event(self) -> None:
        order = make_placeable_order()
        order.place()
        assert order.pull_domain_events() == [OrderPlaced(order_id=order.id)]

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
        order = make_placeable_order()
        order.place()
        order.to_snapshot()
        assert len(order.pull_domain_events()) == 1

    def test_events_are_not_part_of_the_snapshot(self) -> None:
        order = make_placeable_order()
        order.place()
        restored = Order(order.to_snapshot())
        assert restored.pull_domain_events() == []


# --- Nesting rules -------------------------------------------------------


class TestNestability:
    def test_flags(self) -> None:
        assert Aggregate._nestable is False
        assert Order._nestable is False
        assert Entity._nestable is True
        assert Line._nestable is True

    def test_aggregate_inside_another_aggregates_state_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class HolderState(State[UUID]):
            related: object = None

        @attrs.frozen(kw_only=True)
        class HolderSnapshot(Snapshot[UUID]):
            related: object = None

        class Holder(Aggregate[UUID, HolderSnapshot, HolderState]):
            pass

        holder = Holder(HolderSnapshot(id=uuid4()))
        holder._state.related = make_order()
        with pytest.raises(TypeError, match="not nestable"):
            holder.to_snapshot()

    def test_aggregates_reference_each_other_by_id(self) -> None:
        @attrs.define(kw_only=True)
        class InvoiceState(State[UUID]):
            order_id: UUID

        @attrs.frozen(kw_only=True)
        class InvoiceSnapshot(Snapshot[UUID]):
            order_id: UUID

        class Invoice(Aggregate[UUID, InvoiceSnapshot, InvoiceState]):
            pass

        order = make_order()
        invoice = Invoice(InvoiceSnapshot(id=uuid4(), order_id=order.id))
        assert invoice.to_snapshot().order_id == order.id

    def test_aggregate_is_not_restored_from_a_snapshot_inside_a_snapshot(self) -> None:
        # Aggregate snapshots are not registered for nested restoration:
        # they stay as plain snapshot values.
        @attrs.define(kw_only=True)
        class HolderState(State[UUID]):
            cart: object = None

        @attrs.frozen(kw_only=True)
        class HolderSnapshot(Snapshot[UUID]):
            cart: object = None

        class Holder(Aggregate[UUID, HolderSnapshot, HolderState]):
            pass

        cart_snapshot = CartSnapshot(id=uuid4(), customer_id=uuid4())
        holder = Holder(HolderSnapshot(id=uuid4(), cart=cart_snapshot))
        assert holder._state.cart is cart_snapshot


# --- Snapshot immutability -----------------------------------------------


class TestSnapshotImmutability:
    def test_snapshot_fields_cannot_be_reassigned(self) -> None:
        snapshot = make_order().to_snapshot()
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            snapshot.status = OrderStatus.CANCELLED  # type: ignore[misc]

    def test_snapshot_cannot_hold_a_live_inner_entity(self) -> None:
        line = Line(LineSnapshot(id=1, sku="a", quantity=1))
        snapshot = OrderSnapshot(
            id=uuid4(),
            customer_id=uuid4(),
            status=OrderStatus.DRAFT,
            lines=(line,),  # type: ignore[arg-type]
        )
        # Validated when the snapshot reaches an aggregate.
        with pytest.raises(TypeError, match=r"OrderSnapshot\.lines\[0\] holds Line"):
            Order(snapshot)

    def test_converter_turns_lists_into_tuples(self) -> None:
        snapshot = OrderSnapshot(
            id=uuid4(),
            customer_id=uuid4(),
            status=OrderStatus.DRAFT,
            notes=["a"],  # type: ignore[arg-type]
        )
        assert snapshot.notes == ("a",)

    def test_snapshot_holding_a_list_is_rejected_by_the_aggregate(self) -> None:
        @attrs.define(kw_only=True)
        class RawState(State[UUID]):
            tags: object = None

        @attrs.frozen(kw_only=True)
        class RawSnapshot(Snapshot[UUID]):
            tags: object = None

        class Raw(Aggregate[UUID, RawSnapshot, RawState]):
            pass

        with pytest.raises(TypeError, match="mutable list"):
            Raw(RawSnapshot(id=uuid4(), tags=["a"]))


# --- Definition-time rules -----------------------------------------------


class TestBindingRules:
    def test_unparametrized_aggregate_is_rejected(self) -> None:
        # An unsubscripted generic base leaves its type variables open.
        with pytest.raises(TypeError, match="unresolved"):

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

    def test_indirect_parametrization_binds_through_a_generic_base(self) -> None:
        # More cases live in test_indirect_parametrization.py.
        class Intermediate[M: Snapshot](Aggregate[UUID, M, OrderState], abstract=True):
            pass

        class Concrete(Intermediate[OrderSnapshot]):
            pass

        assert Concrete._snapshot_cls is OrderSnapshot
        assert Concrete._state_cls is OrderState

    def test_state_type_must_be_an_attrs_state(self) -> None:
        with pytest.raises(TypeError, match="state type must be an attrs class"):

            class Bad(Aggregate[UUID, OrderSnapshot, dict]):  # type: ignore[type-var]
                pass

    def test_snapshot_type_must_be_an_attrs_snapshot(self) -> None:
        with pytest.raises(TypeError, match="snapshot type must be an attrs class"):

            class Bad(Aggregate[UUID, dict, OrderState]):  # type: ignore[type-var]
                pass

    def test_snapshot_field_missing_on_state_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class ThinState(State[UUID]):
            pass

        @attrs.frozen(kw_only=True)
        class WideSnapshot(Snapshot[UUID]):
            total: int

        with pytest.raises(TypeError, match=r"missing fields.*\['total'\]"):

            class Bad(Aggregate[UUID, WideSnapshot, ThinState]):
                pass

    def test_required_state_field_missing_on_snapshot_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class WideState(State[UUID]):
            total: int

        @attrs.frozen(kw_only=True)
        class ThinSnapshot(Snapshot[UUID]):
            pass

        with pytest.raises(TypeError, match=r"no default.*\['total'\]"):

            class Bad(Aggregate[UUID, ThinSnapshot, WideState]):
                pass

    def test_stray_dataclasses_field_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class StrayState(State[UUID]):
            tags: list[str] = dataclasses.field(default_factory=list)  # type: ignore[assignment]

        @attrs.frozen(kw_only=True)
        class PlainSnapshot(Snapshot[UUID]):
            pass

        with pytest.raises(TypeError, match="dataclasses.Field"):

            class Bad(Aggregate[UUID, PlainSnapshot, StrayState]):
                pass

    def test_aggregates_may_share_a_snapshot_class(self) -> None:
        # Only nestable entities are registered (one snapshot class per entity),
        # so two aggregates can use the same snapshot/state pair.
        class CartCopy(Aggregate[UUID, CartSnapshot, CartState]):
            pass

        snapshot = CartSnapshot(id=uuid4(), customer_id=uuid4())
        assert Cart(snapshot) != CartCopy(snapshot)  # different identity roots


# --- Representation ------------------------------------------------------


class TestRepresentation:
    def test_str_uses_class_name_and_id(self) -> None:
        order = make_order()
        assert str(order) == f"Order({order.id})"

    def test_repr_starts_with_class_and_state(self) -> None:
        assert repr(make_order()).startswith("Order(state=")
