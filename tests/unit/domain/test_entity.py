from dataclasses import FrozenInstanceError, dataclass
from typing import Self
from uuid import UUID, uuid4

import pytest

from fast_ddd.domain.entity import Entity, entity

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
    def test_hash_is_derived_from_id(self) -> None:
        oid = OrderId.new()
        line = OrderLine(id=oid, sku="A", quantity=1)
        assert hash(line) == hash(oid)

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
    def test_entity_is_frozen(self) -> None:
        customer = Customer(id=1, name="a")
        with pytest.raises(FrozenInstanceError):
            customer.name = "b"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            customer.id = 2  # type: ignore[misc]

    def test_fields_are_keyword_only(self) -> None:
        with pytest.raises(TypeError):
            Customer(1, name="a")  # type: ignore[misc]

    def test_id_is_required(self) -> None:
        with pytest.raises(TypeError):
            Customer(name="a")  # type: ignore[call-arg]

    def test_unhashable_id_is_rejected_at_construction(self) -> None:
        @dataclass(frozen=True, kw_only=True, eq=False)
        class BadEntity(Entity[list]):  # type: ignore[type-var]
            pass

        with pytest.raises(TypeError, match="must be hashable, got list"):
            BadEntity(id=[1, 2, 3])


# --- Definition rules ----------------------------------------------------


class TestDefinitionRules:
    def test_field_based_dataclass_eq_is_rejected(self) -> None:
        # frozen=True with eq left at its default generates field-based __eq__ and __hash__.
        @dataclass(frozen=True, kw_only=True)
        class Broken(Entity[int]):
            name: str = ""

        with pytest.raises(TypeError, match="Broken overrides __eq__ and __hash__"):
            Broken(id=1)

    def test_custom_eq_in_body_is_rejected_on_instantiation(self) -> None:
        @dataclass(frozen=True, kw_only=True, eq=False)
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
