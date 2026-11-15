"""
User is no longer an Aggregate intermediate base.
It is simply a behavioral mixin.
This solution requires to repeat the Aggregate[...] declaration in every concrete subclass.
"""

from abc import ABC
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

import attrs

from fast_ddd.domain.aggregate import Aggregate
from fast_ddd.domain.flavors.attrs_models import Snapshot, State

# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class AccountTypeEnum(StrEnum):
    candidate = "candidate"
    recruiter = "recruiter"


@attrs.define(kw_only=True)
class UserFields(ABC):
    name: str
    hashed_password: str
    email: str
    is_active: bool = True


@attrs.define(kw_only=True)
class UserState(UserFields, State, ABC):
    pass


@attrs.frozen(kw_only=True)
# pyrefly: ignore[invalid-inheritance]
class UserSnapshot(UserFields, Snapshot, ABC):
    pass


class User[M: UserSnapshot, S: UserState](ABC):
    """Shared user behavior."""

    def __init__(self, snapshot: M) -> None:
        self._snapshot = snapshot

    @staticmethod
    def _hash_password(password: str) -> str:
        return f"hashed_{password}"


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


class CandidateFields:
    """Candidate-specific fields."""


@attrs.define(kw_only=True)
class CandidateState(CandidateFields, UserState):
    pass


@attrs.frozen(kw_only=True)
class CandidateSnapshot(CandidateFields, UserSnapshot):
    pass


class Candidate(
    Aggregate[UUID, CandidateSnapshot, CandidateState],
    User[CandidateSnapshot, CandidateState],
):
    def __init__(self, snapshot: CandidateSnapshot) -> None:
        super().__init__(snapshot)

    @classmethod
    def create(cls, email: str, password: str, name: str) -> Self:
        return cls(
            CandidateSnapshot(
                id=uuid4(),
                email=email.lower().strip(),
                hashed_password=cls._hash_password(password),
                name=name,
            )
        )


# ---------------------------------------------------------------------------
# Recruiter
# ---------------------------------------------------------------------------


class RecruiterFields:
    """Recruiter-specific fields."""


@attrs.define(kw_only=True)
class RecruiterState(RecruiterFields, UserState):
    pass


@attrs.frozen(kw_only=True)
class RecruiterSnapshot(RecruiterFields, UserSnapshot):
    pass


class Recruiter(
    Aggregate[UUID, RecruiterSnapshot, RecruiterState],
    User[RecruiterSnapshot, RecruiterState],
):
    def __init__(self, snapshot: RecruiterSnapshot) -> None:
        super().__init__(snapshot)

    @classmethod
    def create(cls, email: str, password: str, name: str) -> Self:
        return cls(
            RecruiterSnapshot(
                id=uuid4(),
                email=email.lower().strip(),
                hashed_password=cls._hash_password(password),
                name=name,
            )
        )


def test_user():
    candidate = Candidate.create(email="a", password="b", name="c")
    recruiter = Recruiter.create(email="a", password="b", name="c")

    print(candidate)
    print(recruiter)
