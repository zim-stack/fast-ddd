# DDD Primer

## Entity
  An entity is defined by its identity rather than its attributes. Two
    entities are equal when they share an identity root and their `id` values
    match, even if their other fields differ. Entities are owned by an
    aggregate root and are never persisted or loaded on their own; they are
    always accessed through the root.

# Aggregates and boundaries


## Things aggregates are not for

Even in a domain-heavy service, not every operation should go through an
aggregate.

- **Reads and reports.** Aggregates exist to change state while keeping rules
  true. To list orders, show a dashboard or export data, query the database
  directly and return plain data. Loading aggregates to read them wastes the
  copying described above and adds nothing.
- **Bulk updates.** "Mark every order older than a year as archived" is a set
  operation. One SQL statement is better than loading and saving every
  aggregate, as long as it does not bypass a rule that matters. If it does,
  that is a sign the rule needs a home in the domain, not a reason to skip it.
- **Very large aggregates.** An aggregate is loaded and saved as a whole. If one
  holds an unbounded collection (every event ever recorded for a customer, say),
  split it so each aggregate stays small and each transaction touches one of
  them.
