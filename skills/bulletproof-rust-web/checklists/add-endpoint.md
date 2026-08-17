# Add an Endpoint

Build the vertical slice from the inside out. Every type the next step needs already exists.

## 1. Plan

- Which domain entities are involved? Can existing types, services, or repositories be reused?
- Which layers change (domain, infra, api)?
- What is the smallest slice that delivers value? List the files to be edited before writing code.

## 2. Domain types

- Add or reuse the entity and value objects in `src/domain/models/`.
- New value objects: private inner field, `parse()` returning `Result`, `as_str()` / `as_ref()`.
- New failure modes: add variants to the relevant error enum, or add a new `thiserror` enum
  with an `Unknown(#[from] anyhow::Error)` catch-all.

## 3. Migration (if the schema changes)

Follow `add-migration.md`. Summary: `cargo sqlx migrate add <description>`, `TIMESTAMPTZ`,
`gen_random_uuid()`, indexes on filtered columns, backward compatibility, then
`cargo sqlx migrate run && cargo sqlx prepare`.

## 4. Repository

- Add the method to the repository in `src/infra/repositories/`.
- `sqlx::query_as!` with parameter placeholders and a `RETURNING` clause on writes.
- `fetch_optional` for lookups; "not found" is `Ok(None)`.
- Map database errors to domain errors (unique violation to `Duplicate`, everything else to
  `Unknown` with `.context()`).
- Return domain types via `TryFrom<Row>`.

## 5. Service

- Add the method to the service in `src/domain/services/` when there is real logic:
  orchestration, authorization, business rules, or CPU work.
- Pure single-query CRUD may call the repository directly from the handler if the project
  has no service layer for that aggregate.
- CPU-heavy work goes through `tokio::task::spawn_blocking`.

## 6. DTOs

- Request DTO in `src/api/dtos/`: `#[derive(Debug, Deserialize, Validate)]` with validation
  attributes and messages.
- Response DTO: `#[derive(Debug, Serialize)]` (plus `ToSchema` when using utoipa). No
  password hashes, no internal-only fields.
- `impl From<DomainEntity> for ResponseDto`.

## 7. Handler

- `src/api/handlers/`: extract, parse raw fields into domain types, call one service method,
  build the response.
- Extract with `ValidatedJson<T>` / `ValidatedQuery<T>`; `AuthUser` when authentication is
  required.
- Return `AppResult<T>`. 201 for create, 204 for delete.
- Keep it under 20 lines. Body-consuming extractors last in the signature.

## 8. Route

- Register in `src/api/routes.rs` under the correct nest and version prefix.
- Correct method: POST create, GET read, PATCH partial update, PUT full replace, DELETE remove.
- Protected endpoints: `route_layer` with the auth middleware, or the `AuthUser` extractor.

## 9. Tests

- Integration test for the happy path via `oneshot`, asserting status and body shape.
- Integration test for the primary error case (validation failure, not found, conflict,
  unauthorized).
- Unit test for non-trivial domain logic using an in-memory repository.
- `#[sqlx::test]` when the query logic itself is worth testing.

## 10. Observability

- `#[tracing::instrument(skip(state, payload))]` on the handler.
- `tracing::info!` with structured, low-PII fields for significant business events.
- OpenAPI annotation if the project uses utoipa.

## 11. Verify

```sh
cargo fmt --check \
  && cargo clippy --workspace --all-targets -- -D warnings \
  && cargo test --workspace \
  && cargo sqlx prepare --check
```

All must pass. Then review the diff against `review-checklist.md`.
