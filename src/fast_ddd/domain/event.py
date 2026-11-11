from dataclasses import dataclass

from fast_ddd.base import BaseEvent


@dataclass(frozen=True, kw_only=True)
class DomainEvent(BaseEvent):
    pass
