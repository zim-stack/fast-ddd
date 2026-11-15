# Entities and aggregates

This guide shows how to model entities and aggregates, and how to declare their
state and snapshot with **attrs**, **dataclasses**, or a mix of both. The API
reference lists every class and parameter; this page focuses on how the pieces
fit together. If you are new to the library, the
[tutorial](../tutorial/index.md) builds the same ideas step by step first.

!!! note "Conventions on this page"
    - Code blocks run top to bottom as one script, so later blocks reuse names
      from earlier ones.
    - A first line such as `# raises TypeError` marks a block that is *meant* to
      fail. The comment names the exception you will see.
    - Domain events are plain frozen classes here. Use your own `DomainEvent`
      base class if your project defines one.

## The mental model

| Object | Mutable? | Purpose |
|---|---|---|
| **State** | yes | The entity's working data. Lives inside the entity as `_state`, so callers can only change it through the entity's methods. |
| **Snapshot** | no (deeply) | A frozen memento of the state. This is what you persist, publish, or hand to other layers. |
| **Entity** | yes | Identity plus behavior. Equality and hashing use the `id`, never the data. |
| **Aggregate** | yes | An entity that is also a consistency boundary: it records domain events and validates invariants before it hands out a snapshot. |

An entity is always built *from* a snapshot and always produces one:

```
snapshot ──► Entity(snapshot) ──► commands change _state ──► to_snapshot() ──► snapshot
```

## Installation

```bash
pip install fast-ddd              # dataclass flavor, no extra dependencies
pip install "fast-ddd[attrs]"     # adds the attrs flavor
```

attrs is optional. Everything except the attrs `State`/`Snapshot` base classes
works without it.

## Quick start

An `Order` aggregate that owns `OrderLine` entities. Pick the tab for the
library you prefer; both behave identically.

=== "attrs"

    ```python
    from uuid import UUID, uuid4

    import attrs

    from {{ import_name }}.domain.aggregate import Aggregate
    from {{ import_name }}.domain.entity import Entity
    from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


    # --- Inner entity ------------------------------------------------------
    @attrs.define(kw_only=True)
    class OrderLineState(State[int]):  # mutable, private to the entity
        sku: str
        quantity: int


    @attrs.frozen(kw_only=True)
    class OrderLineSnapshot(Snapshot[int]):  # frozen: what you persist or publish
        sku: str
        quantity: int


    class OrderLine(Entity[int, OrderLineSnapshot, OrderLineState]):
        @classmethod
        def create(cls, line_no: int, sku: str, quantity: int) -> "OrderLine":
            return cls(OrderLineSnapshot(id=line_no, sku=sku, quantity=quantity))

        def change_quantity(self, quantity: int) -> None:
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            self._state.quantity = quantity


    # --- Aggregate root ----------------------------------------------------
    @attrs.define(kw_only=True)
    class OrderState(State[UUID]):
        customer_id: UUID
        placed: bool = False
        # The annotation decides which container is restored on load.
        lines: list[OrderLine] = attrs.field(factory=list)


    @attrs.frozen(kw_only=True)
    class OrderSnapshot(Snapshot[UUID]):
        customer_id: UUID
        placed: bool = False
        lines: tuple[OrderLineSnapshot, ...] = ()


    @attrs.frozen
    class OrderPlaced:
        order_id: UUID


    class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
        @classmethod
        def create(cls, customer_id: UUID) -> "Order":
            return cls(OrderSnapshot(id=uuid4(), customer_id=customer_id))

        def add_line(self, sku: str, quantity: int) -> OrderLine:
            line = OrderLine.create(len(self._state.lines) + 1, sku, quantity)
            self._state.lines.append(line)
            return line

        def place(self) -> None:
            self._state.placed = True
            self.record_event(OrderPlaced(order_id=self.id))

        def validate_invariants(self) -> None:
            if self._state.placed and not self._state.lines:
                raise ValueError("a placed order needs at least one line")
    ```

=== "dataclass"

    ```python
    from dataclasses import dataclass, field
    from uuid import UUID, uuid4

    from {{ import_name }}.domain.aggregate import Aggregate
    from {{ import_name }}.domain.entity import Entity
    from {{ import_name }}.domain.flavors.dataclass_models import (
        DataclassSnapshot,
        DataclassState,
    )


    # --- Inner entity ------------------------------------------------------
    @dataclass(kw_only=True)
    class OrderLineState(DataclassState[int]):  # mutable, private to the entity
        sku: str
        quantity: int


    @dataclass(frozen=True, kw_only=True)
    class OrderLineSnapshot(DataclassSnapshot[int]):  # frozen
        sku: str
        quantity: int


    class OrderLine(Entity[int, OrderLineSnapshot, OrderLineState]):
        @classmethod
        def create(cls, line_no: int, sku: str, quantity: int) -> "OrderLine":
            return cls(OrderLineSnapshot(id=line_no, sku=sku, quantity=quantity))

        def change_quantity(self, quantity: int) -> None:
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            self._state.quantity = quantity


    # --- Aggregate root ----------------------------------------------------
    @dataclass(kw_only=True)
    class OrderState(DataclassState[UUID]):
        customer_id: UUID
        placed: bool = False
        # The annotation decides which container is restored on load.
        lines: list[OrderLine] = field(default_factory=list)


    @dataclass(frozen=True, kw_only=True)
    class OrderSnapshot(DataclassSnapshot[UUID]):
        customer_id: UUID
        placed: bool = False
        lines: tuple[OrderLineSnapshot, ...] = ()


    @dataclass(frozen=True)
    class OrderPlaced:
        order_id: UUID


    class Order(Aggregate[UUID, OrderSnapshot, OrderState]):
        @classmethod
        def create(cls, customer_id: UUID) -> "Order":
            return cls(OrderSnapshot(id=uuid4(), customer_id=customer_id))

        def add_line(self, sku: str, quantity: int) -> OrderLine:
            line = OrderLine.create(len(self._state.lines) + 1, sku, quantity)
            self._state.lines.append(line)
            return line

        def place(self) -> None:
            self._state.placed = True
            self.record_event(OrderPlaced(order_id=self.id))

        def validate_invariants(self) -> None:
            if self._state.placed and not self._state.lines:
                raise ValueError("a placed order needs at least one line")
    ```

Using it:

```python
order = Order.create(customer_id=uuid4())
line = order.add_line("sku-1", 2)
line.change_quantity(3)
order.place()

snapshot = order.to_snapshot()  # validates invariants, then freezes the state
assert isinstance(snapshot, OrderSnapshot)
assert isinstance(snapshot.lines, tuple)  # list -> tuple
assert snapshot.lines[0].quantity == 3  # OrderLine -> OrderLineSnapshot

restored = Order(snapshot)  # rebuild, e.g. after loading from storage
assert restored == order  # equality is identity, not data
assert type(restored._state.lines) is list  # container follows the annotation
assert type(restored._state.lines[0]) is OrderLine  # snapshots become entities again

events = order.pull_domain_events()  # returns the events and clears them
assert events == [OrderPlaced(order_id=order.id)]
assert order.pull_domain_events() == []
```

!!! tip "Why `_state`?"
    The state is deliberately private. Outside code calls commands such as
    `order.place()` instead of setting fields, so invariants live in one place.
    Expose reads through properties if you need them:

    ```python
    @property
    def sku(self) -> str:
        return self._state.sku
    ```

## Choosing a flavor

State and snapshot are independent choices. Each can be an attrs class or a
dataclass, with or without the optional base classes.

| Flavor | State | Snapshot | `id` field | State `id` protected |
|---|---|---|---|---|
| attrs + bases | `State[TId]` | `Snapshot[TId]` | inherited | yes |
| dataclass + bases | `DataclassState[TId]` | `DataclassSnapshot[TId]` | inherited | yes |
| structural | any attrs class or dataclass | any frozen attrs class or dataclass | you declare it | no |
| mixed | any of the above | any of the above | per class | depends on the state |

The only requirements are: both classes have an `id` field, the snapshot is
frozen, and every snapshot field also exists on the state. The FAQ explains
[when to use the base classes and when to go structural](../faq/state-base-vs-structural.md)
and [why attrs is optional](../faq/why-attrs.md).

### Structural classes (no base classes)

You can skip the library's bases entirely. You declare `id` yourself, and the
library checks the contract when the entity class is defined.

```python
from dataclasses import dataclass

from {{ import_name }}.domain.entity import Entity


@dataclass(kw_only=True)
class CouponState:
    id: int
    code: str
    uses_left: int = 1


@dataclass(frozen=True, kw_only=True)
class CouponSnapshot:
    id: int
    code: str
    uses_left: int = 1


class Coupon(Entity[int, CouponSnapshot, CouponState]):
    def redeem(self) -> None:
        if self._state.uses_left == 0:
            raise ValueError("coupon exhausted")
        self._state.uses_left -= 1


coupon = Coupon(CouponSnapshot(id=1, code="SAVE10", uses_left=1))
coupon.redeem()
assert coupon.to_snapshot().uses_left == 0
```

!!! warning "Structural states do not protect `id`"
    The `Entity.id` property is always read-only. But a structural *state* is a
    plain class, so `coupon._state.id = 2` would not be blocked, and it would
    change the entity's hash. Use the bases (or attrs'
    `attrs.field(on_setattr=attrs.setters.frozen)`) when you want the guard.

### Mixing attrs and dataclasses

The entity only needs the declared fields, so any pair works:

```python
import attrs
from dataclasses import dataclass

from {{ import_name }}.domain.entity import Entity
from {{ import_name }}.domain.flavors.attrs_models import State
from {{ import_name }}.domain.flavors.dataclass_models import DataclassSnapshot


@attrs.define(kw_only=True)
class SupplierState(State[int]):  # attrs state ...
    name: str


@dataclass(frozen=True, kw_only=True)
class SupplierSnapshot(DataclassSnapshot[int]):  # ... with a dataclass snapshot
    name: str


class Supplier(Entity[int, SupplierSnapshot, SupplierState]):
    def rename(self, name: str) -> None:
        self._state.name = name


supplier = Supplier(SupplierSnapshot(id=7, name="Acme"))
supplier.rename("Acme Ltd")
assert supplier.to_snapshot() == SupplierSnapshot(id=7, name="Acme Ltd")
```

### Sharing fields between state and snapshot (attrs only)

Declaring the same fields twice is tedious. attrs lets a frozen class inherit
from a non-frozen one, so a plain mixin can hold the shared fields:

```python
from uuid import UUID, uuid4

import attrs

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


@attrs.define(kw_only=True)
class RefreshTokenFields:  # declared once
    user_id: UUID
    token: str


@attrs.define(kw_only=True)
class RefreshTokenState(RefreshTokenFields, State[UUID]):
    pass


@attrs.frozen(kw_only=True)
class RefreshTokenSnapshot(RefreshTokenFields, Snapshot[UUID]):
    pass


class RefreshToken(Aggregate[UUID, RefreshTokenSnapshot, RefreshTokenState]):
    @classmethod
    def create(cls, user_id: UUID, token: str) -> "RefreshToken":
        return cls(RefreshTokenSnapshot(id=uuid4(), user_id=user_id, token=token))

    @property
    def token(self) -> str:
        return self._state.token


refresh = RefreshToken.create(uuid4(), "opaque-secret")
assert refresh.to_snapshot().token == refresh.token
```

!!! warning "Dataclasses cannot do this"
    The standard library rejects a frozen dataclass that inherits from a
    non-frozen one (Python 3.13 and later reject it even when another base is
    frozen). With dataclasses, repeat the fields in the state and the snapshot.

The how-to guide [Share fields between state and snapshot](../how-to/sharing-state-snapshot-fields.md)
covers the rules, and a type checker warning you may see.

## Containers and nested entities

A state field can hold entities in a `list`, `tuple`, `set`, `frozenset` or
`dict`. The library converts both ways:

| State value | Snapshot value | Restored state value |
|---|---|---|
| entity | its snapshot class | the entity again |
| `list` / `tuple` | `tuple` | follows the annotation |
| `set` / `frozenset` | `frozenset` | follows the annotation |
| `dict` / `Mapping` | read-only mapping (`MappingProxyType`) | follows the annotation |
| anything else | deep copy | unchanged |

The **annotation on the state field** picks the restored container, so no
converters are needed:

| State annotation | Restored as |
|---|---|
| `list[X]`, `MutableSequence[X]` | `list` |
| `set[X]`, `MutableSet[X]` | `set` |
| `frozenset[X]` | `frozenset` |
| `tuple[X, ...]` | `tuple` |
| `dict[K, V]`, `MutableMapping[K, V]` | `dict` |
| `Sequence[X]`, `Mapping[K, V]`, `Collection[X]` | the snapshot's own kind |
| `X \| None`, `Optional[X]`, `Annotated[X, ...]` | unwrapped, then as above |
| `Any`, or a union of two containers | the snapshot's own kind |

Element annotations apply recursively, so `dict[str, list[Item]]` restores a
`dict` of `list`s.

```python
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.entity import Entity
from {{ import_name }}.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


@dataclass(kw_only=True)
class CartItemState(DataclassState[str]):  # the id is the SKU
    quantity: int = 1


@dataclass(frozen=True, kw_only=True)
class CartItemSnapshot(DataclassSnapshot[str]):
    quantity: int = 1


class CartItem(Entity[str, CartItemSnapshot, CartItemState]):
    pass


@dataclass(kw_only=True)
class CartState(DataclassState[UUID]):
    items: dict[str, CartItem] = field(default_factory=dict)
    coupon_codes: set[str] = field(default_factory=set)
    history: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CartSnapshot(DataclassSnapshot[UUID]):
    items: Mapping[str, CartItemSnapshot] = field(
        default_factory=lambda: MappingProxyType({})
    )
    coupon_codes: frozenset[str] = frozenset()
    history: tuple[tuple[str, int], ...] = ()


class Cart(Aggregate[UUID, CartSnapshot, CartState]):
    def add(self, sku: str, quantity: int) -> None:
        self._state.items[sku] = CartItem(CartItemSnapshot(id=sku, quantity=quantity))
        self._state.history.append((sku, quantity))

    def apply_coupon(self, code: str) -> None:
        self._state.coupon_codes.add(code)


cart = Cart(CartSnapshot(id=uuid4()))
cart.add("sku-1", 2)
cart.apply_coupon("SAVE10")

snapshot = cart.to_snapshot()
assert type(snapshot.items) is MappingProxyType
assert type(snapshot.items["sku-1"]) is CartItemSnapshot
assert type(snapshot.coupon_codes) is frozenset
assert snapshot.history == (("sku-1", 2),)

restored = Cart(snapshot)
assert type(restored._state.items) is dict
assert type(restored._state.items["sku-1"]) is CartItem
assert type(restored._state.coupon_codes) is set
assert type(restored._state.history) is list
```

!!! note "Snapshots must be deeply immutable"
    Use `tuple`, `frozenset` and read-only mappings in snapshot fields. The
    library builds them for you from the state, and rejects mutable values
    (lists, dicts, sets, `bytearray`, non-frozen attrs or dataclass instances,
    live entities) at any depth. See [What the library enforces](#what-the-library-enforces).

## Persisting only part of the state

A snapshot may expose any subset of the state fields. State-only fields need a
default (or `init=False`). They are **not** part of the snapshot, so they are
reset to their default whenever the entity is rebuilt. Use them for transient or
derived data.

```python
import attrs
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


@attrs.define(kw_only=True)
class AccountState(State[UUID]):
    email: str
    failed_logins: int = 0  # state-only: needs a default, never persisted


@attrs.frozen(kw_only=True)
class AccountSnapshot(Snapshot[UUID]):
    email: str


class Account(Aggregate[UUID, AccountSnapshot, AccountState]):
    def register_failed_login(self) -> None:
        self._state.failed_logins += 1


account = Account(AccountSnapshot(id=uuid4(), email="ann@example.com"))
account.register_failed_login()

assert not hasattr(account.to_snapshot(), "failed_logins")
assert Account(account.to_snapshot())._state.failed_logins == 0  # reset on load
```

## Identity and equality

Entities are equal when they share an *identity space* and an `id`, regardless
of the other fields. The hash uses the same pair, so entities work in sets and
as dict keys.

```python
a = Coupon(CouponSnapshot(id=1, code="A"))
b = Coupon(CouponSnapshot(id=1, code="B"))
assert a == b and len({a, b}) == 1  # same id: the same entity
assert a != Coupon(CouponSnapshot(id=2, code="A"))

supplier_1 = Supplier(SupplierSnapshot(id=1, name="Acme"))
assert a != supplier_1  # same id, different entity type
assert a != a.to_snapshot()  # an entity is never equal to its snapshot
```

A subclass of a concrete entity shares its parent's identity space and its
state/snapshot binding:

```python
class SeasonalCoupon(Coupon):
    pass


assert SeasonalCoupon(CouponSnapshot(id=1, code="X")) == a
```

Use `abstract=True` for a shared base that is never instantiated. Each concrete
child becomes its own identity space:

```python
class BaseCart(Aggregate[UUID, CartSnapshot, CartState], abstract=True):
    pass


class WebCart(BaseCart):
    pass


class MobileCart(BaseCart):
    pass


shared = CartSnapshot(id=uuid4())
assert WebCart(shared) != MobileCart(shared)
```

## Sharing behavior through a generic base

Aggregates of different kinds often share behavior. Put it in a generic base
declared with `abstract=True`, and let each concrete class pass its own snapshot
and state:

```python
from dataclasses import dataclass
from uuid import UUID, uuid4

from {{ import_name }}.domain.aggregate import Aggregate
from {{ import_name }}.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


@dataclass(kw_only=True)
class UserState(DataclassState[UUID]):
    name: str
    is_active: bool = True


@dataclass(frozen=True, kw_only=True)
class UserSnapshot(DataclassSnapshot[UUID]):
    name: str
    is_active: bool = True


class User[M: UserSnapshot, S: UserState](Aggregate[UUID, M, S], abstract=True):
    def deactivate(self) -> None:
        self._state.is_active = False  # typed: S is bound to UserState


@dataclass(kw_only=True)
class CandidateState(UserState):
    resume_url: str | None = None


@dataclass(frozen=True, kw_only=True)
class CandidateSnapshot(UserSnapshot):
    resume_url: str | None = None


class Candidate(User[CandidateSnapshot, CandidateState]):
    pass


candidate = Candidate(CandidateSnapshot(id=uuid4(), name="Ann"))
candidate.deactivate()
assert candidate.to_snapshot().is_active is False
assert type(candidate.to_snapshot()) is CandidateSnapshot  # not the base snapshot
```

The library follows the type arguments up the chain until it reaches `Aggregate`
(or `Entity`), so `Candidate` is bound exactly as if it had named the types
itself. Each concrete subclass is its own identity space, and type checkers see
the concrete types inside the shared code. The how-to guide
[Share behavior with a generic base](../how-to/share-behavior-with-a-generic-base.md)
has the full set of rules and error cases.

!!! warning "Inner entity ids are local to their aggregate"
    `OrderLine(id=1)` in order A equals `OrderLine(id=1)` in order B. Do not mix
    inner entities of different aggregates in one set or dict. If you need
    global uniqueness, use a compound id:

    ```python
    @dataclass(frozen=True)
    class LineId:
        order_id: UUID
        line_no: int
    ```

Ids can be an `int`, `str`, `UUID`, enum, or a frozen value object. Never
`None`.

## Invariants and domain events

Invariants belong to the aggregate (the consistency boundary). Override
`validate_invariants`; it runs inside `to_snapshot()`, so an inconsistent
aggregate can never be persisted. Inner entities enforce their own simple
rules inside their command methods, as `change_quantity` does above.

```python
# raises ValueError
broken = Order.create(customer_id=uuid4())
broken.place()  # placed, but it has no lines
broken.to_snapshot()  # ValueError: a placed order needs at least one line
```

Events are recorded by commands and collected by the caller, typically after a
successful save:

```python
order = Order.create(customer_id=uuid4())
order.add_line("sku-1", 1)
order.place()

saved = order.to_snapshot()  # 1. persist the snapshot ...
for event in order.pull_domain_events():  # 2. ... then publish the events
    assert isinstance(event, OrderPlaced)
```

!!! note
    Events are not part of the snapshot. An aggregate rebuilt from a snapshot
    starts with no pending events.

## A repository on top of snapshots

Because the snapshot is the only thing that crosses the boundary, a repository
only deals in snapshots:

```python
class InMemoryOrders:
    def __init__(self) -> None:
        self._rows: dict[UUID, OrderSnapshot] = {}

    def save(self, order: Order) -> None:
        self._rows[order.id] = order.to_snapshot()  # frozen, safe to store

    def get(self, order_id: UUID) -> Order:
        return Order(self._rows[order_id])  # a fresh aggregate each time


repo = InMemoryOrders()
repo.save(order)

loaded = repo.get(order.id)
assert loaded == order and loaded is not order
loaded.add_line("sku-2", 5)  # changes the loaded copy only
assert len(repo.get(order.id).to_snapshot().lines) == 1
```

In a real repository, map `OrderSnapshot` to your database rows (or serialize
it) instead of keeping it in a dict. The aggregate never needs to know.

## What the library enforces

Most mistakes fail early with a clear message: either when the class is
**defined**, or when an entity is **constructed** or **snapshotted**.

At **construction** and **snapshot** time:

```python
# raises TypeError
Coupon(CouponSnapshot(id=None, code="x"))  # TypeError: Coupon.id must not be None
```

```python
# raises TypeError
class RawId:  # hashable, but equal only by reference
    pass


Supplier(SupplierSnapshot(id=RawId(), name="x"))  # TypeError: ... uses identity equality
```

```python
# raises TypeError
live_line = OrderLine.create(1, "sku-1", 1)
Order(OrderSnapshot(id=uuid4(), customer_id=uuid4(), lines=(live_line,)))
# TypeError: OrderSnapshot.lines[0] holds OrderLine; use its snapshot instead
```

```python
# raises TypeError
cart._state.history.append(bytearray(b"x"))  # cannot be frozen
cart.to_snapshot()  # TypeError: ... holds a mutable bytearray
```

At **class definition** time:

```python
# raises TypeError
@dataclass(kw_only=True)
class LooseSnapshot:  # not frozen
    id: int


@dataclass(kw_only=True)
class LooseState:
    id: int


class Bad(Entity[int, LooseSnapshot, LooseState]):
    pass
# TypeError: Bad: snapshot type LooseSnapshot must be frozen (frozen=True)
```

| Rule | When |
|---|---|
| `id` is not `None`, is hashable, compares by value, and (if attrs or dataclass) is frozen | entity construction |
| Snapshots are deeply immutable | whenever a snapshot is produced or consumed |
| Snapshot class is frozen; both classes have an `id` field | class definition |
| Every snapshot field exists on the state | class definition |
| State-only fields have a default or `init=False` | class definition |
| `__eq__` / `__hash__` are not overridden | class definition |
| A snapshot class belongs to one concrete entity | class definition |
| A concrete class binds its snapshot and state types, directly or through generic bases; generic bases that leave types open are `abstract=True` | class definition |
| Two generic bases must not resolve to different snapshot or state types | class definition |
| Aggregates are not nested inside other aggregates | snapshot time |

!!! info "Aggregates reference each other by id"
    An aggregate cannot sit inside another aggregate's state. Store the other
    aggregate's id (for example `order_id: UUID`) instead.

## Limitations

- **Type arguments must be classes.** A concrete class must reach `Entity[...]`
  or `Aggregate[...]` with real classes, directly or through generic bases.
  String forward references (`User["Snap", "State"]`) and PEP 695 `type` aliases
  as type arguments are not supported; pass the classes themselves.
- **One snapshot class per concrete entity.** A child class that needs to be
  restored as its own type when nested needs its own snapshot class.
- **Dataclass flavor cannot share a fields mixin** between state and snapshot
  (see above). Use attrs for that.
- **Hand-built snapshots are checked later.** Constructing a snapshot never
  fails; the check runs when it reaches an entity, or when `to_snapshot()` builds
  one.
- **Snapshots with mapping fields are not hashable**, because a read-only
  mapping view is not hashable.
- **Private attrs fields** (`_secret`) work and are passed through their
  `__init__` alias (`secret=`).

## Related

- [Tutorial](../tutorial/index.md): build an aggregate step by step.
- [Test aggregates](../how-to/test-aggregates.md): patterns for fast domain tests.
- [Share fields between state and snapshot](../how-to/sharing-state-snapshot-fields.md)
- [Share behavior with a generic base](../how-to/share-behavior-with-a-generic-base.md)
- [Glossary](../glossary.md)
