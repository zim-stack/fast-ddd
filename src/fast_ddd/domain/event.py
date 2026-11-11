from dataclasses import dataclass

from fast_ddd.base import BaseEvent

# TODO: 8. Events and the rest of the library
#   Domain events never touch state or snapshot machinery.
#   Define DomainEvent as a protocol or minimal base and don’t constrain how events are declared.
#   The same applies to value objects and ids: the existing id check already inspects __dataclass_params__ for frozen-ness.
#   Add the attrs equivalent (attrs.has(cls) and cls.__attrs_attrs__ frozen flag, via the adapter) so attrs ids get the
#   same “must be frozen” rule instead of passing silently.


@dataclass(frozen=True, kw_only=True)
class DomainEvent(BaseEvent):
    pass
