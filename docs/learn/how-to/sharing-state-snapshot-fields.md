## Sharing fields between State and Snapshot

State is mutable and Snapshot is frozen. To avoid declaring the same fields
twice, put the shared fields in a plain attrs mixin and inherit it in both:

```python
from enum import StrEnum
from uuid import UUID, uuid4

import attrs

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLACED = "placed"


@attrs.define(kw_only=True)
class OrderFields:
    customer_id: UUID
    status: OrderStatus = OrderStatus.DRAFT


@attrs.define(kw_only=True)
class OrderState(OrderFields, State[UUID]):
    notes: list[str] = attrs.field(factory=list)


@attrs.frozen(kw_only=True)
class OrderSnapshot(  # pyrefly: ignore[invalid-inheritance]
    OrderFields, Snapshot[UUID]
):
    notes: tuple[str, ...] = ()


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    def add_note(self, note: str) -> None:
        self._state.notes.append(note)
```

`customer_id` and `status` are declared once, in `OrderFields`. `notes` differs
between the two classes (a `list` in the state, a `tuple` in the snapshot), so it
is declared in each. The annotation on the state field tells the library to give
you a `list` back when an order is loaded, so no converter is needed.

The result behaves like any other aggregate:

```python
order = Order(OrderSnapshot(id=uuid4(), customer_id=uuid4()))
order.add_note("gift wrap")

snapshot = order.to_snapshot()
assert snapshot.notes == ("gift wrap",)  # list -> tuple
assert snapshot.status is OrderStatus.DRAFT  # shared field

assert Order(snapshot)._state.notes == ["gift wrap"]  # tuple -> list
```

### Type checker warning

Some type checkers report an error on the snapshot class, for example Pyrefly:

    Cannot inherit frozen dataclass `OrderSnapshot` from non-frozen
    dataclass `OrderFields` (invalid-inheritance)

**Why it appears.** attrs decorators (`attrs.define`, `attrs.frozen`) are
declared as `dataclass_transform` (PEP 681), so type checkers treat attrs
classes as dataclasses and apply the stdlib rule that a frozen dataclass cannot
inherit from a non-frozen one.

**Why it is safe to ignore.** attrs has no such restriction. The snapshot is
created without error, and assigning to its fields raises
`attrs.exceptions.FrozenInstanceError`. Only the type checker complains.

**What to do.** Suppress the diagnostic on the snapshot class line:

| Checker | Comment |
|---|---|
| Pyrefly | `# pyrefly: ignore[invalid-inheritance]` |
| mypy | `# type: ignore[misc]` (check the error code your version reports) |
| pyright | `# pyright: ignore[reportGeneralTypeIssues]` (check the rule name your version reports) |

If you prefer no suppressions, declare the shared fields in both the state and
the snapshot instead of using a mixin. The library behaves identically either
way.

**Do not** make the mixin frozen to silence the warning. attrs does not allow
a subclass to unfreeze a frozen base, so the state would become immutable too.

### Mixin rules

- The mixin must be an attrs class. Plain classes and stdlib dataclasses
  contribute no fields.
- Do not derive the mixin from `State` or `Snapshot`. Those bases belong to the
  state and snapshot classes themselves.
- A field is shareable only if it is identical in both classes. Fields with a
  mutable/immutable pair (`list`/`tuple`, `dict`/`Mapping`, `set`/`frozenset`)
  must be declared in each class.
- Fields that exist only on the state need a default (or `init=False`).

### Without a mixin

Dataclasses cannot share a mixin between a mutable and a frozen class, so
declare the fields in the state and in the snapshot. You can still avoid
repetition **within** each side by inheriting: see
[Share behavior with a generic base](share-behavior-with-a-generic-base.md),
where `CandidateState` extends `UserState` and `CandidateSnapshot` extends
`UserSnapshot`.

### Recommendation

attrs is the first-class choice when you want shared fields. Dataclasses are
supported, but without field sharing. See [Why attrs?](../faq/why-attrs.md).
