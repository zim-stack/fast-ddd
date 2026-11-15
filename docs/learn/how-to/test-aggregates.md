# Test aggregates

Domain objects are plain Python, so testing them needs no database, no mocks and
no framework. This guide collects the patterns that keep those tests short and
resilient to refactoring.

The examples use the `Order` aggregate from the
[tutorial](../tutorial/aggregates-and-invariants.md), with `OrderLine`, `Money`
and `OrderError`.

## Build aggregates from snapshots

An aggregate is built from a snapshot, so a snapshot is the natural way to put
one into any state you want to test. Wrap it in a small helper:

```python
import dataclasses

import pytest


def line_snapshot(
    line_no: int, sku: str, quantity: int = 1, cents: int = 100
) -> OrderLineSnapshot:
    return OrderLineSnapshot(
        id=line_no,
        sku=sku,
        quantity=quantity,
        unit_price=Money(cents, "EUR"),
    )


def make_order(
    *,
    status: OrderStatus = OrderStatus.DRAFT,
    lines: tuple[OrderLineSnapshot, ...] = (),
) -> Order:
    return Order(
        OrderSnapshot(id=uuid4(), customer_id=uuid4(), status=status, lines=lines)
    )
```

Now a test can start from "a placed order with one line" without replaying the
commands that would normally get it there:

```python
def test_a_placed_order_can_be_cancelled() -> None:
    order = make_order(status=OrderStatus.PLACED, lines=(line_snapshot(1, "book"),))

    order.cancel("out of stock")

    assert order.status is OrderStatus.CANCELLED
```

!!! tip
    Keep the helper's defaults boring and only pass what the test is about.
    Readers should see at a glance which detail matters.

## Assert through the public surface

Check results through properties and through the **snapshot**, not through
`_state`. The snapshot is the aggregate's stable, public description of itself,
so tests written against it survive refactoring of the internals:

```python
def test_adding_a_line_shows_up_in_the_snapshot() -> None:
    order = make_order()

    order.add_line("book", 2, Money(1500, "EUR"))

    snapshot = order.to_snapshot()
    assert [(line.sku, line.quantity) for line in snapshot.lines] == [("book", 2)]
```

Because snapshots are frozen dataclasses (or attrs classes), you can also compare
them whole:

```python
def test_cancelling_changes_only_the_status() -> None:
    order = make_order(lines=(line_snapshot(1, "book"),))
    before = order.to_snapshot()

    order.cancel("changed my mind")

    assert order.to_snapshot() == dataclasses.replace(
        before, status=OrderStatus.CANCELLED
    )
```

For attrs snapshots use `attrs.evolve` instead of `dataclasses.replace`.

## Test commands: the happy path and each rule

One test per rule keeps failures readable. Name the test after the rule, and
parametrize when the same rule has several triggers:

```python
@pytest.mark.parametrize("status", [OrderStatus.PLACED, OrderStatus.CANCELLED])
def test_lines_cannot_change_unless_the_order_is_a_draft(status: OrderStatus) -> None:
    order = make_order(status=status, lines=(line_snapshot(1, "book"),))

    with pytest.raises(OrderError, match="only a draft order can change"):
        order.add_line("pen", 1, Money(250, "EUR"))
```

Assert on the **domain error type** (and a fragment of the message when several
rules share a type), not on a generic `Exception`.

## Test invariants as a safety net

Guards in commands are tested through the commands. Invariants are different:
they exist for the case where a command is wrong or missing. To test one, put the
aggregate into the forbidden state directly, which a snapshot lets you do, and
check that taking a snapshot refuses it:

```python
def test_a_placed_order_without_lines_is_never_stored() -> None:
    order = make_order(status=OrderStatus.PLACED)  # no lines: forbidden

    with pytest.raises(OrderError, match="at least one line"):
        order.to_snapshot()
```

!!! note
    Invariants are checked when you **take** a snapshot, not when you build an
    aggregate from one. That is why the test above can construct the forbidden
    order and then expect `to_snapshot()` to fail.

## Test domain events

Events are returned by `pull_domain_events()`, which also clears them. Compare
the whole list, since events are frozen dataclasses with value equality:

```python
def test_placing_an_order_announces_it() -> None:
    order = make_order(lines=(line_snapshot(1, "book", quantity=2, cents=1500),))

    order.place()

    assert order.pull_domain_events() == [
        OrderPlaced(order_id=order.id, total=Money(3000, "EUR"))
    ]


def test_a_failed_command_records_nothing() -> None:
    order = make_order()  # an empty draft

    with pytest.raises(OrderError):
        order.place()

    assert order.pull_domain_events() == []
```

The second test is worth having for every command: a rejected change must not
leave an event behind.

## Test inner entities directly

An inner entity can be tested on its own. It has its own rules and needs no
aggregate around it:

```python
def test_a_line_rejects_a_non_positive_quantity() -> None:
    line = OrderLine.create(1, "book", 1, Money(1500, "EUR"))

    with pytest.raises(OrderError, match="quantity must be positive"):
        line.change_quantity(0)
```

Rules that involve several lines belong to the aggregate, so test those through
the aggregate (as in the previous sections).

## Check that nothing is lost in a round trip

The snapshot is how an aggregate is stored and loaded, so a round trip must
preserve everything. A parametrized test over a few representative orders
guards that for every field you add later:

```python
@pytest.mark.parametrize(
    "order",
    [
        make_order(),
        make_order(lines=(line_snapshot(1, "book", quantity=3),)),
        make_order(
            status=OrderStatus.PLACED,
            lines=(line_snapshot(1, "book"), line_snapshot(2, "pen")),
        ),
    ],
    ids=["empty draft", "one line", "placed with two lines"],
)
def test_nothing_is_lost_in_a_round_trip(order: Order) -> None:
    snapshot = order.to_snapshot()

    assert Order(snapshot).to_snapshot() == snapshot
```

If you add a field to the state but forget it in the snapshot, or the other way
round, this is the test that notices.

## Test identity

Aggregates are equal when their ids are equal, which makes them safe to keep in
sets and dictionaries while their data changes:

```python
def test_an_order_is_the_same_order_after_it_changes() -> None:
    order = make_order()
    same_order_before = Order(order.to_snapshot())

    order.add_line("book", 1, Money(1500, "EUR"))

    assert order == same_order_before
    assert len({order, same_order_before}) == 1
```

## Share set-up with fixtures

When several tests need the same starting point, a fixture reads well:

```python
@pytest.fixture
def draft_order() -> Order:
    order = make_order()
    order.add_line("book", 2, Money(1500, "EUR"))
    return order


def test_removing_the_last_line_leaves_an_empty_draft(draft_order: Order) -> None:
    draft_order.remove_line(1)

    assert draft_order.lines == ()
    assert draft_order.status is OrderStatus.DRAFT
```

## What not to test

- **The library's own guarantees.** You do not need to test that snapshots are
  frozen, that ids cannot be reassigned or that `abstract` classes are rejected.
  That is covered by the library's tests.
- **`_state`.** If a test needs it, the aggregate is missing a property or the
  test is asserting on the wrong thing.
- **Mocks of inner entities.** They are cheap and pure. Use real ones.

## Where the database comes in

None of these tests touched a database. Tests for a repository are a different
kind of test: see [Write an in-memory repository](write-an-in-memory-repository.md)
for a fake that lets you test application services without one, and
[Map an aggregate to an ORM](map-aggregate-to-orm.md) for the tests that check the
real mapping.
