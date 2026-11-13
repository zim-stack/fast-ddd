# DDD Primer

## Entity
  An entity is defined by its identity rather than its attributes. Two
    entities are equal when they share an identity root and their `id` values
    match, even if their other fields differ. Entities are owned by an
    aggregate root and are never persisted or loaded on their own; they are
    always accessed through the root.

# Aggregates and boundaries
