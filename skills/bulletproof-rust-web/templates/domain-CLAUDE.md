# Domain Layer Rules

<!-- Copy to src/domain/CLAUDE.md -->

## Zero external dependencies

This module must not import axum, sqlx, reqwest, tonic, tower, or any framework or
infrastructure crate. Allowed: serde, thiserror, anyhow, uuid, chrono, and the standard
library.

## Models

- Newtypes for identifiers and validated values: `struct UserId(Uuid)`, `struct Email(String)`.
- Inner fields private. Provide a `parse()` constructor returning `Result`.
- Implement `AsRef<str>` or an `as_str()` / `as_uuid()` accessor for read access.
- Once constructed, validity is guaranteed. No downstream re-validation.
- Entities have private fields and getters. Mutation goes through methods that enforce rules.
- The data needed to create an entity is its own type (`NewUser`), separate from the entity.

## Services

- Services are generic over repository traits: `UserService<R: UserRepository>`.
- Services hold business logic: validation, orchestration, authorization decisions.
- Services return domain error types, never HTTP status codes or SQL errors.
- CPU-intensive work (password hashing) runs under `tokio::task::spawn_blocking`.

## Ports (traits)

- Repository traits live in `domain/ports/`.
- Use `-> impl Future<Output = ...> + Send` (native async traits), not `#[async_trait]`,
  for internal ports.
- Bounds are `Send + Sync + 'static`, but not `Clone`: cloneability belongs to the holder.
- Such traits are not object safe. For `dyn` dispatch use `#[async_trait]` or `trait_variant::make`.
- Introduce a port only when a second implementation or database-free testing is actually
  wanted. Otherwise call a concrete repository.

## Errors

- One error enum per operation (`CreateUserError`, `AuthError`).
- `#[error("...")]` messages describe business violations ("user already exists"), not
  infrastructure details ("unique constraint violation").
- Include a catch-all `Unknown(#[from] anyhow::Error)` for unexpected failures.
