# Share behavior with a generic base

When several kinds of aggregate share behavior, put that behavior in one generic
base class instead of copying it. This guide shows the pattern, how the library
resolves the types, and the mistakes it rejects.

The example: users come in different kinds (candidates and recruiters). They all
have a name, can be deactivated, and must have a name. Each kind also has data of
its own.

## The pattern

First the data. Each kind extends a common state and a common snapshot. Pick the
tab for your library.

=== "dataclass"

    ```python
    from dataclasses import dataclass
    from uuid import UUID, uuid4

    from {{ import_name }}.domain.aggregate import Aggregate
    from {{ import_name }}.domain.flavors.dataclass_models import (
        DataclassSnapshot,
        DataclassState,
    )


    @dataclass(kw_only=True)
    class UserState(DataclassState[UUID]):
        name: str
        is_active: bool = True


    @dataclass(frozen=True, kw_only=True)
    class UserSnapshot(DataclassSnapshot[UUID]):
        name: str
        is_active: bool = True


    @dataclass(kw_only=True)
    class CandidateState(UserState):
        resume_url: str | None = None


    @dataclass(frozen=True, kw_only=True)
    class CandidateSnapshot(UserSnapshot):
        resume_url: str | None = None


    @dataclass(kw_only=True)
    class RecruiterState(UserState):
        company: str = ""


    @dataclass(frozen=True, kw_only=True)
    class RecruiterSnapshot(UserSnapshot):
        company: str = ""
    ```

=== "attrs"

    ```python
    from dataclasses import dataclass
    from uuid import UUID, uuid4

    import attrs

    from {{ import_name }}.domain.aggregate import Aggregate
    from {{ import_name }}.domain.flavors.attrs_models import Snapshot, State


    @attrs.define(kw_only=True)
    class UserFields:  # shared between state and snapshot
        name: str
        is_active: bool = True


    @attrs.define(kw_only=True)
    class UserState(UserFields, State[UUID]):
        pass


    @attrs.frozen(kw_only=True)
    class UserSnapshot(UserFields, Snapshot[UUID]):
        pass


    @attrs.define(kw_only=True)
    class CandidateState(UserState):
        resume_url: str | None = None


    @attrs.frozen(kw_only=True)
    class CandidateSnapshot(UserSnapshot):
        resume_url: str | None = None


    @attrs.define(kw_only=True)
    class RecruiterState(UserState):
        company: str = ""


    @attrs.frozen(kw_only=True)
    class RecruiterSnapshot(UserSnapshot):
        company: str = ""
    ```

Now the shared behavior, in a generic base that is **abstract**, and the
concrete aggregates that pass their own snapshot and state:

```python
@dataclass(frozen=True)
class UserDeactivated:
    user_id: UUID


class User[M: UserSnapshot, S: UserState](Aggregate[UUID, M, S], abstract=True):
    def deactivate(self) -> None:
        self._state.is_active = False  # S is bound to UserState: this is typed
        self.record_event(UserDeactivated(user_id=self.id))

    def validate_invariants(self) -> None:
        if not self._state.name:
            raise ValueError("a user needs a name")


class Staff[M: UserSnapshot, S: UserState](User[M, S], abstract=True):
    """A second level: behavior shared by users who work for a company."""

    def welcome_message(self) -> str:
        return f"Welcome, {self._state.name}"


class Candidate(User[CandidateSnapshot, CandidateState]):
    pass


class Recruiter(Staff[RecruiterSnapshot, RecruiterState]):
    pass
```

Each concrete class works exactly as if it had named the types itself:

```python
candidate = Candidate(CandidateSnapshot(id=uuid4(), name="Ann"))
candidate.deactivate()

snapshot = candidate.to_snapshot()
assert type(snapshot) is CandidateSnapshot  # not the base UserSnapshot
assert snapshot.is_active is False
assert candidate.pull_domain_events() == [UserDeactivated(user_id=candidate.id)]

recruiter = Recruiter(RecruiterSnapshot(id=uuid4(), name="Bob", company="Acme"))
assert recruiter.welcome_message() == "Welcome, Bob"
assert recruiter.to_snapshot().company == "Acme"  # its own field survives
```

The shared invariant applies to every kind:

```python
# raises ValueError
Candidate(CandidateSnapshot(id=uuid4(), name="")).to_snapshot()
```

## How the types are resolved

When a class is defined, the library follows the type arguments **up the chain**
until it reaches `Aggregate` (or `Entity`), substituting each type variable on
the way:

```text
Recruiter(Staff[RecruiterSnapshot, RecruiterState])
   Staff's (M, S)  :=  (RecruiterSnapshot, RecruiterState)
Staff[M, S](User[M, S])
   User's  (M, S)  :=  (RecruiterSnapshot, RecruiterState)
User[M, S](Aggregate[UUID, M, S])
   Aggregate[UUID, RecruiterSnapshot, RecruiterState]   <- the final binding
```

Type variables can be passed through in any order, an intermediate base can fix
some of them and leave others open, and the chain can be as long as you need.
Once resolved, the pair is validated exactly as in the direct form (frozen
snapshot, `id` fields, matching fields, and so on).

## The rules

- **A generic base that leaves types open must be `abstract=True`.** It is never
  instantiated, and only the concrete subclasses bind the types.
- **Every concrete class resolves to concrete snapshot and state classes.** You
  subscript each generic base fully; Python itself rejects the wrong number of
  arguments.
- **Each concrete subclass is its own identity space.** A candidate and a
  recruiter with the same id are different aggregates, and the abstract bases
  are not identities at all.
- **A subclass of a concrete aggregate inherits the binding.** A
  `class SeniorRecruiter(Recruiter)` needs no type arguments.

```python
assert Candidate(CandidateSnapshot(id=candidate.id, name="Ann")) != Recruiter(
    RecruiterSnapshot(id=candidate.id, name="Ann")
)
```

## What the library rejects

Forgetting `abstract=True` on a base that still has open type variables:

```python
# raises TypeError
class Broken[M: UserSnapshot, S: UserState](Aggregate[UUID, M, S]):
    pass


# TypeError: Broken leaves snapshot/state types unresolved; ...
```

Inheriting a generic base without subscripting it:

```python
# raises TypeError
class Unsubscripted(User):
    pass


# TypeError: Unsubscripted leaves snapshot/state types unresolved; ...
```

Inheriting two generic bases that resolve to different types:

```python
# raises TypeError
class Other[M: UserSnapshot, S: UserState](Aggregate[UUID, M, S], abstract=True):
    pass


class Mixed(
    User[CandidateSnapshot, CandidateState],
    Other[RecruiterSnapshot, RecruiterState],
):
    pass


# TypeError: Mixed inherits conflicting entity parametrizations: ...
```

All of these fail when the class is defined, so you see them on import.

## Entities work the same way

`Entity` supports the same pattern. One extra rule applies: a snapshot class
belongs to **one concrete entity**, because the library uses it to turn a nested
snapshot back into the right entity class. Two concrete entities cannot share a
snapshot class, so give each concrete entity its own. Aggregates are never
nested inside other aggregates, so they are not subject to this rule.

## Limitations

- Type arguments must be the classes themselves. String forward references
  (`User["CandidateSnapshot", "CandidateState"]`) and PEP 695 `type` aliases are
  not supported.
- The bound on a type variable (`M: UserSnapshot`) is enforced by your type
  checker, not at runtime. Passing a snapshot that does not extend `UserSnapshot`
  is a type error, and the library still validates the pair itself.

## Related

- [Entities and aggregates](../concepts/entities-and-aggregates.md)
- [Share fields between state and snapshot](sharing-state-snapshot-fields.md)
