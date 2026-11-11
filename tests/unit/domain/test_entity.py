from dataclasses import dataclass
from enum import Enum
from typing import Self
from uuid import UUID, uuid4

import pytest

from fast_ddd.domain.entity import BaseEntity, Entity, entity

# --- Fixtures ------------------------------------------------------------


@dataclass(frozen=True)
class OrderId:
    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())


@entity
class OrderLine(Entity[OrderId]):
    sku: str
    quantity: int


@entity
class Customer(Entity[int]):
    name: str = ""


@entity
class PremiumCustomer(Customer):
    tier: str = "gold"


@entity
class Guest(Customer):
    pass


@entity
class Product(Entity[int]):
    name: str


# --------


@dataclass(eq=False)
class Account(BaseEntity[int]):  # direct BaseEntity subclass, not under Entity
    id: int


@dataclass(eq=False)
class Savings(Account):
    pass


@dataclass(eq=False)
class Party(Entity[int], abstract=True):  # abstract intermediate base
    pass


@entity
class Person(Party):
    pass


@entity
class Company(Party):
    pass


class Color(Enum):
    RED = 1


# --- Equality ------------------------------------------------------------


class TestEquality:
    def test_equality_ignores_other_fields(self) -> None:
        assert Customer(id=1, name="A") == Customer(id=1, name="B")
        assert Customer(id=1) != Customer(id=2)

    def test_value_object_ids_compare_by_value(self) -> None:
        value = uuid4()
        a = OrderLine(id=OrderId(value), sku="A", quantity=1)
        b = OrderLine(id=OrderId(value), sku="B", quantity=2)
        assert a == b

    def test_hierarchy_shares_one_identity_space(self) -> None:
        assert Customer(id=1) == PremiumCustomer(id=1)
        assert PremiumCustomer(id=1) == Customer(id=1)

    def test_siblings_under_same_root_with_same_id_are_equal(self) -> None:
        assert Guest(id=1, name="a") == PremiumCustomer(id=1)

    def test_equality_is_transitive_within_hierarchy(self) -> None:
        a, b, c = Customer(id=1), PremiumCustomer(id=1), Guest(id=1)
        assert a == b and b == c and a == c

    def test_entities_of_different_roots_with_same_id_are_not_equal(self) -> None:
        assert Customer(id=1, name="x") != Product(id=1, name="x")

    def test_comparison_with_non_entity_is_false(self) -> None:
        customer = Customer(id=1, name="a")
        assert customer != 1
        assert customer != None  # noqa: E711
        assert customer != {"id": 1}

    def test_entity_is_not_equal_to_its_raw_id(self) -> None:
        oid = OrderId.new()
        line = OrderLine(id=oid, sku="A", quantity=1)
        assert line != oid


# --- Hashing -------------------------------------------------------------


class TestHashing:
    def test_hash_combines_identity_root_and_id(self) -> None:
        oid = OrderId.new()
        assert hash(OrderLine(id=oid, sku="A", quantity=1)) == hash((OrderLine, oid))
        assert hash(PremiumCustomer(id=1)) == hash((Customer, 1))

    def test_hierarchy_members_share_hash(self) -> None:
        assert hash(Customer(id=1)) == hash(PremiumCustomer(id=1))
        assert hash(Guest(id=1)) == hash(PremiumCustomer(id=1))

    def test_set_deduplicates_entities_by_identity(self) -> None:
        oid = OrderId.new()
        a = OrderLine(id=oid, sku="A", quantity=1)
        b = OrderLine(id=oid, sku="B", quantity=2)
        assert len({a, b}) == 1

    def test_dict_lookup_uses_identity_not_attributes(self) -> None:
        store = {Customer(id=1, name="old"): "value"}
        assert store[Customer(id=1, name="new")] == "value"


# --- Construction and immutability ---------------------------------------


class TestConstruction:
    def test_id_is_immutable_but_other_fields_are_not(self) -> None:
        customer = Customer(id=1, name="a")
        customer.name = "b"
        assert customer.name == "b"
        with pytest.raises(AttributeError, match="immutable"):
            customer.id = 2

    def test_fields_are_keyword_only(self) -> None:
        with pytest.raises(TypeError):
            Customer(1, name="a")  # type: ignore[misc]

    def test_id_is_required(self) -> None:
        with pytest.raises(TypeError):
            Customer(name="a")  # type: ignore[call-arg]

    def test_unhashable_id_is_rejected_at_construction(self) -> None:
        @dataclass(eq=False)
        class BadEntity(Entity[list]):  # type: ignore[type-var]
            pass

        with pytest.raises(TypeError, match="must be hashable, got list"):
            BadEntity(id=[1, 2, 3])


# --- Definition rules ----------------------------------------------------


class TestDefinitionRules:
    def test_field_based_dataclass_eq_is_rejected(self) -> None:
        @dataclass()
        class Broken(Entity[int]):
            name: str = ""

        with pytest.raises(TypeError, match="Broken overrides __eq__ and __hash__"):
            Broken(id=1)

    def test_custom_eq_in_body_is_rejected_on_instantiation(self) -> None:
        @dataclass(eq=False)
        class Broken(Entity[int]):
            def __eq__(self, other: object) -> bool:
                return True

            __hash__ = Entity.__hash__

        with pytest.raises(TypeError, match="overrides __eq__"):
            Broken(id=1)

    def test_custom_eq_is_rejected_by_decorator_at_definition_time(self) -> None:
        with pytest.raises(TypeError, match="overrides __eq__"):

            @entity
            class Broken(Entity[int]):
                def __eq__(self, other: object) -> bool:
                    return True


# -- Identity rules -----------------------------------------------------


class TestIdentityRoot:
    def test_base_entity_hierarchy_shares_identity_space(self) -> None:
        assert Account(id=1) == Savings(id=1)  # was the fallback bug
        assert hash(Account(id=1)) == hash(Savings(id=1))

    def test_abstract_base_does_not_merge_its_children(self) -> None:
        assert Person(id=1) != Company(id=1)

    def test_root_is_resolved_at_class_definition(self) -> None:
        assert Customer._identity_root is Customer
        assert PremiumCustomer._identity_root is Customer
        assert Entity._identity_root is None

    def test_multiple_identity_roots_are_rejected_at_definition(self) -> None:
        with pytest.raises(TypeError, match="several identity roots"):

            class Mixed(Customer, Product):  # type: ignore[misc]
                pass


class TestIdRules:
    def test_none_id_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="must not be None"):
            Customer(id=None)  # type: ignore[arg-type]

    def test_id_cannot_be_reassigned_or_deleted(self) -> None:
        customer = Customer(id=1)
        with pytest.raises(AttributeError, match="immutable"):
            customer.id = 2
        with pytest.raises(AttributeError, match="cannot be deleted"):
            del customer.id
        assert customer.id == 1

    def test_hash_is_stable_after_mutating_other_fields(self) -> None:
        customer = Customer(id=1, name="a")
        before = hash(customer)
        customer.name = "b"
        assert hash(customer) == before

    def test_non_frozen_dataclass_id_is_rejected(self) -> None:
        @dataclass(unsafe_hash=True)  # hashable, but mutable
        class MutableId:
            value: int

        @entity
        class Thing(Entity[MutableId]):
            pass

        with pytest.raises(TypeError, match="must be frozen=True"):
            Thing(id=MutableId(1))

    def test_identity_equality_id_type_is_rejected(self) -> None:
        class RawId:  # hashable, but equality is by reference
            def __init__(self, value: int) -> None:
                self.value = value

        @entity
        class Thing(Entity[RawId]):
            pass

        with pytest.raises(TypeError, match="uses identity equality"):
            Thing(id=RawId(1))

    @pytest.mark.parametrize("valid_id", [1, "a", uuid4(), Color.RED, OrderId.new()])
    def test_value_like_ids_are_accepted(self, valid_id: object) -> None:
        @entity
        class Thing(Entity[object]):  # type: ignore[type-var]
            pass

        assert Thing(id=valid_id).id == valid_id
