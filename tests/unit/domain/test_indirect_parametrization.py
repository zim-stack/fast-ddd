"""Binding snapshot and state types through generic intermediate bases.

Entity snapshot classes are registered globally (one snapshot class per
concrete entity), so every entity test below builds its own fresh pair.
"""

from dataclasses import dataclass
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

import attrs
import pytest

from fast_ddd.domain.aggregate import Aggregate
from fast_ddd.domain.entity import Entity
from fast_ddd.domain.flavors.attrs_models import Snapshot, State
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


class NamedState(Protocol):
    @property
    def id(self) -> int: ...

    name: str


def pair() -> tuple[type, type]:
    """A fresh (snapshot, state) pair with an int id and a `name` field."""

    @attrs.define(kw_only=True)
    class FreshState(State[int]):
        name: str = ""

    @attrs.frozen(kw_only=True)
    class FreshSnapshot(Snapshot[int]):
        name: str = ""

    return FreshSnapshot, FreshState


# --- Entities -----------------------------------------------------------------


class TestEntityIndirect:
    def test_one_level(self) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: NamedState](Entity[int, M, S], abstract=True):
            def rename(self, name: str) -> None:
                self._state.name = name

        class Thing(Base[Snap, St]):  # type: ignore[valid-type]
            pass

        assert Thing._snapshot_cls is Snap
        assert Thing._state_cls is St
        thing = Thing(Snap(id=1, name="a"))
        thing.rename("b")
        assert thing.to_snapshot() == Snap(id=1, name="b")
        assert type(thing.to_snapshot()) is Snap

    def test_binding_matches_direct_parametrization(self) -> None:
        Snap, St = pair()
        Snap2, St2 = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Indirect(Base[Snap, St]):  # type: ignore[valid-type]
            pass

        class Direct(Entity[int, Snap2, St2]):  # type: ignore[valid-type]
            pass

        assert [f.name for f in Indirect._shared_fields] == [
            f.name for f in Direct._shared_fields
        ]

    def test_several_levels_with_reordered_parameters(self) -> None:
        Snap, St = pair()

        class A[S: State, M: Snapshot](
            Entity[int, M, S], abstract=True
        ):  # S, M swapped
            pass

        # fixes the snapshot only
        class B[S2: State](A[S2, Snap], abstract=True):  # type: ignore[valid-type]
            pass

        class C(B[St]):  # type: ignore[valid-type]
            pass

        assert C._snapshot_cls is Snap and C._state_cls is St

    def test_intermediate_generic_over_an_outer_generic(self) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Mid[S2: State](Base[Snap, S2], abstract=True):  # type: ignore[valid-type]
            pass

        class Leaf(Mid[St]):  # type: ignore[valid-type]
            pass

        assert Leaf._snapshot_cls is Snap and Leaf._state_cls is St

    def test_old_style_type_variables(self) -> None:
        Snap, St = pair()
        M_ = TypeVar("M_")
        S_ = TypeVar("S_")

        class Old(Entity[int, M_, S_], abstract=True):  # type: ignore[valid-type]
            pass

        class Leaf(Old[Snap, St]):
            pass

        assert Leaf._snapshot_cls is Snap and Leaf._state_cls is St

    def test_generic_snapshot_arguments_bind_to_their_origin_class(self) -> None:
        @attrs.define(kw_only=True)
        class BoxState(State[int]):
            value: object = None

        @attrs.frozen(kw_only=True)
        class BoxSnapshot[T](Snapshot[int]):
            value: object = None

        class Base[T](Entity[int, BoxSnapshot[T], BoxState], abstract=True):
            pass

        class StrBox(Base[str]):
            pass

        assert StrBox._snapshot_cls is BoxSnapshot  # origin of BoxSnapshot[str]
        assert StrBox(BoxSnapshot(id=1, value="x")).id == 1

    def test_type_arguments_of_the_same_snapshot_class_are_not_a_conflict(
        self,
    ) -> None:
        @attrs.define(kw_only=True)
        class BoxState(State[int]):
            value: object = None

        @attrs.frozen(kw_only=True)
        class BoxSnapshot[T](Snapshot[int]):
            value: object = None

        class X[T](Entity[int, BoxSnapshot[T], BoxState], abstract=True):
            pass

        class Y[T](Entity[int, BoxSnapshot[T], BoxState], abstract=True):
            pass

        # pyrefly: ignore[invalid-inheritance]
        class Ok(X[str], Y[int]):  # same classes, different type arguments
            pass

        assert Ok._snapshot_cls is BoxSnapshot

    def test_subclass_of_an_indirect_concrete_inherits_binding_and_identity(
        self,
    ) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Thing(Base[Snap, St]):  # type: ignore[valid-type]
            pass

        class SubThing(Thing):
            pass

        assert SubThing._snapshot_cls is Snap
        assert SubThing._identity_root is Thing
        assert SubThing(Snap(id=1)) == Thing(Snap(id=1))

    def test_children_of_one_generic_base_are_separate_identity_spaces(self) -> None:
        SnapA, StA = pair()
        SnapB, StB = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class A(Base[SnapA, StA]):  # type: ignore[valid-type]
            pass

        class B(Base[SnapB, StB]):  # type: ignore[valid-type]
            pass

        assert A(SnapA(id=1)) != B(SnapB(id=1))
        assert Base._identity_root is None

    def test_indirect_entities_are_restored_when_nested(self) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Child(Base[Snap, St]):  # type: ignore[valid-type]
            pass

        @attrs.define(kw_only=True)
        class HolderState(State[int]):
            children: list[Child] = attrs.field(factory=list)

        @attrs.frozen(kw_only=True)
        class HolderSnapshot(Snapshot[int]):
            children: tuple[Snap, ...] = ()  # type: ignore[valid-type]

        class Holder(Entity[int, HolderSnapshot, HolderState]):
            pass

        holder = Holder(HolderSnapshot(id=1, children=(Snap(id=7, name="x"),)))
        assert type(holder._state.children) is list
        assert type(holder._state.children[0]) is Child
        assert holder.to_snapshot().children == (Snap(id=7, name="x"),)

    def test_one_snapshot_class_per_concrete_entity_still_holds(self) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class First(Base[Snap, St]):  # type: ignore[valid-type]
            pass

        with pytest.raises(TypeError, match="already paired with .*First"):

            class Second(Base[Snap, St]):  # type: ignore[valid-type]
                pass

    def test_dataclass_flavor_works_through_a_generic_base(self) -> None:
        @dataclass(kw_only=True)
        class DcState(DataclassState[int]):
            name: str = ""

        @dataclass(frozen=True, kw_only=True)
        class DcSnapshot(DataclassSnapshot[int]):
            name: str = ""

        class Base[M: DataclassSnapshot, S: DataclassState](
            Entity[int, M, S], abstract=True
        ):
            pass

        class DcThing(Base[DcSnapshot, DcState]):  # type: ignore[valid-type]
            pass

        assert DcThing(DcSnapshot(id=1, name="a")).to_snapshot().name == "a"


class TestEntityIndirectErrors:
    def test_unsubscripted_generic_base_is_unresolved(self) -> None:
        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        with pytest.raises(TypeError, match="unresolved"):

            class Bad(Base):  # type: ignore[type-arg]
                pass

    def test_unsubscripted_generic_base_is_allowed_when_abstract(self) -> None:
        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class StillAbstract(Base, abstract=True):  # type: ignore[type-arg]
            pass

        assert StillAbstract._identity_root is None

    def test_non_abstract_class_with_open_variables_is_rejected(self) -> None:
        Snap, St = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        with pytest.raises(TypeError, match="unresolved"):

            class Bad[S2: State](Base[Snap, S2]):  # type: ignore[valid-type]
                pass

    def test_open_variables_are_allowed_when_abstract(self) -> None:
        Snap, _ = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Mid[S2: State](Base[Snap, S2], abstract=True):  # type: ignore[valid-type]
            pass

        assert Mid._identity_root is None

    def test_conflicting_parametrizations_are_rejected(self) -> None:
        Snap1, St1 = pair()
        Snap2, St2 = pair()

        class X[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Y[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        with pytest.raises(
            TypeError, match="inherits conflicting entity parametrizations"
        ):

            class Bad(X[Snap1, St1], Y[Snap2, St2]):  # type: ignore[valid-type]
                pass

    def test_identical_parametrizations_through_two_bases_are_accepted(self) -> None:
        Snap, St = pair()

        class X[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Y[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        class Ok(X[Snap, St], Y[Snap, St]):  # type: ignore[valid-type]
            pass

        assert Ok._snapshot_cls is Snap

    def test_invalid_state_type_is_still_reported_through_the_chain(self) -> None:
        Snap, _ = pair()

        class Base[M: Snapshot, S](Entity[int, M, S], abstract=True):  # type: ignore[valid-type]
            pass

        with pytest.raises(TypeError, match="state type must be an attrs class"):

            class Bad(Base[Snap, dict]):  # type: ignore[valid-type]
                pass

    def test_unparametrized_entity_is_still_rejected(self) -> None:
        with pytest.raises(TypeError, match="must bind its snapshot and state types"):

            class Bad(Entity):  # type: ignore[type-arg]
                pass

    def test_arity_errors_come_from_typing_itself(self) -> None:
        Snap, _ = pair()

        class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
            pass

        with pytest.raises(TypeError):
            Base[Snap]  # type: ignore[misc]


# --- Aggregates ---------------------------------------------------------------


@attrs.define(kw_only=True)
class UserFields:
    name: str
    is_active: bool = True


@attrs.define(kw_only=True)
class UserState(UserFields, State[UUID]):
    pass


@attrs.frozen(kw_only=True)
# pyrefly: ignore[invalid-inheritance]
class UserSnapshot(UserFields, Snapshot[UUID]):
    pass


@attrs.frozen
class UserDeactivated:
    user_id: UUID


class User[M: UserSnapshot, S: UserState](Aggregate[UUID, M, S], abstract=True):
    """Shared behavior; `self._state` is typed as the bound UserState."""

    def deactivate(self) -> None:
        self._state.is_active = False
        self.record_event(UserDeactivated(user_id=self.id))  # type: ignore[arg-type]

    def validate_invariants(self) -> None:
        if not self._state.name:
            raise ValueError("a user needs a name")


@attrs.define(kw_only=True)
class CandidateState(UserState):
    resume_url: str | None = None


@attrs.frozen(kw_only=True)
class CandidateSnapshot(UserSnapshot):
    resume_url: str | None = None


class Candidate(User[CandidateSnapshot, CandidateState]):
    pass


@attrs.define(kw_only=True)
class RecruiterState(UserState):
    company: str = ""


@attrs.frozen(kw_only=True)
class RecruiterSnapshot(UserSnapshot):
    company: str = ""


class Recruiter(User[RecruiterSnapshot, RecruiterState]):
    pass


class TestAggregateIndirect:
    def test_binding(self) -> None:
        assert Candidate._snapshot_cls is CandidateSnapshot
        assert Candidate._state_cls is CandidateState
        assert Recruiter._snapshot_cls is RecruiterSnapshot
        assert Recruiter._state_cls is RecruiterState

    def test_round_trip_keeps_subtype_fields(self) -> None:
        candidate = Candidate(
            CandidateSnapshot(id=uuid4(), name="ann", resume_url="https://cv")
        )
        snapshot = candidate.to_snapshot()
        assert type(snapshot) is CandidateSnapshot
        assert snapshot.resume_url == "https://cv"
        assert Candidate(snapshot).to_snapshot() == snapshot

    def test_shared_behavior_works_for_each_subtype(self) -> None:
        candidate = Candidate(CandidateSnapshot(id=uuid4(), name="ann"))
        recruiter = Recruiter(RecruiterSnapshot(id=uuid4(), name="bob", company="X"))
        candidate.deactivate()
        recruiter.deactivate()
        assert candidate.to_snapshot().is_active is False
        assert recruiter.to_snapshot().is_active is False
        assert candidate.pull_domain_events() == [UserDeactivated(candidate.id)]

    def test_shared_invariants_apply_to_each_subtype(self) -> None:
        recruiter = Recruiter(RecruiterSnapshot(id=uuid4(), name="", company="X"))
        with pytest.raises(ValueError, match="needs a name"):
            recruiter.to_snapshot()

    def test_each_subtype_is_its_own_identity_space(self) -> None:
        shared = uuid4()
        candidate = Candidate(CandidateSnapshot(id=shared, name="a"))
        recruiter = Recruiter(RecruiterSnapshot(id=shared, name="a"))
        assert candidate != recruiter
        assert User._identity_root is None
        assert Candidate._identity_root is Candidate

    def test_aggregates_are_still_not_nestable(self) -> None:
        assert Candidate._nestable is False

    def test_binding_matches_direct_parametrization(self) -> None:
        class DirectCandidate(Aggregate[UUID, CandidateSnapshot, CandidateState]):
            pass

        assert DirectCandidate._shared_fields == Candidate._shared_fields
        assert DirectCandidate._state_cls is Candidate._state_cls

    def test_aggregates_may_share_snapshot_classes_through_a_generic_base(
        self,
    ) -> None:
        # Aggregates are not registered, so no "already paired" error.
        class Another(User[CandidateSnapshot, CandidateState]):
            pass

        assert Another._snapshot_cls is CandidateSnapshot

    def test_conflicting_generic_bases_are_rejected(self) -> None:
        class Other[M: UserSnapshot, S: UserState](
            Aggregate[UUID, M, S], abstract=True
        ):
            pass

        with pytest.raises(TypeError, match="conflicting entity parametrizations"):

            # pyrefly: ignore[invalid-inheritance]
            class Bad(
                User[CandidateSnapshot, CandidateState],
                Other[RecruiterSnapshot, RecruiterState],
            ):
                pass

    def test_unresolved_aggregate_base_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="unresolved"):

            class Bad(User):  # type: ignore[type-arg]
                pass


class TestIndirectWithInnerEntities:
    def test_aggregate_with_inner_entities_through_a_generic_base(self) -> None:
        Snap, St = pair()

        class Line(Entity[int, Snap, St]):  # type: ignore[valid-type]
            pass

        @attrs.define(kw_only=True)
        class BasketState(State[UUID]):
            lines: list[Line] = attrs.field(factory=list)

        @attrs.frozen(kw_only=True)
        class BasketSnapshot(Snapshot[UUID]):
            lines: tuple[Snap, ...] = ()  # type: ignore[valid-type]

        class Base[M: Snapshot, S: State](Aggregate[UUID, M, S], abstract=True):
            pass

        class Basket(Base[BasketSnapshot, BasketState]):
            pass

        basket = Basket(BasketSnapshot(id=uuid4(), lines=(Snap(id=1, name="a"),)))
        assert type(basket._state.lines[0]) is Line
        assert basket.to_snapshot().lines == (Snap(id=1, name="a"),)


def test_plain_mixins_next_to_the_generic_base_are_ignored() -> None:
    # Plain mixins and ABC next to the generic base must not disturb the walk.
    Snap, St = pair()

    class Mixin:
        def shout(self) -> str:
            return "hey"

    class Base[M: Snapshot, S: State](Entity[int, M, S], abstract=True):
        pass

    class Thing(Mixin, Base[Snap, St]):  # type: ignore[valid-type]
        pass

    assert Thing._snapshot_cls is Snap
    assert Thing(Snap(id=1)).shout() == "hey"  # type: ignore[attr-defined]
