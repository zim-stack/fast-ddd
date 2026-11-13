## Sharing fields between State and Snapshot

State is mutable and Snapshot is frozen. To avoid declaring the same fields
twice, put the shared fields in a plain attrs mixin and inherit it in both:

```python
@attrs.define(kw_only=True)
class OrderFields:
    customer_id: UUID
    status: OrderStatus = OrderStatus.DRAFT


@attrs.define(kw_only=True)
class OrderState(OrderFields, AggregateState[UUID]):
    notes: list[str] = attrs.field(factory=list, converter=list)


@attrs.frozen(kw_only=True)
class OrderSnapshot(  # pyrefly: ignore[invalid-inheritance]
    OrderFields, AggregateSnapshot[UUID]
):
    notes: tuple[str, ...] = attrs.field(default=(), converter=tuple)
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
- Do not derive the mixin from `AggregateState` or `AggregateSnapshot`.
- A field is shareable only if it is identical in both classes. Fields with a
  mutable/immutable pair (`list`/`tuple`, `dict`/`Mapping`, `set`/`frozenset`)
  must be declared in each class.
- Fields that exist only on the state need a default.

### Recommendation: 
attrs is the first-class choice when you want shared fields. Dataclasses are supported, but without field sharing.
