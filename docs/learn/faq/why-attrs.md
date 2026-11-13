
## Why attrs?
Current design gives each entity a mutable State and a frozen Snapshot, and a snapshot subclass may need to extend a base that isn't frozen. Dataclasses reject this at class creation, and attrs allows it. That single constraint is the main reason the core is on attrs.
