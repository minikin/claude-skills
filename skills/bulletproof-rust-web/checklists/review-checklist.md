# Review Checklist

Run against the diff, whether the code was written by a human or an agent.

## Architecture

- [ ] Dependencies flow inward (api → domain, infra → domain). Domain imports no framework crate.
- [ ] Handlers are thin: extract, call a service, respond. No SQL, no business rules.
- [ ] New types live in the right layer (DTOs in api, entities in domain, rows in infra).
- [ ] No database row types reachable from an API response.
- [ ] No framework types (axum extractors, sqlx types) in domain code.
- [ ] Abstraction is proportionate: no ports, generics, or crates introduced without a need.

## Correctness

- [ ] No `unwrap()` / `expect()` in request-handling paths.
- [ ] Error types are appropriate: domain errors for business violations, `AppError` for HTTP.
- [ ] `?` propagation works end to end (infra error → domain error → `AppError`).
- [ ] Newtypes used for validated domain values, not raw `String` / `Uuid`.
- [ ] Partial updates use PATCH; PUT means full replacement.
- [ ] `Option` is handled explicitly; "not found" is not silently a 500.

## Database

- [ ] Every query parameterized. No string interpolation anywhere in SQL.
- [ ] New queries use `query_as!` for compile-time checking.
- [ ] Row-to-domain conversion uses `TryFrom`, not `From`.
- [ ] Migrations are backward compatible or follow expand/contract.
- [ ] `.sqlx/` metadata regenerated and committed if queries changed.
- [ ] Multi-step writes are wrapped in a transaction.

## Security

- [ ] Input validated at the API boundary (`ValidatedJson` / `ValidatedQuery`).
- [ ] Response DTOs exclude password hashes, internal ids, and other sensitive fields.
- [ ] Protected endpoints actually enforce authentication (`AuthUser` or `route_layer`).
- [ ] Authorization is checked, not just authentication: can a user reach another user's data?
- [ ] No secrets in logs; check `tracing::instrument` fields and skip lists.
- [ ] Rate limiting considered for new public or auth-adjacent endpoints.

## Testing

- [ ] Happy-path integration test exists for each new endpoint.
- [ ] Error-path test exists for the primary failure case.
- [ ] Non-trivial domain logic has unit tests.
- [ ] Tests build the router through the same `create_app` path production uses.

## Operations

- [ ] New handlers carry `#[tracing::instrument]` with sensible `skip` and fields.
- [ ] No blocking calls on the async runtime; CPU work uses `spawn_blocking`.
- [ ] Outbound HTTP calls have connect, request, and overall timeouts.
- [ ] Background tasks observe a `CancellationToken` and drain on shutdown.
- [ ] Log levels are right: `error` for real failures, `info` for business events.

## Gate

- [ ] `cargo fmt --check`
- [ ] `cargo clippy --workspace --all-targets -- -D warnings`
- [ ] `cargo test --workspace`
- [ ] `cargo sqlx prepare --check`
