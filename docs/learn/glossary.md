# Glossary

Short definitions of the terms used across these docs, with links to where they
are explained in context.

### Active Record

A pattern where a model class corresponds to a database row and saves itself.
Django's ORM and Tortoise ORM work this way. It is simple and works well for
CRUD, and it ties the domain model to the schema. See
[Motivation](../about/motivation.md).

### Aggregate

A cluster of objects (an [aggregate root](#aggregate-root) and its
[inner entities](#inner-entity) and [value objects](#value-object)) that is
treated as one unit for changes. It is a **consistency boundary**: the
[invariants](#invariant) of the whole cluster hold every time the aggregate is
saved. In {{ project_name }}, `Aggregate` is a base class built from and
producing a [snapshot](#snapshot). See
[Entities and aggregates](concepts/entities-and-aggregates.md) and the
[tutorial](tutorial/aggregates-and-invariants.md).

### Aggregate root

The one object through which the outside world reaches an aggregate. Everything
else in the cluster is reached through it, and only the root is loaded and saved
directly. In an order with lines, the order is the root.

### Anemic domain model

A model whose objects are little more than data holders, with the business logic
living in separate services. {{ project_name }} pushes behavior into the
aggregate instead. See [Motivation](../about/motivation.md).

### Data Mapper

A pattern that keeps domain objects and the database independent by putting the
mapping between them in a separate layer. See
[Map an aggregate to an ORM](how-to/map-aggregate-to-orm.md).

### Domain error

An exception that signals a broken business rule, as opposed to a bug. Giving
rule violations their own type lets callers handle them deliberately. See the
[tutorial](tutorial/entities-and-value-objects.md).

### Domain event

An immutable fact, in the past tense, that an aggregate records when something
business-relevant happens (`OrderPlaced`). Aggregates record events with
`record_event()` and hand them out with `pull_domain_events()`. See
[Aggregates and invariants](tutorial/aggregates-and-invariants.md).

### Entity

An object defined by its **identity**, not its values. It can change over time
and remain the same entity. Two entities are equal when they share an
[identity space](#identity-space) and an `id`, whatever their other fields hold.

### Identity

The `id` that makes an [entity](#entity) the same thing over time. It must not be
`None`, must be hashable, and cannot be reassigned.

### Identity space

The set of classes whose entities can be equal to each other. Each concrete
aggregate or entity class is its own identity space, and a subclass of a
concrete class shares its parent's. An `abstract` base class is not an identity
space. So a `Candidate` and a `Recruiter` with the same `id` are different
aggregates.

### Inner entity

An [entity](#entity) that lives inside an [aggregate](#aggregate) and is only
reached through its root, such as an order line. Its `id` is only unique within
its aggregate.

### Invariant

A rule that must be true whenever the aggregate is stored, such as "a placed
order has at least one line". An aggregate checks its invariants in
`validate_invariants()`, which runs before every snapshot. See
[Aggregates and invariants](tutorial/aggregates-and-invariants.md).

### Persistence ignorance

The domain model knows nothing about how it is stored: no tables, sessions or
SQL. It is what lets you test business rules without a database.

### Repository

An abstraction that lets the application load and save aggregates as if they were
an in-memory collection. It deals in aggregates (or their snapshots) and hides
the storage. See the [tutorial](tutorial/repositories.md).

### Snapshot

A frozen, deeply immutable copy of an entity's state. It is what you persist,
publish or hand to other layers, and what an aggregate is rebuilt from.
Snapshots compare by value, unlike entities. See
[Modeling the domain](tutorial/modeling-the-domain.md).

### State

The mutable working data of an entity, private to it as `_state`. Outside code
changes it only through the entity's methods.

### State-only field

A state field that is not part of the snapshot. It needs a default and is reset
to it whenever the entity is rebuilt, so it suits transient or derived data.

### Structural class

A state or snapshot class that does not derive from the library's base classes.
It is an attrs class or dataclass with an `id` field, and any snapshot must be
frozen. See [Base classes or structural classes?](faq/state-base-vs-structural.md).

### Unit of Work

An abstraction that tracks the changes made during one business operation and
commits them together. See the [tutorial](tutorial/unit-of-work.md).

### Value object

An object defined by its **values**, with no identity. It is immutable, and two
with equal values are interchangeable (`Money(100, "EUR")`). See
[Entities and value objects](tutorial/entities-and-value-objects.md).
