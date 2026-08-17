# Project Rules

<!--
Copy to the root of a Rust web project as CLAUDE.md (and/or AGENTS.md for other agents).
Adapt paths and commands to the actual layout. Keep this file under about 40 lines:
everything layer-specific belongs in the nested files listed at the bottom.
-->

This is a Rust web service built with Axum, SQLx, and Tokio.

## Architecture

- Three layers: `src/api/` (HTTP), `src/domain/` (business logic), `src/infra/` (database, external APIs).
- Dependencies point inward: api depends on domain, infra depends on domain. Domain depends on nothing external.
- Domain types never import axum, sqlx, reqwest, or any framework crate.
- Handlers are thin: extract request data, call a service method, return a response. No SQL, no business logic.
- Shared state lives in `AppState`, extracted via `State<AppState>` or `FromRef`.

## Code style

- `thiserror` for domain error enums. `anyhow` only inside the catch-all `AppError::Internal` variant.
- Every handler returns `Result<T, AppError>`. Never `unwrap()` or `expect()` in request-handling code.
- Newtypes for domain identifiers and validated values (`Email`, `UserId`). Inner fields private.
- Separate types at each boundary: request DTO, domain entity, database row, response DTO.
  Share a type only when the shapes and invariants are genuinely identical.
- No emdashes in documentation or comments. Clear, direct sentences.

## Database

- All SQL goes through repository or query structs, never handlers.
- `sqlx::query_as!` for compile-time checked queries; parameterized placeholders only.
- `TryFrom<Row>` (not `From`) for row to domain conversions.
- Run `cargo sqlx prepare` after changing queries or migrations and commit `.sqlx/`.

## Testing

- Unit tests for domain logic with in-memory repositories.
- Integration tests via `tower::ServiceExt::oneshot` against the real router.
- Database tests with `#[sqlx::test]` for isolation.
- Test error paths, not only happy paths.

## Security

- Validate input at the API boundary with `ValidatedJson` / `ValidatedQuery`.
- Hash passwords with Argon2id via `spawn_blocking`.
- Never log secrets. Sensitive config values use `SecretString` from `secrecy`.
- CORS, rate limiting, body size limits, and request timeouts are required in production.

## Verification

A change is done when all of these pass:

```
cargo fmt --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo sqlx prepare --check
```

Do not skip any of them.

## Nested instructions

- `src/api/CLAUDE.md` - handlers, middleware, extractors, DTOs
- `src/domain/CLAUDE.md` - models, services, ports, errors
- `src/infra/db/CLAUDE.md` - repositories, queries, migrations
