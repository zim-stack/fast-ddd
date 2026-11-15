# Entities and value objects

An order needs lines. In this chapter you add them, and in doing so meet the two
kinds of objects that live inside an aggregate: **entities**, which have an
identity, and **value objects**, which do not.

The code uses dataclasses. With attrs, swap `DataclassState` and
`DataclassSnapshot` for `State` and `Snapshot` as in
[chapter 1](modeling-the-domain.md).

## Entity or value object?

| | Entity | Value object |
|---|---|---|
| Defined by | its **identity** (an id) | its **values** |
| Two with equal fields | still different if the ids differ | the same thing |
| Changes over time | yes, and stays the same entity | never; you create a new one |
| Here | `OrderLine` | `Money` |

Ask: "if I changed this field, would it still be *the same thing*?" A line whose
quantity goes from 2 to 3 is still line number 1 of the order: an entity. An
amount of 10 euros that becomes 12 euros is a different amount: a value object.

## A value object: `Money`

A value object is just a **frozen** class. Prices should not be plain numbers,
because a number does not know its currency:

```python
from dataclasses import dataclass, field

from {{ import_name }}.domain.exceptions import DomainError


class OrderError(DomainError):
    """A rule of the ordering domain was violated."""


@dataclass(frozen=True)
class Money:
    amount: int  # minor units, e.g. cents
    currency: str

    def __add__(self, other: "Money") -> "Money":
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def times(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)

    def _ensure_same_currency(self, other: "Money") -> None:
        if other.currency != self.currency:
            raise OrderError(f"currency mismatch: {self.currency} vs {other.currency}")
```

`OrderError` is a **domain error**: a business rule was broken. Giving it its
own type lets callers (the API layer, for example) tell it apart from a bug.

Because `Money` is frozen it can be used safely anywhere: inside state, inside
snapshots, even as an id. The library requires snapshots to be deeply immutable,
and a frozen value object satisfies that.

## An inner entity: `OrderLine`

An entity has the same three-part shape as the aggregate: a state, a snapshot
and the entity class. It is declared with `Entity` instead of `Aggregate`:

```python
from {{ import_name }}.domain.entity import Entity
from {{ import_name }}.domain.flavors.dataclass_models import (
    DataclassSnapshot,
    DataclassState,
)


@dataclass(kw_only=True)
class OrderLineState(DataclassState[int]):
    sku: str
    quantity: int
    unit_price: Money


@dataclass(frozen=True, kw_only=True)
class OrderLineSnapshot(DataclassSnapshot[int]):
    sku: str
    quantity: int
    unit_price: Money


class OrderLine(Entity[int, OrderLineSnapshot, OrderLineState]):
    @classmethod
    def create(
        cls, line_no: int, sku: str, quantity: int, unit_price: Money
    ) -> "OrderLine":
        cls._ensure_positive(quantity)
        return cls(
            OrderLineSnapshot(
                id=line_no, sku=sku, quantity=quantity, unit_price=unit_price
            )
        )

    @property
    def sku(self) -> str:
        return self._state.sku

    @property
    def quantity(self) -> int:
        return self._state.quantity

    @property
    def subtotal(self) -> Money:
        return self._state.unit_price.times(self._state.quantity)

    def change_quantity(self, quantity: int) -> None:
        self._ensure_positive(quantity)
        self._state.quantity = quantity

    @staticmethod
    def _ensure_positive(quantity: int) -> None:
        if quantity <= 0:
            raise OrderError("quantity must be positive")
```

The line's identity is `line_no`, a plain `int`. Two things follow:

- Line numbers are only unique **within one order**. Line 1 of order A and line 1
  of order B are equal as far as the library is concerned, so never mix lines
  from different orders in one set or dictionary. If you ever need a globally
  unique line id, use a compound id such as `(order_id, line_no)`.
- Lines are not loaded or saved on their own. You always reach them through the
  order, which is the point of the next section.

## Putting lines inside the order

The order owns its lines. Add them to the state and to the snapshot, then give
the aggregate commands that use them:

```python
from enum import StrEnum
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    CANCELLED = "cancelled"


@dataclass(kw_only=True)
class OrderState(DataclassState[UUID]):
    customer_id: UUID
    currency: str = "EUR"
    status: OrderStatus = OrderStatus.DRAFT
    lines: list[OrderLine] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class OrderSnapshot(DataclassSnapshot[UUID]):
    customer_id: UUID
    currency: str = "EUR"
    status: OrderStatus = OrderStatus.DRAFT
    lines: tuple[OrderLineSnapshot, ...] = ()


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    @classmethod
    def create(cls, customer_id: UUID, currency: str = "EUR") -> "Order":
        return cls(
            OrderSnapshot(id=uuid4(), customer_id=customer_id, currency=currency)
        )

    @property
    def customer_id(self) -> UUID:
        return self._state.customer_id

    @property
    def status(self) -> OrderStatus:
        return self._state.status

    @property
    def lines(self) -> tuple[OrderLine, ...]:
        return tuple(self._state.lines)

    @property
    def total(self) -> Money:
        total = Money(0, self._state.currency)
        for line in self._state.lines:
            total = total + line.subtotal
        return total

    def add_line(self, sku: str, quantity: int, unit_price: Money) -> OrderLine:
        if unit_price.currency != self._state.currency:
            raise OrderError(
                f"order is in {self._state.currency}, got {unit_price.currency}"
            )
        line_no = max((line.id for line in self._state.lines), default=0) + 1
        line = OrderLine.create(line_no, sku, quantity, unit_price)
        self._state.lines.append(line)
        return line
```

Look at how the two sides of the boundary differ:

| | In the state | In the snapshot |
|---|---|---|
| Lines | `list[OrderLine]`, live entities you can call methods on | `tuple[OrderLineSnapshot, ...]`, frozen data |
| Price | `Money` | the same `Money` (it is frozen, so it is shared safely) |

You do not write any conversion code. When you call `to_snapshot()`, every
`OrderLine` becomes an `OrderLineSnapshot` and the list becomes a tuple. When
you build an order from a snapshot, the snapshots become entities again, and the
**annotation on the state field** (`list[OrderLine]`) decides that you get a
`list` back.

!!! note "Reach inner entities through the root"
    `order.lines` returns the entities so you can read them, but changes should
    go through the order's methods (`add_line`, and in the next chapter
    `remove_line`). The aggregate root is the single door into the cluster.

## Try it

```python
order = Order.create(customer_id=uuid4())
order.add_line("book", 2, Money(1500, "EUR"))
order.add_line("pen", 1, Money(250, "EUR"))

assert order.total == Money(3250, "EUR")  # value objects compare by value

snapshot = order.to_snapshot()
assert isinstance(snapshot.lines, tuple)
assert [line.sku for line in snapshot.lines] == ["book", "pen"]

restored = Order(snapshot)
assert isinstance(restored.lines[0], OrderLine)  # snapshots became entities again
assert restored.total == order.total
```

An entity is compared by identity, a value object by value:

```python
a = OrderLine.create(1, "book", 1, Money(1500, "EUR"))
b = OrderLine.create(1, "pen", 9, Money(250, "EUR"))
assert a == b  # same id: the same line, whatever the fields say
assert Money(100, "EUR") != Money(100, "USD")  # different values: different things
```

## Test it

```python
import pytest


def test_the_total_adds_up_all_lines() -> None:
    order = Order.create(customer_id=uuid4())
    order.add_line("book", 2, Money(1500, "EUR"))
    order.add_line("pen", 1, Money(250, "EUR"))

    assert order.total == Money(3250, "EUR")


def test_lines_get_consecutive_numbers() -> None:
    order = Order.create(customer_id=uuid4())
    first = order.add_line("book", 1, Money(1500, "EUR"))
    second = order.add_line("pen", 1, Money(250, "EUR"))

    assert (first.id, second.id) == (1, 2)


def test_lines_must_use_the_order_currency() -> None:
    order = Order.create(customer_id=uuid4(), currency="EUR")

    with pytest.raises(OrderError, match="order is in EUR"):
        order.add_line("book", 1, Money(1500, "USD"))


def test_quantity_must_be_positive() -> None:
    order = Order.create(customer_id=uuid4())

    with pytest.raises(OrderError, match="quantity must be positive"):
        order.add_line("book", 0, Money(1500, "EUR"))


def test_lines_survive_a_round_trip_through_a_snapshot() -> None:
    order = Order.create(customer_id=uuid4())
    order.add_line("book", 2, Money(1500, "EUR"))
    snapshot = order.to_snapshot()

    assert Order(snapshot).to_snapshot() == snapshot


def test_an_earlier_snapshot_is_not_changed_by_later_edits() -> None:
    order = Order.create(customer_id=uuid4())
    line = order.add_line("book", 1, Money(1500, "EUR"))
    before = order.to_snapshot()

    line.change_quantity(5)

    assert before.lines[0].quantity == 1
    assert order.to_snapshot().lines[0].quantity == 5
```

## Recap

- **Entities** have an identity and a lifecycle; **value objects** are frozen
  and compared by value.
- An inner entity is declared like the aggregate: state, snapshot, and a class
  deriving from `Entity`.
- The state holds live entities in a `list`; the snapshot holds frozen
  snapshots in a `tuple`. The library converts both ways, guided by the state
  field's annotation.
- Inner entities are reached through the aggregate root.

Next: [Aggregates and invariants](aggregates-and-invariants.md). Right now
nothing stops you from adding a line to a cancelled order.
