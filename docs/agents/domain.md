# Domain docs

This repository uses a single-context domain-documentation layout.

## Before exploring

Read these sources when they exist and are relevant:

- `CONTEXT.md` at the repository root.
- ADRs under `docs/adr/`.

Missing domain files require no setup warning. The domain-modeling workflow
creates them only when terminology or architectural decisions need recording.

## Layout

```text
/
├── CONTEXT.md
├── docs/
│   └── adr/
└── src/
```

## Vocabulary

Use terms as defined in `CONTEXT.md` in issues, proposals, tests, and code.
Treat an absent concept as a signal to reconsider the term or update the
domain model.

## ADR conflicts

Surface conflicts with an existing ADR explicitly rather than silently
overriding the recorded decision.
