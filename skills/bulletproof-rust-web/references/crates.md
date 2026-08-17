# Crate Reference

Default picks are marked **bold**. Versions reflect the stack this skill targets
(axum 0.8, sqlx 0.8, tonic 0.14).

## Core framework

| Crate | Purpose | Notes |
|-------|---------|-------|
| **axum** | routing, extractors, handlers | enable `macros` for `#[debug_handler]` |
| **tokio** | async runtime | `features = ["full"]` unless trimming dependencies |
| **tower** | middleware abstractions | `ServiceBuilder`, `ServiceExt::oneshot` for tests |
| **tower-http** | HTTP middleware | cors, compression, trace, timeout, request-id, limit; enable features selectively |
| hyper | HTTP engine | rarely used directly under axum |

## Serialization and data

| Crate | Purpose | Notes |
|-------|---------|-------|
| **serde** | serialization | `features = ["derive"]` |
| **serde_json** | JSON | used by axum's `Json` |
| **uuid** | ids | `features = ["v4", "serde"]`; `v7` for index-friendly ordering |
| **chrono** | dates and times | `features = ["serde"]`, prefer `DateTime<Utc>` |
| **rust_decimal** | exact decimal arithmetic | money and anything where float round-off is unacceptable; store as `NUMERIC` and enable sqlx's `rust_decimal` feature |

## Data types and utilities

| Crate | Purpose | Notes |
|-------|---------|-------|
| derive_more | derives for `Display`, `From`, `Into`, `AsRef`, `Deref`, `Add`, and friends | removes most newtype boilerplate; keep the inner field private and do not derive `DerefMut` or `From` where it would bypass a validating constructor |
| derive_builder | derives a builder with setters and `build()` | good for config structs and test fixtures with many optional fields. Missing required fields fail at runtime in `build()`; when that must be a compile error, use the typestate builder in `domain-modeling.md` |
| once_cell | `Lazy` and `OnceCell` for lazily initialized statics | std now covers most of this with `OnceLock` (1.70) and `LazyLock` (1.80). Reach for once_cell only for an older MSRV or the APIs std lacks |
| smallvec | `Vec` that keeps up to N elements inline | avoids heap allocation in hot paths with small, bounded collections; pointless for large or unbounded ones |
| arrayvec | fixed-capacity `ArrayVec` / `ArrayString`, never heap-allocated | when the maximum length is a hard, known bound; pushing past capacity errors instead of growing |
| thin-vec | `ThinVec`, one pointer wide instead of three | worth it only when the vector is embedded in a type you have millions of, or in enum variants where `Vec` inflates every variant |
| const_format | compile-time string formatting | build route prefixes, version strings, and user-agent constants without runtime work or `lazy_static` |
| ouroboros | macro for self-referential structs | last resort. First try restructuring: store indices instead of references, or share ownership with `Arc`. Self-referential types complicate borrows, `Send`/`Sync` reasoning, and every later refactor |

## Database

| Crate | Purpose | Notes |
|-------|---------|-------|
| **sqlx** | async SQL, compile-time checked | default choice; Postgres, MySQL, SQLite |
| diesel | type-safe ORM and query builder | mature; use `diesel-async` for async |
| sea-orm | ActiveRecord-style async ORM | less control, faster scaffolding |
| axum-sqlx-tx | request-scoped transactions | commits or rolls back per response |

## Errors

| Crate | Purpose | Notes |
|-------|---------|-------|
| **thiserror** | derive typed errors | domain errors, `AppError` |
| **anyhow** | propagate with context | `AppError::Internal`, infra plumbing |

## Validation

| Crate | Purpose | Notes |
|-------|---------|-------|
| **validator** | derive-based validation | `email`, `url`, `length`, `range`, custom |
| garde | alternative validation | different API style |
| axum-valid | prebuilt validated extractors | integrates validator, garde, validify |

## Auth and security

| Crate | Purpose | Notes |
|-------|---------|-------|
| **jsonwebtoken** | JWT encode/decode | pin the algorithm explicitly |
| **argon2** | password hashing | Argon2id; run under `spawn_blocking` |
| **secrecy** | secret protection | `SecretString`: debug-redacted, zeroed on drop |
| axum-login | session-based auth | pluggable backends |
| tower-sessions | session middleware | server-side sessions |
| axum-csrf-sync-pattern | CSRF | OWASP synchronizer token pattern |
| tower-governor | rate limiting | per-IP; per-process counters only |
| jwt-authorizer | JWT with OIDC discovery | key rotation for third-party IdPs |

## Configuration

| Crate | Purpose | Notes |
|-------|---------|-------|
| **config** | layered configuration | env vars with `__` nesting separator |
| **dotenvy** | `.env` loading | call `.ok()`, absent in production is normal |

## Observability

| Crate | Purpose | Notes |
|-------|---------|-------|
| **tracing** | structured logging and spans | the ecosystem standard |
| **tracing-subscriber** | output configuration | `features = ["env-filter", "json"]` |
| tracing-opentelemetry | bridge spans to OTel | |
| opentelemetry, opentelemetry-otlp | distributed tracing export | Jaeger, Tempo, Datadog |
| axum-tracing-opentelemetry | trace context propagation | |
| axum-otel-metrics / axum-prometheus | metrics with Prometheus export | |
| console-subscriber | feeds the tokio-console debugger | async task debugger from [tokio-rs/console](https://github.com/tokio-rs/console): shows running, idle, and blocked tasks, poll times, and resource waits. Requires `RUSTFLAGS="--cfg tokio_unstable"` and tokio's `tracing` feature; keep it behind a dev or debug feature flag, not in production builds |

## API documentation

| Crate | Purpose | Notes |
|-------|---------|-------|
| utoipa | OpenAPI from code | cannot drift from the implementation |
| utoipa-swagger-ui | Swagger UI | serves the generated spec |

## Testing

| Crate | Purpose | Notes |
|-------|---------|-------|
| **tower (`ServiceExt`)** | integration tests without a server | `oneshot()` |
| axum-test | nicer test client | wraps the same mechanism |
| mockall | generated mocks | hand-written fakes are often clearer |

## HTTP client and resilience

| Crate | Purpose | Notes |
|-------|---------|-------|
| **reqwest** | async HTTP client | one shared `Client`, always set timeouts |
| reqwest-middleware / reqwest-tracing | retries, trace propagation | injects `traceparent` |
| tower-resilience | circuit breaker, bulkhead, retry | Tower layers |

## gRPC

| Crate | Purpose | Notes |
|-------|---------|-------|
| tonic | gRPC client and server | Tower-compatible |
| tonic-prost | runtime for prost types | required alongside tonic |
| prost | protobuf | message types |
| tonic-prost-build | codegen in `build.rs` | `[build-dependencies]`, replaces direct tonic-build |
| tonic-reflection | server reflection | lets grpcurl discover the API |

## Async utilities

| Crate | Purpose | Notes |
|-------|---------|-------|
| **tokio-util** | `CancellationToken` | structured shutdown with parent/child tokens |
| futures | `FuturesUnordered`, `StreamExt` | dynamic task pools; the umbrella crate |
| futures-util | combinators for futures, streams, sinks | what `futures` re-exports; depend on it directly to trim compile time, and set `default-features = false` when you only need `StreamExt` |

## Background jobs

| Crate | Purpose | Notes |
|-------|---------|-------|
| apalis | persistent job processing | Postgres/Redis/SQLite, monitoring, graceful shutdown |
| fang | persistent job queue | cron scheduling, retry backoff, auto-restart |
| backie | Postgres-backed task queue | horizontal scaling across processes |

## Concurrency and caching

| Crate | Purpose | Notes |
|-------|---------|-------|
| dashmap | concurrent map, sharded locking | read-heavy shared state; never hold a guard across an `.await` |
| moka | concurrent cache | TTL, size bounds, async variant |
| rayon | work-stealing data parallelism | CPU-bound batches (`par_iter`) off the async runtime; call it from inside `spawn_blocking`, never directly in a handler |
| crossbeam | concurrency primitives for threads | channels, scoped threads, deques, epoch reclamation. For communication between async tasks use `tokio::sync` instead; reach for crossbeam when the other side is a real OS thread |
| parking_lot | faster, smaller `Mutex` / `RwLock` without poisoning | drop-in for `std::sync` locks in synchronous code: `lock()` returns the guard directly, no `unwrap()`. Still a blocking lock: never hold a guard across an `.await`. For state shared between async tasks use `tokio::sync` or an actor |

Pick by access pattern, not by habit: an actor task for state that needs coordination,
`dashmap` or `moka` for read-heavy shared state, `rayon` for CPU batches inside
`spawn_blocking`, `crossbeam` and `parking_lot` only where real OS threads are involved.

## Development tooling

Not dependencies of the service. Install with `cargo install` and run them locally or in CI.

| Tool | Purpose | Notes |
|------|---------|-------|
| cargo-audit | known vulnerabilities in `Cargo.lock` | run in CI; checks the RustSec advisory database |
| cargo-udeps | finds declared dependencies nothing uses | requires a nightly toolchain (`cargo +nightly udeps`). `cargo-machete` is a faster, stable-toolchain heuristic alternative |
| criterion | statistically rigorous benchmarks | tells a real improvement from run-to-run noise |
| samply | sampling CPU profiler | `samply record ./target/release/my-app` opens the trace in the Firefox Profiler UI; build with `debug = true` in the release profile for readable frames |
| cargo-flamegraph | flamegraphs from perf or dtrace | same purpose as samply, different viewer |
| cargo-pgo | profile-guided optimization, and BOLT | `cargo pgo run` to collect profiles, then `cargo pgo optimize`. Needs `rustup component add llvm-tools-preview`. Worth it only after the usual wins (queries, blocking, allocations) are gone, and only with a workload representative of production |
| tokio-console | async task debugger | pairs with the `console-subscriber` crate; see the Observability section |
