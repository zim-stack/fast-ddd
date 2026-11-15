## Requirements
fast-ddd requires Python 3.13 or newer

## Installation

```shell
pip install {{ project_name }}
```

If you want to declare states and snapshots with attrs, install the attrs extra:

```shell
pip install "fast-ddd[attrs]"
```

The core works with the standard library only. attrs is optional, and
[Why attrs?](faq/why-attrs.md) explains when it is worth adding.

## Quick Start
<!--
Hands-on smallest working example: “make it run on your machine” 
A complete file you can copy, plus run command
-->

Save this as `quickstart.py`. It models a tiny `Order` aggregate, changes it
through a command, and then rebuilds it from a snapshot, which is exactly what a
repository does when it loads an aggregate from storage.

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.dataclass_models import (
    DataclassSnapshot,
    DataclassState,
)


@dataclass(frozen=True)
class OrderPlaced:
    order_id: UUID


@dataclass(kw_only=True)
class OrderState(DataclassState[UUID]):  # mutable, private to the aggregate
    customer_id: UUID
    placed: bool = False


@dataclass(frozen=True, kw_only=True)
class OrderSnapshot(DataclassSnapshot[UUID]):  # frozen: what you store or publish
    customer_id: UUID
    placed: bool = False


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    @classmethod
    def create(cls, customer_id: UUID) -> "Order":
        return cls(OrderSnapshot(id=uuid4(), customer_id=customer_id))

    def place(self) -> None:
        if self._state.placed:
            raise ValueError("order is already placed")
        self._state.placed = True
        self.record_event(OrderPlaced(order_id=self.id))


order = Order.create(customer_id=uuid4())
order.place()

snapshot = order.to_snapshot()  # a frozen copy of the state
print(snapshot)

restored = Order(snapshot)  # what a repository does when it loads an order
assert restored == order  # aggregates are equal when their ids are equal
print(order.pull_domain_events())
```

Run it:

```shell
python quickstart.py
```

You should see the snapshot, then the recorded event, similar to:

```text
OrderSnapshot(id=UUID('...'), customer_id=UUID('...'), placed=True)
[OrderPlaced(order_id=UUID('...'))]
```

What just happened:

- `OrderState` holds the working data and stays private inside the aggregate.
- `OrderSnapshot` is a frozen copy. It is what you hand to storage or to other
  layers, and it is what an aggregate is rebuilt from.
- `place()` is a **command**: it checks a rule, changes the state and records a
  **domain event**.
- No database was involved. The domain model is plain Python.

### Recommended Project Layout

Keep the domain in its own package and let every other layer depend on it, never
the other way round. The domain imports nothing from FastAPI, SQLAlchemy or any
other infrastructure:

```text
src/shop/
├── domain/
│   └── orders/
│       ├── __init__.py
│       ├── order.py          # the Order aggregate, its state and snapshot
│       ├── order_line.py     # inner entities and value objects
│       ├── events.py         # domain events
│       └── errors.py         # domain errors
└── ...                       # application, persistence and API layers, which
                              # depend on `domain` and are covered in the tutorial
```

Group by aggregate (`orders/`, `customers/`, ...) rather than by technical role
(`entities/`, `events/`, ...). Everything that must change together then lives
together, and each aggregate stays easy to find and to move.

It works, now go to the [tutorial](tutorial/index.md).
