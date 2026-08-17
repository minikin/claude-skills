---
name: bulletproof-rust-web
description: >
  Opinionated architecture and production patterns for Rust web services built with Axum,
  Tokio, SQLx, and Tower. Use this skill when: (1) starting or structuring a Rust web
  service or API, (2) adding an endpoint, migration, repository, service, or middleware to
  an Axum project, (3) designing domain types, error handling, or application state for a
  Rust backend, (4) reviewing Rust web code for layering, correctness, or security issues,
  (5) hardening a Rust service for production (observability, graceful shutdown, testing,
  deployment), (6) debugging async pitfalls, cancellation safety, or background jobs in a
  Tokio web service.
license: MIT
metadata:
  source: https://github.com/gruberb/bulletproof-rust-web
  version: "1.0.0"
allowed-tools: Read Write Edit Glob Grep Bash(cargo:*) Bash(sqlx:*) Bash(rustfmt:*) Bash(docker:*)
---

# Bulletproof Rust Web

Structural answers for Rust web services. Distilled from Bastian Gruber's
[bulletproof-rust-web](https://github.com/gruberb/bulletproof-rust-web), the Axum
counterpart to bulletproof-react.

Default stack: **axum 0.8, tokio, tower/tower-http, sqlx (Postgres), thiserror + anyhow,
tracing, validator, secrecy**.

## The five principles

1. **Thin handlers.** Extract, call one service method, respond. 5 to 20 lines. No SQL, no
   business rules, no orchestration of multiple services.
2. **Let the type system work.** Newtypes with private fields and validated constructors,
   `Result` everywhere, traits for layer boundaries. Make invalid states unrepresentable.
3. **Separate what changes for different reasons.** Routing, business rules, and queries
   live in different modules and change independently.
4. **Start simple, evolve deliberately.** Flat modules for a prototype, layered single
   crate for most production apps, workspace only when it earns its keep.
5. **Optimize for the reader.** Clarity and predictability over cleverness.

## The dependency rule

```
api    (axum, http, json)     ──┐
                                ├──► domain  (no framework crates at all)
infra  (sqlx, reqwest, tonic) ──┘
```

Dependencies point inward. `domain/` may import only `serde`, `thiserror`, `anyhow`,
`uuid`, `chrono`, and std. If the domain needs the outside world, it defines a trait
(port) in `domain/ports/` and `infra/` implements it (adapter). A cross-layer import from
domain into api or infra is a defect, not a style preference.

Directory layout, layering, ports and adapters, static vs dynamic dispatch, single crate
vs workspace: see `references/architecture.md`.

## Non-negotiable rules

| Rule                                                                                | Why                                                                                                                                           |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| No `unwrap()` / `expect()` in request-handling code                                 | A panic drops the request and can poison shared state. Use `?` and `.ok_or(AppError::NotFound)?`. `expect()` is allowed only in startup code. |
| Separate types per boundary: request DTO, domain entity, DB row, response DTO       | A new DB column can never leak into an API response. Bridge with `From` / `TryFrom`.                                                          |
| `TryFrom<Row>` for row to domain, never `From`                                      | Stored data may violate current invariants (legacy rows, manual SQL fixes).                                                                   |
| All SQL lives in repositories or query structs, parameterized only                  | No SQL in handlers, no string interpolation, ever.                                                                                            |
| Newtypes for domain values (`Email`, `UserId`, `UserName`)                          | `fn f(String, String)` accepts swapped arguments; `fn f(UserName, Email)` does not.                                                           |
| `thiserror` for typed errors, `anyhow` only inside the catch-all `Internal` variant | Callers match variants; the 500 path just needs context.                                                                                      |
| Internal error details are logged, never returned to the client                     | Error text leaks schema, paths, and internals.                                                                                                |
| Secrets in `SecretString` (`secrecy`), loaded from env, validated at startup        | Debug-redacted, zeroed on drop, never committed.                                                                                              |
| CPU work and blocking I/O go through `spawn_blocking` / `tokio::fs`                 | One blocked worker thread stalls every task on it.                                                                                            |
| Every outbound HTTP call has a timeout                                              | A slow dependency otherwise exhausts your connection pool.                                                                                    |
| Handlers carry `#[tracing::instrument(skip(state, payload))]`                       | Correlated structured logs, no PII, no secrets in span fields.                                                                                |

## Definition of done

A change is complete only when all of these pass:

```sh
cargo fmt --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo sqlx prepare --check     # if the project uses sqlx macros
```

Do not report success with any of them skipped or failing.

## Working on a task

**Plan first.** Name the layers the change touches, the smallest vertical slice that
delivers it, and the files to be edited. Then implement one slice at a time.

**Build inward to outward:** domain types and errors → migration → repository → service →
DTOs → handler → route → tests → tracing → verification gate. The full procedure is in
`checklists/add-endpoint.md`.

**Review your own diff** against `checklists/review-checklist.md` before declaring done.

**Promote corrections.** When the same mistake recurs, write the rule into the project's
`CLAUDE.md` (see `templates/`) instead of only fixing the instance.

## Choosing the level of architecture

| Situation                                                                       | Structure                                                                                                    |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Prototype, a handful of CRUD endpoints, one entry point                         | Flat modules, concrete repository structs, no ports. Handler-local SQL is acceptable if chosen deliberately. |
| Production service maintained by a team (the common case)                       | Single crate, `api` / `domain` / `infra` split, services, thin handlers. Start here.                         |
| Complex domain, several teams, several inbound channels (HTTP + gRPC + workers) | Cargo workspace, one crate per layer, so Cargo enforces the dependency rule.                                 |

Over-engineering costs real time. Add ports, generics, and crates when the problem demands
them, not in anticipation.

## References

Read the file that matches the task; do not load them all.

| File                                         | Read when                                                                                                                                    |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `references/architecture.md`                 | Laying out a project, layering, ports and adapters, wiring the composition root, full vertical slice example                                 |
| `references/domain-modeling.md`              | Designing entities, newtypes, domain errors, conversions between layers, typestate                                                           |
| `references/error-handling.md`               | Building `AppError`, `IntoResponse`, the error chain from sqlx to HTTP                                                                       |
| `references/database.md`                     | Pools, migrations, repositories, transactions, sqlx offline mode                                                                             |
| `references/http-layer.md`                   | Routing, handlers, extractors, validation, middleware order, state, pagination, versioning, OpenAPI                                          |
| `references/auth-and-security.md`            | JWT or session auth, password hashing, authorization, CORS, CSRF, rate limiting, security headers, security checklist                        |
| `references/testing.md`                      | Unit tests with fakes, integration tests via `oneshot`, `#[sqlx::test]`, what to cover                                                       |
| `references/observability-and-deployment.md` | tracing setup, metrics, Docker, health probes, graceful shutdown, performance                                                                |
| `references/async-and-concurrency.md`        | `select!` and cancellation safety, channels and the actor pattern, multi-subsystem shutdown, background jobs, outbound HTTP resilience, gRPC |
| `references/crates.md`                       | Picking a crate for a concern                                                                                                                |
| `references/anti-patterns.md`                | Reviewing code, or explaining why a pattern is wrong                                                                                         |

## Checklists and templates

- `checklists/add-endpoint.md` - full vertical slice for a new endpoint
- `checklists/add-migration.md` - safe schema change, expand/contract, sqlx metadata
- `checklists/review-checklist.md` - architecture, correctness, database, security, testing, ops
- `checklists/feature-checklist.md` - end-to-end feature implementation
- `templates/project-CLAUDE.md` - root rules to copy into a Rust web project
- `templates/domain-CLAUDE.md`, `templates/http-CLAUDE.md`, `templates/db-CLAUDE.md` -
  nested per-layer rules, placed in `src/domain/`, `src/api/`, `src/infra/db/`

When setting up a new project, copy the templates into it and adapt the paths to the
actual layout. Nested files load only when the agent works in that directory.
