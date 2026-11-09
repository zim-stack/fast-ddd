# Fast DDD

**Domain-Driven Design for FastAPI services.**

{{ project_name }} gives you `Aggregate`, `Entity`, and `ValueObject` building blocks,
wired together with `Repository` and `UnitOfWork` abstractions, so you can start
from a tested structure instead of assembling one from scratch.

Your domain model stays independent of the database: business rules live in
plain Python objects and can be tested without a database.

## Key features

- **Domain building blocks**: `Aggregate`, `Entity`, `ValueObject`.
- **Persistence-ignorant domain**: the domain model knows nothing about tables or sessions.
- **Repository and Unit of Work**: a clear way to load, save, and commit changes.
- **FastAPI integration**: dependency-injection-friendly, so it fits normal FastAPI code.
<!-- 
- **Testable by design**: swap in an in-memory repository and test without a database.
-->


## Installation

Supports python version 3.13 and later.

```shell
pip install {{ project_name }}
```

## A minimal example

<!-- Teaser: “this is what the code looks like”, incomplete -->

```python
from dataclasses import dataclass
from {{ import_name }} import Aggregate, ValueObject, Uow

class Money(ValueObject):
    amount: int
    currency: str
    
class Order(Aggregate):
    
    def pay(self) -> None:
        # business rules and invariants live here, not in the API layer
        ...
        
@dataclass(frozen=True)
class PayOrderPayload:
    order_id: int
    
class PayOrderCommand:
    """Application service"""
    
    def __init__(self, uow: Uow):
        self._uow = uow
    
    async def execute(self, payload: PayOrderPayload):
        async with self._uow:
            order = await self._uow.orders.get_by_id(payload.order_id)
            order.pay()
            
        # auto-committed
```

The application service loads an aggregate through a repository, calls domain behavior on it,
and commits through the unit of work. It never touches the database directly.


## Is this for you?

{{ project_name }} targets services, including small microservices, whose business
logic is complex enough that the domain model should not be tied to the database schema.

If your service is mostly CRUD, an Active Record framework such as Django
(with its admin) is probably the better choice. See [Motivation](motivation.md)
for the full reasoning and the [trade-offs](concepts/when-not-to-use-this.md).


## Where to go next

| I want to...                         | Go to                                         |
| ------------------------------------ | --------------------------------------------- |
| Understand why this exists           | [Motivation](motivation.md)                   |
| Get something running in 5 minutes   | [Quickstart](getting-started.md)   |
| Learn step by step                   | [Tutorial](tutorial/index.md)                 |
| Understand the concepts              | [Concepts](concepts/ddd-primer.md)            |
| Solve a specific problem             | [How-to guides](how-to/add-a-field.md)        |
<!--
| Look up the API                      | [Reference](reference/aggregate.md)           |
-->

<!-- 
Reader journey
```txt
 index ──► getting-started ──► tutorial ──► how-to
   │                              │            │
   │                              ▼            ▼
   └──► motivation ──────────► concepts ──► reference
        (why?)                (deep why)    (lookup)
```
-->
