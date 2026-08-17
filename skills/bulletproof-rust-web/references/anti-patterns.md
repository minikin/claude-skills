# Anti-Patterns

Each entry: what it looks like, why it hurts, what to do instead.

## SQL in handlers

`sqlx::query!` calls, transactions, and database error mapping inside the handler body.

Welds HTTP to the database schema. The handler cannot be tested without a database, the
query cannot be reused by a worker or a second endpoint, and query changes edit a file that
is supposed to be about HTTP.

Move database access into a repository or query struct. The handler calls a service or
repository method and sees only domain types.

*Acceptable when:* the service is small and CRUD-shaped, each endpoint maps to one or two
queries, and a second entry point is not realistic. Make it a deliberate choice, and extract
as soon as a query is duplicated across handlers or a handler orchestrates several queries
that must succeed together.

## Fat handlers

One function that validates, hashes, queries, sends an email, publishes an event, and builds
the response.

Impossible to test in isolation, hard to read, and a second entry point for the same logic
means duplicating all of it.

Keep handlers to extract, call one service method, respond. Past 15 to 20 lines, extract.

## `unwrap()` in request paths

A panic kills that request with an opaque 500, and a panic while holding a mutex poisons it
for other requests. Use `?`, and `.ok_or(AppError::NotFound)?` for `Option`. Reserve
`unwrap()` for provably-present values (a compiled regex) and `expect()` for startup code
where a missing value means the process cannot run.

## Leaking database types into the API

One struct deriving both `sqlx::FromRow` and `serde::Serialize`, returned as `Json<UserRow>`.

Adding a column silently adds it to the API response, including password hashes, internal
flags, and soft-delete markers. Renaming a column becomes a breaking API change.

Keep `UserRow`, `User`, and `UserResponse` distinct, bridged by explicit `From` / `TryFrom`.

## Exposing internal errors to clients

Raw database, filesystem, or upstream error text in the response body leaks table names,
paths, queries, and internals, and describes implementation rather than the business
problem. Log the full chain at `error` level, return a generic message via
`AppError::Internal`.

## Hardcoded secrets

A JWT secret or database password as a literal, or a committed `.env`. Everyone with repo
access, every CI checkout, and anyone who finds the repo has your credentials. Load from
environment variables, wrap in `SecretString`, git-ignore `.env`, commit `.env.example`.

## Cross-layer imports

Domain importing an Axum extractor or a `PgPool`.

Breaks the dependency rule: the domain can no longer be used from a CLI without dragging in
the HTTP framework, or tested without a database. Dependencies point inward; when the domain
needs the outside world it declares a trait and infra implements it.

## Blocking the async runtime

CPU-heavy work (Argon2), `std::fs`, or blocking library calls inside an async handler.

A blocked worker thread stalls every task scheduled on it. Symptoms are latency spikes and
throughput collapse under concurrency, which are hard to attribute.

Use `tokio::task::spawn_blocking` for CPU work, `tokio::fs` for files, and an async-native
driver (SQLx, `diesel-async`; base Diesel is synchronous).

## String-typed domain values

`fn f(name: String, email: String, password: String)` accepts any permutation and the
compiler is fine with it. Validation logic scatters because no single place owns the
invariant. Use newtypes with validated constructors.

## Missing or wrong health checks

No probes at all, or a liveness probe that checks the database. Without probes the
orchestrator cannot restart a stuck process or drain a broken instance. A liveness probe
that depends on the database restarts healthy pods during a brief outage and amplifies it.
Liveness unconditional, readiness checks dependencies.

## Over-engineering from the start

Three workspace crates, generic trait-based repositories, CQRS, and an event bus for five
CRUD endpoints.

Every layer of indirection is another thing to understand, another place for bugs, another
barrier to change. Start with the simplest structure that keeps layers clean and add
abstraction when the problem demands it. Flat to layered is an easy refactor when module
boundaries are already sane.
