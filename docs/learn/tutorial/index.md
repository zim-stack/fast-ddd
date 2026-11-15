# Tutorial
<!-- 
One running example (e.g. orders or bookings) that grows each chapter. 
Every chapter should end in runnable, tested code.
-->
In this tutorial you build the domain core of a small **ordering** service, one
chapter at a time. Each chapter adds a few concepts to the same running example
and ends with code you can run and tests that pass.

## What we build

A customer creates an order, adds lines to it (a product, a quantity and a unit
price), then either places or cancels it. The business rules we model along the
way:

- an order belongs to one customer and has a currency;
- lines can only be added or removed while the order is a draft;
- a line has a positive quantity, and an order has at most one line per product;
- an order can only be placed when it has at least one line;
- placing or cancelling an order is announced with a domain event.

By the end you have an `Order` aggregate with inner entities, value objects,
invariants and domain events. All of it runs and is tested **without a
database**: the domain model knows nothing about tables or sessions.

## Prerequisites

- Python 3.13 or newer, and {{ project_name }} installed
  (see [Getting started](../getting-started.md)).
- `pytest` to run the tests: `pip install pytest`.
- Some familiarity with Python dataclasses. No prior DDD knowledge is needed; the
  [glossary](../glossary.md) explains the vocabulary as it appears.

The tutorial uses standard-library **dataclasses**, so it needs no extra
dependency. [Chapter 1](modeling-the-domain.md) shows the attrs equivalent, and
the [FAQ](../faq/why-attrs.md) explains when you might prefer it.

## Chapters

1. [Modeling the domain](modeling-the-domain.md): identity, state and snapshot,
   and your first aggregate.
2. [Entities and value objects](entities-and-value-objects.md): order lines as
   inner entities, and `Money` as a value object.
3. [Aggregates and invariants](aggregates-and-invariants.md): commands, rules
   that must always hold, and domain events.

Next, the tutorial moves to the layers around the domain:
[persistence mapping](persistence-mapping.md),
[repositories](repositories.md) and the [unit of work](unit-of-work.md).

## How to follow along

- Code blocks are cumulative. Put them in one module (for example
  `shop/domain/order.py`) and let each chapter replace the classes it changes.
- Every chapter ends with a **Test it** section. Collect those functions in a
  test file and run `pytest`; they should all pass at the end of each chapter.
- For testing patterns beyond the tutorial, see the how-to guide
  [Test aggregates](../how-to/test-aggregates.md).
