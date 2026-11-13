
## A. Optional base classes (nominal)

The shipped bases give you the `id` field and, for attrs, the frozen id protection. Types are inferred from the bases.

```python
# attrs flavor
@attrs.define(kw_only=True)
class OrderState(State[UUID]):
    customer_id: UUID
    lines: list[OrderLine] = attrs.field(factory=list)

@attrs.frozen(kw_only=True)
class OrderSnapshot(Snapshot[UUID]):
    customer_id: UUID
    lines: tuple[OrderLineSnapshot, ...] = ()

# dataclass flavor
@dataclass(kw_only=True)
class OrderState(DataclassState[UUID]):
    customer_id: UUID
    lines: list[OrderLine] = field(default_factory=list)

@dataclass(frozen=True, kw_only=True)
class OrderSnapshot(DataclassSnapshot[UUID]):
    customer_id: UUID
    lines: tuple[OrderLineSnapshot, ...] = ()

class Order(Aggregate[UUID, OrderSnapshot, OrderState]): ...
```

## B. Fully structural (no base classes)

The user declares `id` and picks any recognized model. The library checks capabilities (is it attrs or a dataclass, does it have `id`, is the snapshot frozen).

```python
@dataclass(kw_only=True)
class OrderState:
    id: UUID
    customer_id: UUID
    lines: list[OrderLine] = field(default_factory=list)

@attrs.frozen(kw_only=True)
class OrderSnapshot:
    id: UUID
    customer_id: UUID
    lines: tuple[OrderLineSnapshot, ...] = ()

class Order(Aggregate[UUID, OrderSnapshot, OrderState]): ...
```

## Trade-offs

| | A. Optional bases | B. Structural |
|---|---|---|
| `id` declared by user | no, inherited | yes, every class |
| `id` immutability on state | automatic (attrs setter, or a guard in the dataclass base) | not enforced for dataclasses, only documented |
| Type inference for `TId` | from the base's type argument | needs a Protocol with `id`, weaker inference |
| Mixing attrs and dataclass | allowed, per class | allowed, per class |
| Shared-fields mixin | attrs only (frozen inheritance) | attrs only |
| Library coupling | users import the bases | none |
| Typical error | forgetting the base gives a clear definition-time error | forgetting `id` gives a definition-time error |

## Recommendation

I'd pick A as the main path and let B work as a fallback. The bases stay optional, so the structural form is accepted whenever the capability checks pass. That keeps the protection of `id` and the type inference for people who use the bases, and doesn't force the library on people who don't want it. The cost is that the checks must be written for capabilities and not for `issubclass`, which is the loosening already proposed in point 2 of the plan.
