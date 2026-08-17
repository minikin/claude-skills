# Feature Checklist

For a feature that spans several endpoints or entities. A single endpoint is covered by
`add-endpoint.md`.

## Planning

- [ ] Domain entities involved are identified
- [ ] Layers requiring changes are identified (domain, infra, api)
- [ ] Existing types, services, and repositories checked for reuse
- [ ] Migration planned for backward compatibility (expand/contract if destructive)
- [ ] Feature split into vertical slices, each shippable and verifiable on its own

## Domain layer

- [ ] Entities and value objects defined with private fields
- [ ] Constructors validate invariants and return `Result`
- [ ] Domain error enum covers the real failure cases, with an `Unknown` catch-all
- [ ] Service methods orchestrate the business logic; no HTTP or SQL concepts present
- [ ] Ports defined only where a second implementation or isolated testing is actually wanted

## Infrastructure layer

- [ ] Migration created, applied, and reviewed for compatibility
- [ ] Repository methods implemented with compile-time checked queries
- [ ] Row types defined with `TryFrom` conversion to domain entities
- [ ] Database errors mapped to domain errors
- [ ] Multi-step writes are transactional
- [ ] Outbound clients wrapped in a typed struct with timeouts and error mapping

## API layer

- [ ] Request DTOs with validation attributes
- [ ] Response DTOs excluding sensitive fields, with `From<Entity>`
- [ ] Handlers: extract, parse, call service, respond, under 20 lines
- [ ] Routes registered with correct methods and version prefix
- [ ] Authentication and authorization applied where required
- [ ] Pagination on every list endpoint, `per_page` clamped

## Testing

- [ ] Unit tests for non-trivial domain logic
- [ ] Integration tests for happy paths (`oneshot`)
- [ ] Integration tests for primary error paths
- [ ] Authorization tests: cross-user access rejected
- [ ] Database tests where query logic is complex

## Operations

- [ ] Handlers and service methods instrumented with tracing
- [ ] Structured log events for significant business actions, low-PII fields
- [ ] Metrics considered for new queues or long-running work
- [ ] Background tasks handle cancellation and drain cleanly
- [ ] OpenAPI annotations added if the project uses utoipa

## Verification

- [ ] `cargo fmt --check`
- [ ] `cargo clippy --workspace --all-targets -- -D warnings`
- [ ] `cargo test --workspace`
- [ ] `cargo sqlx prepare --check`
- [ ] Diff reviewed against `review-checklist.md`
- [ ] Recurring corrections promoted into the project's `CLAUDE.md`
