## Motivation

This repository makes Domain-Driven-Design (DDD) practical for FastAPI services.

It provides domain utilities such as Aggregate, Entity, ValueObject and wires them together with Repository and UnitOfWork abstractions, so new projects can start from a tested structure instead of assembling one from scratch.

### Why not just use Active Record (Django, Tortoise ORM)?

Django's ORM and Tortoise ORM follow the Active Record pattern: a model class corresponds to a table row and carries its own persistence behavior ("the object saves itself").

In *Patterns of Enterprise Application Architecture*, Martin Fowler notes that this works well when
domain logic is simple, and that it becomes awkward as logic grows more complex ([Fowler, 2002](#references)).

The reason is coupling. With Active Record the schema and the domain
model are the same thing, so:

- business rules are shaped by table structure instead of by the domain;
- schema changes ripple into domain code, and vice versa;
- rich domain concepts (value objects, polymorphism, invariants spanning several objects) have to be squeezed into one-class-per-table;
- domain logic is hard to test without a database.

For domains with complex business rules, Fowler recommends a Domain Model combined with Data Mapper, which keeps the domain objects and the database independent of each other. 

In DDD this means you first model the domain from business rules, and then design the database schema separately to suit storage and query needs ([Evans, 2003](#references)). Repository and Unit of Work then give the domain a persistence-ignorant way to load, save and commit changes ([Percival and Gregory, 2020](#references)).

If your service is mostly CRUD, Active Record (and Django with its admin) is a sound choice. This project targets the other case: services, including small microservices, whose business logic is complex enough that the domain model should not be tied to the database schema.

### "But we don't do much upfront domain modeling"

You don't need a big upfront design phase to benefit from this approach.
Whether or not you plan it, you will model the domain in code: every business rule you implement, every name you choose and every constraint you enforce is part of a domain model. The only question is whether that model is explicit or accidental.

The same problems then surface later, just more expensively:

- the same rule is implemented in several places and they drift apart;
- invariants hold on some code paths (the API) but not others (admin, bulk updates, scripts);
- it is unclear which objects must change together, so transaction boundaries and consistency rules become accidental;
- renaming or splitting a domain concept forces a schema migration, so refactoring the model means refactoring the database;
- business rules can't be tested without a database;
- logic drifts out of the objects into services, leaving an anemic domain model, where objects are little more than data holders ([Fowler, 2003](#references)).

### Trade-offs

This approach is not free. Separating the domain model from persistence
buys independence and testability, and you pay for it.

- **More code and more layers.** You write the domain classes, the
  persistence models (or tables) and the mapping between them. A simple
  "add a field" change may touch several places.
- **Learning curve.** Teams need to understand aggregates, repositories,
  unit of work and persistence ignorance. Misapplied, DDD vocabulary
  produces ceremony without benefit.

## Goal

Make the benefits of DDD accessible not only to large applications but
also to microservices with complex business logic.

## Out of scope

TODO

## References

- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (Addison-Wesley, 2003), ISBN 0321125215. Evans introduces model-driven design, in which the code is the model.
- Martin Fowler, *Patterns of Enterprise Application Architecture* (Addison-Wesley, 2002), ISBN 0321127420, Chapter 10.
- Martin Fowler, "Anemic Domain Model," martinfowler.com bliki, 25 November 2003, https://martinfowler.com/bliki/AnemicDomainModel.html
- Harry Percival and Bob Gregory, *Architecture Patterns with Python* (O'Reilly, 2020), ISBN 9781492052197. Covers the Repository and Unit of Work patterns, with persistence-ignorant domain code, in Python.
