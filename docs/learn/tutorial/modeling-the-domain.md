# Modeling the domain

In this chapter you create the first version of the `Order` aggregate: its
identity, its data, and the frozen copy of that data that the rest of the
application will see.

## Start from the language

Before writing any code, name the things the business talks about. Here that is
an **order**, placed by a **customer**, which is a **draft** until it is
**placed** or **cancelled**. Those words become the names in your code. Keeping
the code in the language of the business is what makes the model explicit
instead of accidental (see [Motivation](../../about/motivation.md)).

An order is the thing the rest of the system refers to ("pay order 42"), so it
will be an **aggregate**: an object with an identity that guards its own rules.
We will not worry about rules yet. First, the data.

## State, snapshot and aggregate

An aggregate in {{ project_name }} is made of three classes:

| Class | Mutable? | What it is for |
|---|---|---|
| **State** | yes | The working data. Private to the aggregate. |
| **Snapshot** | no | A frozen copy of the state. This is what you store, publish or hand to other layers. |
| **Aggregate** | yes | Identity and behavior. Built from a snapshot and able to produce one. |

Start with the status and the imports shared by both flavors:

```python
from enum import StrEnum
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"
    CANCELLED = "cancelled"
```

Then declare the state and the snapshot. Pick the tab for the library you
prefer; everything after this works the same.

=== "dataclass"

    ```python
    from dataclasses import dataclass

    from {{ import_name }}.domain.flavors.dataclass_models import (
        DataclassSnapshot,
        DataclassState,
    )


    @dataclass(kw_only=True)
    class OrderState(DataclassState[UUID]):
        customer_id: UUID
        status: OrderStatus = OrderStatus.DRAFT


    @dataclass(frozen=True, kw_only=True)
    class OrderSnapshot(DataclassSnapshot[UUID]):
        customer_id: UUID
        status: OrderStatus = OrderStatus.DRAFT
    ```

=== "attrs"

    Needs the extra: `pip install "fast-ddd[attrs]"`.

    ```python
    import attrs

    from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


    @attrs.define(kw_only=True)
    class OrderState(State[UUID]):
        customer_id: UUID
        status: OrderStatus = OrderStatus.DRAFT


    @attrs.frozen(kw_only=True)
    class OrderSnapshot(Snapshot[UUID]):
        customer_id: UUID
        status: OrderStatus = OrderStatus.DRAFT
    ```

A few things to notice:

- `UUID` in `DataclassState[UUID]` (or `State[UUID]`) is the type of the
  **identity**. The base class adds the `id` field for you, and it cannot be
  reassigned after construction.
- The snapshot is **frozen**: its fields cannot change once it exists.
- The snapshot repeats the state's fields. It may expose only some of them
  (a state can keep private working data that never leaves the aggregate), but
  every snapshot field must exist on the state.

Now the aggregate itself:

```python
class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    @classmethod
    def create(cls, customer_id: UUID) -> "Order":
        """Start a new draft order for a customer."""
        return cls(OrderSnapshot(id=uuid4(), customer_id=customer_id))

    @property
    def customer_id(self) -> UUID:
        return self._state.customer_id

    @property
    def status(self) -> OrderStatus:
        return self._state.status
```

`Aggregate[UUID, OrderSnapshot, OrderState]` names the three types once: the
identity, the snapshot and the state. The library reads them when the class is
defined and checks that they fit together.

!!! note "An aggregate is built from a snapshot"
    The constructor takes a snapshot, never loose fields. That is deliberate:
    the same constructor is what a repository will use later to rebuild an order
    that was loaded from storage. `create` is a convenience for the "new order"
    case.

!!! tip "Why is the state private?"
    The state lives in `_state`, so the outside world can only change it through
    the aggregate's methods. That is what lets the aggregate protect its rules
    in the next chapters. Reads go through properties such as `status`.

## Try it

```python
order = Order.create(customer_id=uuid4())
assert order.status is OrderStatus.DRAFT

snapshot = order.to_snapshot()  # a frozen copy of the current state
assert snapshot.customer_id == order.customer_id

restored = Order(snapshot)  # rebuild an order from a snapshot
assert restored == order  # same identity ...
assert restored is not order  # ... but a separate object
```

Two things happened that matter for everything that follows:

1. `to_snapshot()` produced a copy. Changing the order later does not change a
   snapshot you already took.
2. `restored == order` is `True` because aggregates are equal when their **ids**
   are equal, not when all their fields are.

## What the library checks for you

The library validates your classes as early as it can. For example, a snapshot
that is not frozen is rejected the moment the aggregate class is defined:

```python
# raises TypeError
from dataclasses import dataclass


@dataclass(kw_only=True)
class DraftState:
    id: UUID
    customer_id: UUID


@dataclass(kw_only=True)
class DraftSnapshot:  # not frozen!
    id: UUID
    customer_id: UUID


class Draft(Aggregate[UUID, DraftSnapshot, DraftState]):
    pass


# TypeError: Draft: snapshot type DraftSnapshot must be frozen (frozen=True)
```

You get the error when you import the module, not on the first request.

## Test it

```python
import pytest


def test_a_new_order_is_a_draft() -> None:
    order = Order.create(customer_id=uuid4())

    assert order.status is OrderStatus.DRAFT


def test_an_order_survives_a_round_trip_through_a_snapshot() -> None:
    order = Order.create(customer_id=uuid4())
    snapshot = order.to_snapshot()

    assert Order(snapshot).to_snapshot() == snapshot


def test_snapshots_cannot_be_changed() -> None:
    snapshot = Order.create(customer_id=uuid4()).to_snapshot()

    with pytest.raises(AttributeError):
        snapshot.status = OrderStatus.PLACED  # type: ignore[misc]
```

No database, no fixtures, no mocking: the domain model is plain Python.

## Recap

- An aggregate is **state + snapshot + aggregate class**, with the identity
  type named once.
- The state is mutable and private; the snapshot is frozen and is what leaves
  the aggregate.
- Aggregates are built from snapshots and compared by id.
- Mistakes in the class definitions fail at import time.

Next: [Entities and value objects](entities-and-value-objects.md). An order
without lines is not much of an order.
