import dataclasses
from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any
from uuid import uuid4

import attrs
import pytest

from fast_ddd.domain.entity import Entity, EntityIdentity
from fast_ddd.domain.flavors.attrs_models import Snapshot, State

# --- Fixtures (e-commerce) -----------------------------------------------
# Snapshot classes are registered globally (one snapshot class per entity),
# so every entity below owns a distinct snapshot class.


@dataclasses.dataclass(frozen=True)
class LineId:
    order_no: int
    line_no: int


@attrs.define(kw_only=True)
class OrderLineState(State[LineId]):
    sku: str
    quantity: int
    price_cache: Decimal | None = None  # state-only: not part of the snapshot


@attrs.frozen(kw_only=True)
class OrderLineSnapshot(Snapshot[LineId]):
    sku: str
    quantity: int


class OrderLine(Entity[LineId, OrderLineSnapshot, OrderLineState]):
    @classmethod
    def new(
        cls, line_no: int = 1, sku: str = "sku-1", quantity: int = 1
    ) -> "OrderLine":
        return cls(OrderLineSnapshot(id=LineId(1, line_no), sku=sku, quantity=quantity))

    @property
    def quantity(self) -> int:
        return self._state.quantity

    def change_quantity(self, quantity: int) -> None:
        self._state.quantity = quantity


class GiftLine(OrderLine):  # inherits the binding and the identity root
    pass


@attrs.define(kw_only=True)
class CouponState(State[int]):
    code: str


@attrs.frozen(kw_only=True)
class CouponSnapshot(Snapshot[int]):
    code: str


class Coupon(Entity[int, CouponSnapshot, CouponState]):
    @classmethod
    def new(cls, id: int = 1, code: str = "SAVE10") -> "Coupon":
        return cls(CouponSnapshot(id=id, code=code))


def _frozen_map(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@attrs.define(kw_only=True)
class BundleState(State[int]):
    lines: list[OrderLine] = attrs.field(factory=list, converter=list)
    coupons: set[Coupon] = attrs.field(factory=set, converter=set)
    lines_by_sku: dict[str, OrderLine] = attrs.field(factory=dict, converter=dict)
    main_line: OrderLine | None = None
    tags: list[str] = attrs.field(factory=list, converter=list)


@attrs.frozen(kw_only=True)
class BundleSnapshot(Snapshot[int]):
    lines: tuple[OrderLineSnapshot, ...] = attrs.field(default=(), converter=tuple)
    coupons: frozenset[CouponSnapshot] = attrs.field(
        default=frozenset(), converter=frozenset
    )
    lines_by_sku: Mapping[str, OrderLineSnapshot] = attrs.field(
        factory=dict, converter=_frozen_map
    )
    main_line: OrderLineSnapshot | None = None
    tags: tuple[str, ...] = attrs.field(default=(), converter=tuple)


class Bundle(Entity[int, BundleSnapshot, BundleState]):
    """An entity that holds other entities in every supported container."""

    @classmethod
    def new(cls, id: int = 1, **fields: Any) -> "Bundle":
        return cls(BundleSnapshot(id=id, **fields))


@attrs.define(kw_only=True)
class AnyIdState(State[object]):
    pass


@attrs.frozen(kw_only=True)
class AnyIdSnapshot(Snapshot[object]):
    pass


class AnyIdThing(Entity[object, AnyIdSnapshot, AnyIdState]):
    pass


@attrs.define(kw_only=True)
class PayloadState(State[int]):
    payload: object = None


@attrs.frozen(kw_only=True)
class PayloadSnapshot(Snapshot[int]):
    payload: object = None


class Payload(Entity[int, PayloadSnapshot, PayloadState]):
    pass


def make_payload(value: object) -> Payload:
    """Immutability is validated when a snapshot reaches an entity."""
    return Payload(PayloadSnapshot(id=1, payload=value))


class Color(Enum):
    RED = 1


# --- Equality ------------------------------------------------------------


class TestEquality:
    def test_equality_ignores_other_fields(self) -> None:
        assert OrderLine.new(sku="a", quantity=1) == OrderLine.new(sku="b", quantity=9)
        assert OrderLine.new(line_no=1) != OrderLine.new(line_no=2)

    def test_value_object_ids_compare_by_value(self) -> None:
        a = OrderLine(OrderLineSnapshot(id=LineId(5, 1), sku="a", quantity=1))
        b = OrderLine(OrderLineSnapshot(id=LineId(5, 1), sku="b", quantity=2))
        assert a == b

    def test_hierarchy_shares_one_identity_space(self) -> None:
        assert OrderLine.new() == GiftLine.new()
        assert GiftLine.new() == OrderLine.new()

    def test_entities_of_different_roots_with_same_id_are_not_equal(self) -> None:
        assert Coupon.new(id=1) != Bundle.new(id=1)

    def test_comparison_with_non_entity_is_false(self) -> None:
        line = OrderLine.new()
        assert line != 1
        assert line != None  # noqa: E711
        assert line != {"id": LineId(1, 1)}

    def test_entity_is_not_equal_to_its_raw_id_or_snapshot(self) -> None:
        line = OrderLine.new()
        assert line != line.id
        assert line != line.to_snapshot()


# --- Hashing -------------------------------------------------------------


class TestHashing:
    def test_hash_combines_identity_root_and_id(self) -> None:
        line = OrderLine.new()
        assert hash(line) == hash((OrderLine, line.id))
        assert hash(GiftLine.new()) == hash((OrderLine, LineId(1, 1)))

    def test_hierarchy_members_share_hash(self) -> None:
        assert hash(OrderLine.new()) == hash(GiftLine.new())

    def test_set_deduplicates_entities_by_identity(self) -> None:
        assert len({OrderLine.new(sku="a"), OrderLine.new(sku="b")}) == 1

    def test_dict_lookup_uses_identity_not_attributes(self) -> None:
        store = {OrderLine.new(quantity=1): "value"}
        assert store[OrderLine.new(quantity=7)] == "value"

    def test_hash_is_stable_after_mutating_state(self) -> None:
        line = OrderLine.new()
        before = hash(line)
        line.change_quantity(99)
        assert hash(line) == before


# --- Identity root -------------------------------------------------------


class TestIdentityRoot:
    def test_root_is_resolved_at_class_definition(self) -> None:
        assert OrderLine._identity_root is OrderLine
        assert GiftLine._identity_root is OrderLine
        assert Entity._identity_root is None
        assert EntityIdentity._identity_root is None

    def test_abstract_base_does_not_merge_its_children(self) -> None:
        @attrs.define(kw_only=True)
        class PartyState(State[int]):
            pass

        @attrs.frozen(kw_only=True)
        class PartySnapshot(Snapshot[int]):
            pass

        class Party(Entity[int, PartySnapshot, PartyState], abstract=True):
            pass

        class Person(Party):
            pass

        class Company(Party):
            pass

        snapshot = PartySnapshot(id=1)
        assert Person(snapshot) != Company(snapshot)
        assert Party._identity_root is None
        assert Person._identity_root is Person

    def test_multiple_identity_roots_are_rejected_at_definition(self) -> None:
        with pytest.raises(TypeError, match="several identity roots"):

            class Mixed(OrderLine, Coupon):  # type: ignore[misc]
                pass

    def test_plain_identity_hierarchy_without_state_machinery(self) -> None:
        class Account(EntityIdentity[int]):
            def __init__(self, id: int) -> None:
                self._id = id

            @property
            def id(self) -> int:  # type: ignore[override]
                return self._id

        class Savings(Account):
            pass

        assert Account(1) == Savings(1)
        assert hash(Account(1)) == hash(Savings(1))
        assert Savings._identity_root is Account


# --- State / id protection -----------------------------------------------


class TestStateAndId:
    def test_state_is_rebuilt_from_snapshot(self) -> None:
        line = OrderLine.new(sku="abc", quantity=3)
        assert line.id == LineId(1, 1)
        assert line._state.sku == "abc"
        assert line._state.quantity == 3

    def test_state_only_fields_use_their_defaults(self) -> None:
        assert OrderLine.new()._state.price_cache is None

    def test_non_id_fields_are_mutable(self) -> None:
        line = OrderLine.new()
        line.change_quantity(5)
        assert line.quantity == 5

    def test_state_id_cannot_be_reassigned(self) -> None:
        line = OrderLine.new()
        with pytest.raises(AttributeError):  # attrs FrozenAttributeError
            # pyrefly: ignore[read-only]
            line._state.id = LineId(9, 9)
        assert line.id == LineId(1, 1)

    def test_entity_id_property_is_read_only(self) -> None:
        with pytest.raises(AttributeError):
            OrderLine.new().id = LineId(9, 9)  # type: ignore[misc]

    def test_str_uses_class_name_and_id(self) -> None:
        coupon = Coupon.new(id=7)
        assert str(coupon) == "Coupon(7)"

    def test_repr_starts_with_class_and_state(self) -> None:
        assert repr(Coupon.new()).startswith("Coupon(state=")

    def test_entity_has_no_invariants_hook(self) -> None:
        # Invariants are an aggregate concern.
        assert not hasattr(Entity, "validate_invariants")
        assert Entity._nestable is True


# --- Id rules ------------------------------------------------------------


class TestIdRules:
    def test_none_id_is_rejected_at_construction(self) -> None:
        with pytest.raises(TypeError, match="must not be None"):
            AnyIdThing(AnyIdSnapshot(id=None))

    def test_unhashable_id_is_rejected_at_construction(self) -> None:
        @attrs.define  # eq=True and not frozen -> __hash__ is None
        class UnhashableId:
            value: int

        with pytest.raises(TypeError, match="must be hashable, got .*UnhashableId"):
            AnyIdThing(AnyIdSnapshot(id=UnhashableId(1)))

    def test_mutable_container_id_is_rejected_as_unhashable(self) -> None:
        with pytest.raises(TypeError, match="must be hashable, got list"):
            AnyIdThing(AnyIdSnapshot(id=[1, 2]))

    def test_non_frozen_dataclass_id_is_rejected(self) -> None:
        @dataclasses.dataclass(unsafe_hash=True)  # hashable, but mutable
        class MutableId:
            value: int

        with pytest.raises(TypeError, match="is a dataclass and must be frozen=True"):
            AnyIdThing(AnyIdSnapshot(id=MutableId(1)))

    def test_identity_equality_id_type_is_rejected(self) -> None:
        class RawId:  # hashable, but equal only by reference
            pass

        with pytest.raises(TypeError, match="uses identity equality"):
            AnyIdThing(AnyIdSnapshot(id=RawId()))

    @pytest.mark.parametrize(
        "valid_id",
        [1, "a", uuid4(), Color.RED, LineId(1, 2), Decimal("1.5"), (1, 2)],
        ids=["int", "str", "uuid", "enum", "frozen-dataclass", "decimal", "tuple"],
    )
    def test_value_like_ids_are_accepted(self, valid_id: object) -> None:
        assert AnyIdThing(AnyIdSnapshot(id=valid_id)).id == valid_id


# --- Snapshot round trip -------------------------------------------------


class TestToSnapshot:
    def test_returns_exact_snapshot_type(self) -> None:
        assert type(OrderLine.new().to_snapshot()) is OrderLineSnapshot

    def test_fresh_entity_round_trips_to_equal_snapshot(self) -> None:
        snapshot = OrderLineSnapshot(id=LineId(1, 1), sku="a", quantity=2)
        assert OrderLine(snapshot).to_snapshot() == snapshot

    def test_snapshot_reflects_current_state(self) -> None:
        line = OrderLine.new(quantity=1)
        line.change_quantity(4)
        assert line.to_snapshot().quantity == 4

    def test_snapshot_can_expose_a_subset_of_state_fields(self) -> None:
        snapshot = OrderLine.new().to_snapshot()
        assert not hasattr(snapshot, "price_cache")
        assert {f.name for f in attrs.fields(type(snapshot))} == {
            "id",
            "sku",
            "quantity",
        }

    def test_state_only_fields_are_reset_on_load(self) -> None:
        line = OrderLine.new()
        line._state.price_cache = Decimal("9.99")
        restored = OrderLine(line.to_snapshot())
        assert restored._state.price_cache is None

    def test_earlier_snapshot_is_not_affected_by_later_changes(self) -> None:
        line = OrderLine.new(quantity=1)
        before = line.to_snapshot()
        line.change_quantity(5)
        assert before.quantity == 1
        assert line.to_snapshot().quantity == 5

    def test_entity_state_is_independent_of_source_snapshot(self) -> None:
        bundle = Bundle.new(tags=("a",))
        snapshot = bundle.to_snapshot()
        bundle._state.tags.append("b")
        assert snapshot.tags == ("a",)

    def test_entities_with_same_id_have_unequal_snapshots_when_data_differs(
        self,
    ) -> None:
        a, b = OrderLine.new(quantity=1), OrderLine.new(quantity=2)
        assert a == b  # identity equality
        assert a.to_snapshot() != b.to_snapshot()  # value equality

    def test_snapshots_hash_by_value(self) -> None:
        a = OrderLine.new(quantity=1).to_snapshot()
        b = OrderLine.new(quantity=1).to_snapshot()
        assert a == b and hash(a) == hash(b)
        assert len({a, b, OrderLine.new(quantity=2).to_snapshot()}) == 2


# --- Nested entities -----------------------------------------------------


def make_bundle() -> Bundle:
    l1, l2 = OrderLine.new(1, "a", 1), OrderLine.new(2, "b", 2)
    snapshot = BundleSnapshot(
        id=1,
        lines=(l1.to_snapshot(), l2.to_snapshot()),
        coupons=frozenset({Coupon.new(1).to_snapshot()}),
        lines_by_sku={"a": l1.to_snapshot()},
        main_line=l2.to_snapshot(),
        tags=("x",),
    )
    return Bundle(snapshot)


class TestNestedEntities:
    def test_snapshot_entities_are_restored_as_entities(self) -> None:
        state = make_bundle()._state
        assert all(type(line) is OrderLine for line in state.lines)
        assert type(state.main_line) is OrderLine
        assert all(type(c) is Coupon for c in state.coupons)
        assert type(state.lines_by_sku["a"]) is OrderLine

    def test_container_kinds_follow_state_converters(self) -> None:
        state = make_bundle()._state
        assert type(state.lines) is list
        assert type(state.coupons) is set
        assert type(state.lines_by_sku) is dict
        assert type(state.tags) is list

    def test_entities_are_converted_to_snapshots(self) -> None:
        snapshot = make_bundle().to_snapshot()
        assert type(snapshot.lines) is tuple
        assert all(type(s) is OrderLineSnapshot for s in snapshot.lines)
        assert type(snapshot.coupons) is frozenset
        assert type(snapshot.lines_by_sku) is MappingProxyType
        assert type(snapshot.lines_by_sku["a"]) is OrderLineSnapshot
        assert type(snapshot.main_line) is OrderLineSnapshot
        assert snapshot.tags == ("x",)

    def test_round_trip_preserves_data(self) -> None:
        bundle = make_bundle()
        first = bundle.to_snapshot()
        assert Bundle(first).to_snapshot() == first

    def test_changes_to_nested_entities_reach_the_snapshot(self) -> None:
        bundle = make_bundle()
        bundle._state.lines[0].change_quantity(42)
        assert bundle.to_snapshot().lines[0].quantity == 42

    def test_earlier_snapshot_keeps_old_nested_data(self) -> None:
        bundle = make_bundle()
        before = bundle.to_snapshot()
        bundle._state.lines[0].change_quantity(42)
        bundle._state.lines.append(OrderLine.new(3))
        assert before.lines[0].quantity == 1
        assert len(before.lines) == 2

    def test_loaded_entities_are_independent_of_the_snapshot(self) -> None:
        snapshot = make_bundle().to_snapshot()
        restored = Bundle(snapshot)
        restored._state.lines[0].change_quantity(42)
        assert snapshot.lines[0].quantity == 1

    def test_nested_state_only_fields_are_reset(self) -> None:
        bundle = make_bundle()
        bundle._state.lines[0]._state.price_cache = Decimal("1")
        restored = Bundle(bundle.to_snapshot())
        assert restored._state.lines[0]._state.price_cache is None

    def test_none_valued_entity_field_round_trips(self) -> None:
        bundle = Bundle.new()
        assert bundle._state.main_line is None
        assert bundle.to_snapshot().main_line is None

    def test_snapshot_type_without_registered_entity_is_kept_as_is(self) -> None:
        @attrs.frozen(kw_only=True)
        class LooseSnapshot(Snapshot[int]):
            pass

        @attrs.define(kw_only=True)
        class HolderState(State[int]):
            loose: object = None

        @attrs.frozen(kw_only=True)
        class HolderSnapshot(Snapshot[int]):
            loose: object = None

        class Holder(Entity[int, HolderSnapshot, HolderState]):
            pass

        loose = LooseSnapshot(id=1)
        assert Holder(HolderSnapshot(id=1, loose=loose))._state.loose is loose


# --- Snapshot immutability -----------------------------------------------


class TestSnapshotImmutability:
    def test_snapshot_fields_cannot_be_reassigned(self) -> None:
        snapshot = OrderLine.new().to_snapshot()
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            snapshot.quantity = 5  # type: ignore[misc]

    @pytest.mark.parametrize(
        "value",
        [
            [1],
            {"a": 1},
            {1},
            bytearray(b"x"),
            ([1],),
            (1, (2, [3])),
            ((1, 2), [3]),
            MappingProxyType({"a": [1]}),
        ],
        ids=[
            "list",
            "dict",
            "set",
            "bytearray",
            "list-in-tuple",
            "deeply-nested",
            "list-in-pair",
            "list-in-mapping-proxy",
        ],
    )
    def test_mutable_containers_are_rejected(self, value: object) -> None:
        with pytest.raises(TypeError, match="mutable"):
            make_payload(value)

    @pytest.mark.parametrize(
        "value",
        [
            None,
            1,
            "text",
            (),
            (1, 2),
            frozenset({1}),
            ((1, 2), (3,)),
            MappingProxyType({"a": 1}),
        ],
        ids=["none", "int", "str", "empty", "tuple", "frozenset", "nested", "mapping"],
    )
    def test_immutable_values_are_accepted(self, value: object) -> None:
        assert make_payload(value)._state.payload == value

    def test_error_message_names_the_offending_path(self) -> None:
        with pytest.raises(TypeError, match=r"PayloadSnapshot\.payload\[1\]"):
            make_payload((1, [2]))
        with pytest.raises(TypeError, match=r"PayloadSnapshot\.payload\['a'\]"):
            make_payload(MappingProxyType({"a": [2]}))

    def test_entity_inside_snapshot_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="holds OrderLine; use its snapshot"):
            make_payload(OrderLine.new())

    def test_entity_nested_in_containers_is_rejected(self) -> None:
        line = OrderLine.new()
        with pytest.raises(TypeError, match=r"payload\[0\] holds OrderLine"):
            make_payload((line,))
        with pytest.raises(TypeError, match=r"payload\['k'\] holds OrderLine"):
            make_payload(MappingProxyType({"k": line}))
        with pytest.raises(TypeError, match="holds OrderLine"):
            make_payload(frozenset({line}))

    def test_state_object_inside_snapshot_is_rejected(self) -> None:
        state = OrderLineState(id=LineId(1, 1), sku="a", quantity=1)
        with pytest.raises(TypeError, match="holds OrderLineState"):
            make_payload(state)

    def test_nested_snapshots_are_accepted_and_restored_as_entities(self) -> None:
        line = OrderLine.new().to_snapshot()
        (restored,) = make_payload((line,))._state.payload  # type: ignore[misc]
        assert type(restored) is OrderLine
        assert restored.to_snapshot() == line


# --- Definition rules ----------------------------------------------------


class TestDefinitionRules:
    def test_custom_eq_is_rejected_at_definition(self) -> None:
        with pytest.raises(TypeError, match="overrides __eq__"):

            class Broken(Entity[int, CouponSnapshot, CouponState], abstract=True):
                def __eq__(self, other: object) -> bool:
                    return True

    def test_custom_hash_is_rejected_at_definition(self) -> None:
        with pytest.raises(TypeError, match="overrides __hash__"):

            class Broken(Entity[int, CouponSnapshot, CouponState], abstract=True):
                def __hash__(self) -> int:
                    return 1

    def test_override_is_rejected_on_plain_identity_base_too(self) -> None:
        with pytest.raises(TypeError, match="overrides __eq__"):

            class Broken(EntityIdentity[int]):
                def __eq__(self, other: object) -> bool:
                    return True

    def test_override_is_rejected_for_subclass_of_concrete_entity(self) -> None:
        with pytest.raises(TypeError, match="overrides __eq__"):

            class Broken(Coupon):
                def __eq__(self, other: object) -> bool:
                    return True


class TestBindingRules:
    def test_unparametrized_entity_is_rejected(self) -> None:
        with pytest.raises(
            TypeError, match="must parametrize its entity base directly"
        ):

            class Bad(Entity):  # type: ignore[type-arg]
                pass

    def test_unresolved_type_variable_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="unresolved"):

            class Bad[S: CouponState](Entity[int, CouponSnapshot, S]):
                pass

    def test_unresolved_type_variable_is_allowed_when_abstract(self) -> None:
        class Generic_[S: CouponState](Entity[int, CouponSnapshot, S], abstract=True):
            pass

        assert Generic_._identity_root is None

    def test_indirect_parametrization_is_not_supported_yet(self) -> None:
        # Documents a known limitation (see the Todo in aggregate.py).
        # Flip this test when TypeVar substitution is implemented.
        class Intermediate[M: Snapshot](Entity[int, M, CouponState], abstract=True):
            pass

        with pytest.raises(
            TypeError, match="must parametrize its entity base directly"
        ):

            class Concrete(Intermediate[CouponSnapshot]):
                pass

    def test_state_type_must_be_an_attrs_state(self) -> None:
        with pytest.raises(TypeError, match="state type must be an attrs class"):

            class Bad(Entity[int, CouponSnapshot, dict]):  # type: ignore[type-var]
                pass

    def test_snapshot_type_must_be_an_attrs_snapshot(self) -> None:
        with pytest.raises(TypeError, match="snapshot type must be an attrs class"):

            class Bad(Entity[int, dict, CouponState]):  # type: ignore[type-var]
                pass

    def test_snapshot_field_missing_on_state_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class ThinState(State[int]):
            pass

        @attrs.frozen(kw_only=True)
        class WideSnapshot(Snapshot[int]):
            total: int

        with pytest.raises(TypeError, match=r"missing fields.*\['total'\]"):

            class Bad(Entity[int, WideSnapshot, ThinState]):
                pass

    def test_required_state_field_missing_on_snapshot_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class WideState(State[int]):
            total: int

        @attrs.frozen(kw_only=True)
        class ThinSnapshot(Snapshot[int]):
            pass

        with pytest.raises(TypeError, match=r"no default.*\['total'\]"):

            class Bad(Entity[int, ThinSnapshot, WideState]):
                pass

    def test_state_only_field_with_init_false_is_accepted(self) -> None:
        @attrs.define(kw_only=True)
        class DerivedState(State[int]):
            cache: int = attrs.field(init=False)

        @attrs.frozen(kw_only=True)
        class PlainSnapshot(Snapshot[int]):
            pass

        class Ok(Entity[int, PlainSnapshot, DerivedState]):
            pass

        assert Ok(PlainSnapshot(id=1)).id == 1

    def test_stray_dataclasses_field_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class StrayState(State[int]):
            tags: list[str] = dataclasses.field(default_factory=list)  # type: ignore[assignment]

        @attrs.frozen(kw_only=True)
        class PlainSnapshot(Snapshot[int]):
            pass

        with pytest.raises(TypeError, match="dataclasses.Field"):

            class Bad(Entity[int, PlainSnapshot, StrayState]):
                pass

    def test_snapshot_class_cannot_be_paired_with_two_entities(self) -> None:
        @attrs.define(kw_only=True)
        class SharedState(State[int]):
            pass

        @attrs.frozen(kw_only=True)
        class SharedSnapshot(Snapshot[int]):
            pass

        class First(Entity[int, SharedSnapshot, SharedState]):
            pass

        with pytest.raises(TypeError, match="already paired with .*First"):

            class Second(Entity[int, SharedSnapshot, SharedState]):
                pass

    def test_subclass_cannot_reuse_the_parents_snapshot_class(self) -> None:
        # A polymorphic child needs its own snapshot class, otherwise a
        # round trip could not tell the two entity classes apart.
        with pytest.raises(TypeError, match="already paired with"):

            class Child(Coupon, Entity[int, CouponSnapshot, CouponState]):  # type: ignore[misc]
                pass

    def test_subclass_inherits_binding(self) -> None:
        assert GiftLine._snapshot_cls is OrderLineSnapshot
        assert GiftLine._state_cls is OrderLineState
        assert isinstance(GiftLine.new().to_snapshot(), OrderLineSnapshot)


# --- Private field names -------------------------------------------------


class TestPrivateFieldNames:
    def test_attrs_private_fields_round_trip(self) -> None:
        # attrs strips the leading underscore from the __init__ keyword; the
        # library uses the field alias, so private fields work.
        @attrs.define(kw_only=True)
        class PrivState(State[int]):
            _secret: str = ""

        @attrs.frozen(kw_only=True)
        class PrivSnapshot(Snapshot[int]):
            _secret: str = ""

        class Priv(Entity[int, PrivSnapshot, PrivState]):
            pass

        entity = Priv(PrivSnapshot(id=1, secret="x"))
        assert entity._state._secret == "x"
        assert entity.to_snapshot()._secret == "x"


# --- Boundary validation and definition rules (adapter-based) -------------


class TestBoundaryValidation:
    def test_wrong_snapshot_type_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="expects a CouponSnapshot"):
            Coupon(OrderLineSnapshot(id=LineId(1, 1), sku="a", quantity=1))  # type: ignore[arg-type]

    def test_state_value_that_cannot_be_frozen_fails_in_to_snapshot(self) -> None:
        payload = make_payload(None)
        payload._state.payload = bytearray(b"x")
        with pytest.raises(TypeError, match="mutable bytearray"):
            payload.to_snapshot()

    def test_non_frozen_attrs_value_object_in_snapshot_is_rejected(self) -> None:
        @attrs.define
        class Money:
            amount: int

        with pytest.raises(
            TypeError, match=r"holds a non-frozen Money; declare it with frozen=True"
        ):
            make_payload(Money(1))

    def test_non_frozen_dataclass_value_object_in_snapshot_is_rejected(self) -> None:
        @dataclasses.dataclass
        class Money:
            amount: int

        with pytest.raises(TypeError, match="holds a non-frozen Money"):
            make_payload(Money(1))

    def test_frozen_value_object_holding_a_mutable_value_is_rejected(self) -> None:
        @dataclasses.dataclass(frozen=True)
        class Box:
            items: list[int]

        with pytest.raises(TypeError, match=r"payload\.items holds a mutable list"):
            make_payload(Box([1]))

    def test_frozen_value_objects_are_accepted_and_shared_not_copied(self) -> None:
        @dataclasses.dataclass(frozen=True)
        class Money:
            amount: int

        @attrs.frozen
        class Tag:
            label: str

        money, tag = Money(5), Tag("x")
        payload = make_payload((money, tag))
        assert payload._state.payload[0] is money  # type: ignore[index]
        assert payload._state.payload[1] is tag  # type: ignore[index]


class TestIdFrozenness:
    def test_non_frozen_attrs_id_is_rejected(self) -> None:
        @attrs.define(unsafe_hash=True)  # hashable, but mutable
        class MutableId:
            value: int

        with pytest.raises(
            TypeError, match="is an attrs class and must be frozen=True"
        ):
            AnyIdThing(AnyIdSnapshot(id=MutableId(1)))

    def test_frozen_attrs_id_is_accepted(self) -> None:
        @attrs.frozen
        class AttrsId:
            value: int

        assert AnyIdThing(AnyIdSnapshot(id=AttrsId(1))).id == AttrsId(1)


class TestAdapterDefinitionRules:
    def test_plain_class_is_not_a_valid_state_or_snapshot(self) -> None:
        class Plain:
            id: int

        with pytest.raises(
            TypeError, match="state type must be an attrs class or a dataclass"
        ):

            class Bad(Entity[int, CouponSnapshot, Plain]):  # type: ignore[type-var]
                pass

    def test_non_frozen_attrs_snapshot_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class LooseSnapshot:
            id: int

        @attrs.define(kw_only=True)
        class LooseState:
            id: int

        with pytest.raises(
            TypeError,
            match=r"snapshot type LooseSnapshot must be frozen \(frozen=True\)",
        ):

            class Bad(Entity[int, LooseSnapshot, LooseState]):
                pass

    def test_non_frozen_dataclass_snapshot_is_rejected(self) -> None:
        @dataclasses.dataclass
        class LooseSnapshot:
            id: int

        @dataclasses.dataclass
        class LooseState:
            id: int

        with pytest.raises(TypeError, match="must be frozen"):

            class Bad(Entity[int, LooseSnapshot, LooseState]):
                pass

    def test_missing_id_field_is_rejected(self) -> None:
        @attrs.define(kw_only=True)
        class NoIdState:
            name: str = ""

        @attrs.frozen(kw_only=True)
        class NoIdSnapshot:
            name: str = ""

        with pytest.raises(TypeError, match="state type must define an `id` field"):

            # pyrefly: ignore[bad-specialization]
            class Bad(Entity[int, NoIdSnapshot, NoIdState]):  # noqa
                pass

    def test_abstract_entity_does_not_claim_the_snapshot(self) -> None:
        @attrs.define(kw_only=True)
        class ClaimState(State[int]):
            pass

        @attrs.frozen(kw_only=True)
        class ClaimSnapshot(Snapshot[int]):
            pass

        class AbstractBase(Entity[int, ClaimSnapshot, ClaimState], abstract=True):
            pass

        class Concrete(Entity[int, ClaimSnapshot, ClaimState]):  # no "already paired"
            pass

        assert AbstractBase._identity_root is None
        assert Concrete._identity_root is Concrete
