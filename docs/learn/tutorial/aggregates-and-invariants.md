# Aggregates and invariants

So far the order is a bag of data with a couple of checks. In this chapter it
becomes a real **aggregate**: it decides which changes are allowed, it refuses to
end up in an inconsistent state, and it announces what happened.

## What an aggregate is for

An aggregate is a **consistency boundary**: a cluster of objects (here the order
and its lines) that must always be consistent with each other, and that is
changed as one unit. Three consequences shape the code:

1. **Commands decide.** Every change goes through a method on the aggregate root,
   and that method decides whether the change is allowed.
2. **Invariants always hold.** Some rules must be true whatever happened, for
   example "a placed order has at least one line". The aggregate checks them
   before it hands out a snapshot, so an inconsistent order can never be stored.
3. **Events announce what happened.** When something business-relevant occurs,
   the aggregate records a domain event. Other parts of the system react to it.

## Domain events

An event is a fact in the past tense, so it is immutable. Plain frozen
dataclasses do the job:

```python
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class OrderPlaced:
    order_id: UUID
    total: Money


@dataclass(frozen=True)
class OrderCancelled:
    order_id: UUID
    reason: str
```

!!! note
    If your project defines a `DomainEvent` base class, derive your events from
    it. The aggregate records and returns whatever events you give it.

## Commands and invariants

Here is the order with its full behavior. New code is marked with `# new`:

```python
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

    # --- Commands ---------------------------------------------------------

    def add_line(self, sku: str, quantity: int, unit_price: Money) -> OrderLine:
        self._ensure_draft()  # new
        if unit_price.currency != self._state.currency:
            raise OrderError(
                f"order is in {self._state.currency}, got {unit_price.currency}"
            )
        if any(line.sku == sku for line in self._state.lines):  # new
            raise OrderError(f"{sku} is already on the order")
        line_no = max((line.id for line in self._state.lines), default=0) + 1
        line = OrderLine.create(line_no, sku, quantity, unit_price)
        self._state.lines.append(line)
        return line

    def remove_line(self, line_no: int) -> None:  # new
        self._ensure_draft()
        remaining = [line for line in self._state.lines if line.id != line_no]
        if len(remaining) == len(self._state.lines):
            raise OrderError(f"there is no line {line_no}")
        self._state.lines = remaining

    def place(self) -> None:  # new
        self._ensure_draft()
        if not self._state.lines:
            raise OrderError("cannot place an empty order")
        self._state.status = OrderStatus.PLACED
        self.record_event(OrderPlaced(order_id=self.id, total=self.total))

    def cancel(self, reason: str) -> None:  # new
        if self._state.status is OrderStatus.CANCELLED:
            raise OrderError("order is already cancelled")
        self._state.status = OrderStatus.CANCELLED
        self.record_event(OrderCancelled(order_id=self.id, reason=reason))

    # --- Invariants -------------------------------------------------------

    def validate_invariants(self) -> None:  # new
        skus = [line.sku for line in self._state.lines]
        if len(skus) != len(set(skus)):
            raise OrderError("an order has at most one line per product")
        if self._state.status is OrderStatus.PLACED and not self._state.lines:
            raise OrderError("a placed order needs at least one line")

    def _ensure_draft(self) -> None:  # new
        if self._state.status is not OrderStatus.DRAFT:
            raise OrderError(
                f"order is {self._state.status}; only a draft order can change"
            )
```

Two kinds of rule appear here, and it helps to keep them apart:

| | Where | Answers | Example |
|---|---|---|---|
| **Guard** | inside a command | "may I do *this* now?" | you cannot add a line to a placed order |
| **Invariant** | `validate_invariants` | "is the order in a valid state *at all*?" | a placed order has at least one line |

Guards give precise error messages at the moment of the mistake. Invariants are
the safety net behind them: they hold even if a bug in a command, or code you
add later, forgets a guard. The aggregate runs `validate_invariants()` at the
start of every `to_snapshot()`, so an order that breaks a rule can never be
turned into something you store:

```python
# raises OrderError
order = Order.create(customer_id=uuid4())
order._state.status = OrderStatus.PLACED  # bypassing place(): what a bug looks like
order.to_snapshot()  # OrderError: a placed order needs at least one line
```

!!! warning "Do not touch `_state` from outside"
    The example above reaches into `_state` only to show the safety net working.
    Application code should call commands such as `place()`.

Notice that the lines' own rule ("quantity must be positive") lives in
`OrderLine`, while the rule that spans several lines ("at most one line per
product") lives in the order. That is the dividing line: an inner entity guards
itself, and the aggregate root guards everything that involves more than one
object.

## Domain events in action

Commands record events; the caller collects them. The usual order is: persist
first, then publish.

```python
order = Order.create(customer_id=uuid4())
order.add_line("book", 2, Money(1500, "EUR"))
order.place()

snapshot = order.to_snapshot()  # 1. persist this ...
events = order.pull_domain_events()  # 2. ... then publish these

assert events == [OrderPlaced(order_id=order.id, total=Money(3000, "EUR"))]
assert order.pull_domain_events() == []  # pulling clears the list
```

Events are **not** part of the snapshot. An order rebuilt from a snapshot starts
with no pending events, because the events belong to the change that just
happened, not to the order's stored state:

```python
assert Order(snapshot).pull_domain_events() == []
```

## Test it

```python
import pytest


def make_draft_order() -> Order:
    order = Order.create(customer_id=uuid4())
    order.add_line("book", 2, Money(1500, "EUR"))
    return order


def test_placing_an_order_records_an_event() -> None:
    order = make_draft_order()

    order.place()

    assert order.status is OrderStatus.PLACED
    assert order.pull_domain_events() == [
        OrderPlaced(order_id=order.id, total=Money(3000, "EUR"))
    ]


def test_an_empty_order_cannot_be_placed() -> None:
    order = Order.create(customer_id=uuid4())

    with pytest.raises(OrderError, match="empty order"):
        order.place()


def test_a_placed_order_cannot_change() -> None:
    order = make_draft_order()
    order.place()

    with pytest.raises(OrderError, match="only a draft order can change"):
        order.add_line("pen", 1, Money(250, "EUR"))


def test_a_product_can_only_appear_once() -> None:
    order = make_draft_order()

    with pytest.raises(OrderError, match="already on the order"):
        order.add_line("book", 1, Money(1500, "EUR"))


def test_a_line_can_be_removed_while_the_order_is_a_draft() -> None:
    order = make_draft_order()
    order.add_line("pen", 1, Money(250, "EUR"))

    order.remove_line(1)

    assert [line.sku for line in order.lines] == ["pen"]


def test_an_order_can_be_cancelled_once() -> None:
    order = make_draft_order()

    order.cancel("changed my mind")

    assert order.pull_domain_events() == [
        OrderCancelled(order_id=order.id, reason="changed my mind")
    ]
    with pytest.raises(OrderError, match="already cancelled"):
        order.cancel("again")


def test_a_snapshot_is_never_taken_from_an_inconsistent_order() -> None:
    order = Order.create(customer_id=uuid4())
    order._state.status = OrderStatus.PLACED  # simulate a bug in a command

    with pytest.raises(OrderError, match="at least one line"):
        order.to_snapshot()


def test_rebuilding_an_order_does_not_replay_events() -> None:
    order = make_draft_order()
    order.place()

    assert Order(order.to_snapshot()).pull_domain_events() == []
```

## Recap

- An aggregate is a **consistency boundary**: all changes go through its
  commands, and the root guards everything that spans several objects.
- **Guards** reject a change at the moment it is attempted. **Invariants**,
  checked in `validate_invariants()` before every snapshot, guarantee the
  aggregate is never stored in an invalid state.
- Commands record **domain events**. Persist the snapshot, then publish the
  events you pulled.

You now have a complete domain model that runs and is tested without a
database. The next chapters connect it to the world:
[persistence mapping](persistence-mapping.md),
[repositories](repositories.md) and the [unit of work](unit-of-work.md).
