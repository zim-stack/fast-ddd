# Base classes or structural classes?

## Do I have to use the `State` and `Snapshot` base classes?

No. They are a convenience. A state can be **any attrs class or dataclass** with
an `id` field, and a snapshot can be **any frozen attrs class or frozen
dataclass** with an `id` field. The library checks that contract when your
aggregate or entity class is defined, whether or not you use the bases.

There are two styles, and you can mix them class by class.

### With the base classes

The bases add the `id` field and protect it against reassignment:

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.dataclass_models import (
    DataclassSnapshot,
    DataclassState,
)


@dataclass(kw_only=True)
class OrderState(DataclassState[UUID]):
    customer_id: UUID


@dataclass(frozen=True, kw_only=True)
class OrderSnapshot(DataclassSnapshot[UUID]):
    customer_id: UUID


class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
    pass
```

The attrs flavor has the same shape with `State` and `Snapshot` from
`{{ import_name }}.domain.flavors.attrs_models`.

### Structural (no base classes)

You declare `id` yourself, and your domain classes import nothing from the
library except `Aggregate` or `Entity`:

```python
@dataclass(kw_only=True)
class InvoiceState:
    id: UUID
    customer_id: UUID


@dataclass(frozen=True, kw_only=True)
class InvoiceSnapshot:
    id: UUID
    customer_id: UUID


class Invoice(Aggregate[UUID, InvoiceSnapshot, InvoiceState]):
    pass


customer_id = uuid4()
invoice = Invoice(InvoiceSnapshot(id=uuid4(), customer_id=customer_id))
assert invoice.to_snapshot().customer_id == customer_id
```

The same works with attrs classes, and a structural state may be an attrs class
while its snapshot is a dataclass, or the other way round.

## What is different?

| | Base classes | Structural |
|---|---|---|
| You declare `id` | no, it is inherited | yes, in the state and the snapshot |
| State `id` is protected from reassignment | yes | no (see below) |
| Snapshot must be frozen | yes | yes |
| Share fields between state and snapshot with a mixin | attrs only | attrs only |
| Mix attrs and dataclasses | yes, per class | yes, per class |
| Library imports in your domain classes | the two bases | none |
| Mistakes are reported at class definition | yes | yes |

### The one real difference: `id` protection

An entity's hash and identity come from its `id`, so the `id` must never change
while the entity is alive. The bases guard that: assigning to `state.id`
raises. A structural state is a plain class, so nothing stops this:

```python
invoice = Invoice(InvoiceSnapshot(id=uuid4(), customer_id=uuid4()))
original = invoice.id

invoice._state.id = uuid4()  # not blocked: the state is a plain class

assert invoice.id != original  # the entity's identity just changed
```

The `Entity.id` property itself is always read-only; only the *state's* field is
exposed. If you go structural with attrs, you can opt in to the same guard:

```python
import attrs


@attrs.define(kw_only=True)
class ShipmentState:
    id: UUID = attrs.field(on_setattr=attrs.setters.frozen)
    carrier: str = ""
```

With plain dataclasses there is no field-level equivalent. Use the base class or
keep to the convention that code outside the aggregate never touches `_state`.

## What the library checks either way

Whichever style you pick, these mistakes are rejected when the class is
defined, with an error that names the class and the problem:

- the state or the snapshot has no `id` field;
- the snapshot is not frozen;
- a snapshot field does not exist on the state;
- a state-only field has no default.

For example:

```python
# raises TypeError
@dataclass(kw_only=True)
class NoIdState:
    name: str = ""


@dataclass(frozen=True, kw_only=True)
class NoIdSnapshot:
    name: str = ""


class Bad(Aggregate[UUID, NoIdSnapshot, NoIdState]):
    pass


# TypeError: Bad: state type must define an `id` field
```

## Which should I use?

**Use the base classes by default.** They remove boilerplate and give you the
`id` guard for free. Reach for structural classes when:

- you already have attrs classes or dataclasses you want to reuse as state or
  snapshot;
- you want your domain classes to depend on the library as little as possible;
- you need a layout the bases do not fit, such as an `id` field with a custom
  type or validator.

The choice is local to each class, so you can start with the bases and switch a
single aggregate later without touching the others.

## Related

- [Why attrs?](why-attrs.md)
- [Entities and aggregates](../concepts/entities-and-aggregates.md)
- [Share fields between state and snapshot](../how-to/sharing-state-snapshot-fields.md)
