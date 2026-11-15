# Why attrs?

## Short answer

Because of **one capability**: an attrs class can be frozen while inheriting from
a non-frozen one, and a dataclass cannot. That lets a state (mutable) and a
snapshot (frozen) share one fields mixin instead of declaring every field twice.

Everything else works with the standard library. attrs is an **optional extra**,
and dataclasses are fully supported.

## The problem it solves

Every entity has a mutable **state** and a frozen **snapshot** that exposes the
same data. Often the two have many fields in common. You would like to declare
those fields once.

With attrs you can:

```python
from uuid import UUID

import attrs

from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


@attrs.define(kw_only=True)
class TokenFields:  # declared once
    user_id: UUID
    token: str


@attrs.define(kw_only=True)
class TokenState(TokenFields, State[UUID]):  # mutable
    pass


@attrs.frozen(kw_only=True)
class TokenSnapshot(TokenFields, Snapshot[UUID]):  # frozen
    pass
```

With dataclasses you cannot. A frozen dataclass may not inherit from a
non-frozen one:

```python
# raises TypeError
from dataclasses import dataclass


@dataclass(kw_only=True)
class Fields:
    name: str = ""


@dataclass(frozen=True, kw_only=True)
class FrozenFields(Fields):  # frozen, but its base is not
    id: int = 0


# TypeError: cannot inherit frozen dataclass from a non-frozen one
```

!!! note "Python 3.13 is stricter"
    Before 3.13 the standard library only rejected this when *none* of a class's
    dataclass bases was frozen. From 3.13 it rejects a frozen dataclass if *any*
    dataclass base is not frozen, even when another base is. Do not rely on the
    older behavior.

With dataclasses, declare the fields in the state and again in the snapshot.
Within each side you can still inherit normally (a `CandidateState` extending
`UserState`, and a `CandidateSnapshot` extending `UserSnapshot`), so the
repetition is limited to the two parallel hierarchies.

## So is attrs required?

No. The core library depends on nothing but the standard library, and the
dataclass flavor is complete:

| | attrs | dataclasses |
|---|---|---|
| Install | `pip install "fast-ddd[attrs]"` | nothing extra |
| Base classes | `State`, `Snapshot` | `DataclassState`, `DataclassSnapshot` |
| Share fields between state and snapshot with a mixin | yes | no |
| Protect the state's `id` from reassignment | yes (a frozen field) | yes (a guard in the base class) |
| Private field names (`_secret`) | supported | supported |

You can also mix them: an attrs state with a dataclass snapshot, or the reverse.
See [Base classes or structural classes?](state-base-vs-structural.md).

## What attrs adds beyond the mixin

- **Field-level control.** For example `attrs.field(on_setattr=attrs.setters.frozen)`
  protects a single field, which is how the `State` base guards `id`.
- **Private names.** attrs strips the leading underscore from the `__init__`
  keyword (`_secret` becomes `secret=`). The library uses the field's alias, so
  private fields round-trip correctly.

## A note about type checkers

attrs decorators are declared as `dataclass_transform`, so some type checkers
treat attrs classes like dataclasses and may report that a frozen class cannot
inherit from a non-frozen one when you use a fields mixin. attrs itself has no
such restriction and the code runs. The how-to guide
[Share fields between state and snapshot](../how-to/sharing-state-snapshot-fields.md#type-checker-warning)
shows how to silence the diagnostic.

## Which should I pick?

- **Start with dataclasses** if you want no extra dependency, or your states and
  snapshots do not overlap much.
- **Choose attrs** if you want the shared-fields mixin, or you already use attrs
  in the project.

The choice is per class, so you can adopt attrs later for the aggregates where
the mixin pays off, without rewriting the others.
