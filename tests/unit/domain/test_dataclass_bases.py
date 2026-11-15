import dataclasses
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import attrs
import pytest

import fast_ddd
from fast_ddd.domain.entity import (
    Entity,
)
from fast_ddd.domain.flavors.attrs_models import Snapshot, State
from fast_ddd.domain.flavors.dataclass_models import DataclassSnapshot, DataclassState


@dataclass(kw_only=True)
class UserState(DataclassState[int]):
    name: str = ""


@dataclass(frozen=True, kw_only=True)
class UserSnapshot(DataclassSnapshot[int]):
    name: str = ""


class User(Entity[int, UserSnapshot, UserState]):
    pass


class TestDataclassState:
    def test_id_cannot_be_reassigned_or_deleted(self) -> None:
        state = UserState(id=1, name="a")
        with pytest.raises(AttributeError, match="immutable once assigned"):
            state.id = 2
        with pytest.raises(AttributeError, match="cannot be deleted"):
            del state.id
        assert state.id == 1

    def test_other_fields_are_mutable(self) -> None:
        state = UserState(id=1, name="a")
        state.name = "b"
        assert state.name == "b"

    def test_slots_subclass_keeps_the_guard(self) -> None:
        @dataclass(kw_only=True, slots=True)
        class SlottedState(DataclassState[int]):
            name: str = ""

        state = SlottedState(id=1, name="a")
        state.name = "b"
        with pytest.raises(AttributeError, match="immutable once assigned"):
            state.id = 2

    def test_entity_over_dataclass_bases_round_trips(self) -> None:
        user = User(UserSnapshot(id=7, name="ann"))
        user._state.name = "bob"
        assert user.to_snapshot() == UserSnapshot(id=7, name="bob")
        assert user.id == 7


class TestDataclassSnapshot:
    def test_is_frozen_equal_by_value_and_hashable(self) -> None:
        a, b = UserSnapshot(id=1, name="x"), UserSnapshot(id=1, name="x")
        assert a == b and hash(a) == hash(b)
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.name = "y"  # type: ignore[misc]


class TestSharedFieldsMixin:
    @pytest.mark.skipif(
        sys.version_info < (3, 13),
        reason="Python 3.12 accepts this by accident; 3.13+ rejects it",
    )
    def test_dataclasses_cannot_share_a_fields_mixin_with_a_frozen_snapshot(
        self,
    ) -> None:
        # A frozen dataclass may not inherit from a non-frozen one (3.13+ also
        # when another base is frozen), so state and snapshot cannot share a
        # plain fields mixin. Use the attrs flavor for that.
        @dataclass(kw_only=True)
        class Fields:
            name: str = ""

        with pytest.raises(
            TypeError, match="cannot inherit frozen dataclass from a non-frozen"
        ):

            @dataclass(frozen=True, kw_only=True)
            # pyrefly: ignore[invalid-inheritance]
            class SharedSnapshot(Fields, DataclassSnapshot[int]):
                pass

    def test_structural_dataclasses_cannot_share_a_fields_mixin(self) -> None:
        @dataclass(kw_only=True)
        class Fields:
            name: str = ""

        with pytest.raises(
            TypeError, match="cannot inherit frozen dataclass from a non-frozen"
        ):

            @dataclass(frozen=True, kw_only=True)
            # pyrefly: ignore[invalid-inheritance]
            class Snapshot_(Fields):
                id: int = 0

    def test_attrs_can_share_a_fields_mixin(self) -> None:
        @attrs.define(kw_only=True)
        class Fields:
            name: str = ""

        @attrs.define(kw_only=True)
        class SharedState(Fields, State[int]):
            pass

        @attrs.frozen(kw_only=True)
        # pyrefly: ignore[invalid-inheritance]
        class SharedSnapshot(Fields, Snapshot[int]):
            pass

        class Shared(Entity[int, SharedSnapshot, SharedState]):
            pass

        entity = Shared(SharedSnapshot(id=1, name="x"))
        assert entity.to_snapshot() == SharedSnapshot(id=1, name="x")


PROJECT_ROOT = Path(__file__).resolve().parents[3]  # tests/unit/domain/<file>
SRC_ROOT = Path(fast_ddd.__file__).resolve().parents[1]
SCENARIO_MODULE = "tests.unit.domain.scenarios.attrs_optional"


class TestAttrsIsOptional:
    """Run each scenario in a fresh interpreter where importing attrs fails."""

    def _run_scenario(self, name: str) -> subprocess.CompletedProcess[str]:
        prelude = "import sys; sys.modules['attrs'] = None\n"
        code = (
            prelude
            + f"from {SCENARIO_MODULE} import {name} as scenario\n"
            + "scenario()\n"
        )
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            env={
                "PYTHONPATH": os.pathsep.join([str(PROJECT_ROOT), str(SRC_ROOT)]),
                "PATH": "",
            },
        )

    def test_dataclass_only_usage_works_without_attrs(self) -> None:
        result = self._run_scenario("dataclass_only_usage")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "ok"

    def test_attrs_flavor_gives_a_helpful_error_without_attrs(self) -> None:
        result = self._run_scenario("attrs_flavor_error")
        assert result.returncode == 0, result.stderr
        assert "optional dependency 'attrs'" in result.stdout
        assert "Use dataclass alternatives" in result.stdout
