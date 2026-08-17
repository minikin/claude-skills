# Observability, Performance, Deployment

## tracing setup

```rust
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

pub fn init_tracing(log_level: &str) {
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(log_level));

    // Runtime configuration, not build profile: a release build in staging should stay
    // readable, a debug build against production data should still emit JSON.
    let json_output = std::env::var("LOG_JSON").map(|v| v == "true" || v == "1").unwrap_or(false);
    let fmt_layer = if json_output { fmt::layer().json().boxed() } else { fmt::layer().pretty().boxed() };

    tracing_subscriber::registry().with(env_filter).with(fmt_layer).init();
}
```

`RUST_LOG=info,my_app::infra=debug,sqlx=warn` tunes verbosity per module at runtime.

## Request spans

```rust
let trace_layer = TraceLayer::new_for_http().make_span_with(|request: &http::Request<_>| {
    let request_id = request.headers().get("x-request-id")
        .and_then(|v| v.to_str().ok()).unwrap_or("unknown");

    // Matched route pattern, not the raw URI. Raw URIs are high-cardinality and
    // overwhelm metrics backends.
    let matched_path = request.extensions()
        .get::<axum::extract::MatchedPath>()
        .map(|p| p.as_str().to_string())
        .unwrap_or_else(|| request.uri().path().to_string());

    tracing::info_span!("http_request",
        method = %request.method(), path = %matched_path, request_id = %request_id)
});
```

Every event emitted while handling the request inherits those fields.

## Instrumenting functions

```rust
#[tracing::instrument(skip(state, payload))]
async fn create_user(
    State(state): State<AppState>,
    ValidatedJson(payload): ValidatedJson<CreateUserDto>,
) -> AppResult<(StatusCode, Json<UserResponse>)> {
    let user = state.user_service.register(payload).await?;
    tracing::info!(user_id = %user.id().as_uuid(), "user created");
    Ok((StatusCode::CREATED, Json(user.into())))
}
```

Logging rules:

- Structured fields, not interpolation: `tracing::info!(user_id = %id, "user created")`.
- Levels: `error` for bugs and failures needing attention, `warn` for unusual but handled,
  `info` for business events, `debug` for operational detail.
- Log low-PII identifiers (user id, tenant id, request id), not emails or names. Correlate
  later from the id.
- `skip` state and payloads. Never log secrets; `secrecy` redacts config values in `Debug`
  but request bodies and headers are on you.

## OpenTelemetry and metrics

Distributed tracing: `opentelemetry`, `opentelemetry_sdk`, `opentelemetry-otlp`,
`tracing-opentelemetry`, `axum-tracing-opentelemetry`. Each request carries a trace id
across service boundaries via the W3C `traceparent` header.

Metrics: `axum-otel-metrics` (Prometheus export) or `axum-prometheus`. Expose `/metrics`
for scraping. The three that catch most problems: request rate by method/path/status,
request duration histogram, error rate. Add queue depth if you run background jobs.

Logs explain one event, traces follow one request across services, metrics show system
trends. Production needs all three.

## Performance

**Never block the runtime.** Tokio runs many tasks on few worker threads; one blocked
thread stalls every task on it. Symptoms appear only under load: latency spikes, throughput
collapse.

```rust
let hash = tokio::task::spawn_blocking(move || hash_password(&password))
    .await.context("password hashing task panicked")??;
```

Common accidental blocking: Argon2/bcrypt hashing, `std::fs`, `std::sync::Mutex::lock()`
held across an await, sync DNS resolution, non-async database drivers (base Diesel is sync;
SQLx and `diesel-async` are not).

`spawn_blocking` is an escape hatch, not a compute scheduler. The blocking pool caps at 512
threads and tasks cannot be aborted once started. For CPU work at high concurrency, bound
it with a `tokio::sync::Semaphore` or move it to `rayon`.

Other levers, in the order they usually pay off:

- Database first: index the columns you filter on, read query plans with `EXPLAIN ANALYZE`,
  select only the columns you need, paginate every list endpoint.
- Tune the pool (2 to 4 connections per core, `acquire_timeout` as the safety net).
- `CompressionLayer` shrinks JSON responses by roughly 70 to 90 percent.
- `Arc` for shared immutable data so state clones stay cheap; borrow instead of allocating
  in hot paths; stream large responses (`axum-streams`) instead of buffering.

Measure before optimizing: Criterion for benchmarks, flamegraph for CPU hotspots, DHAT for
allocations, `tokio-console` (add the `console-subscriber` crate, build with
`RUSTFLAGS="--cfg tokio_unstable"`, keep it behind a dev feature) for runtime and
task-level diagnosis. Micro-optimizing a 2 ms
handler in front of a 50 ms query is wasted effort.

## Docker

```dockerfile
FROM rust:1-slim AS builder
WORKDIR /app

# Cache dependencies. For sturdier caching use cargo-chef.
COPY Cargo.toml Cargo.lock ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release && rm -rf src

COPY . .
RUN touch src/main.rs && cargo build --release

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home appuser
USER appuser
COPY --from=builder /app/target/release/my-app /usr/local/bin/my-app
EXPOSE 3000
CMD ["my-app"]
```

`ca-certificates` is required for outbound HTTPS. A musl static build on `FROM scratch`
gets under 20 MB but leaves no shell for debugging; Debian slim is the usual compromise.

The image is an immutable artifact: same image in every environment, configuration supplied
by the platform's environment variables and secret manager.

## Graceful shutdown

```rust
axum::serve(listener, app)
    .with_graceful_shutdown(shutdown_signal())
    .await?;

async fn shutdown_signal() {
    let ctrl_c = async { signal::ctrl_c().await.expect("failed to install Ctrl+C handler"); };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler").recv().await;
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! { _ = ctrl_c => {}, _ = terminate => {} }
    tracing::info!("shutdown signal received, draining connections");
}
```

Orchestrators send SIGTERM and wait (typically 30 s) before SIGKILL. Without handling it,
in-flight requests are dropped and transactions die mid-flight. For applications with
background subsystems, coordinate with a `CancellationToken`; see `async-and-concurrency.md`.

## Health probes

```rust
async fn health_live() -> StatusCode { StatusCode::OK }

async fn health_ready(State(state): State<AppState>) -> StatusCode {
    if sqlx::query("SELECT 1").execute(&state.db).await.is_ok() {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    }
}
```

```yaml
livenessProbe:  { httpGet: { path: /health,       port: 3000 }, initialDelaySeconds: 5, periodSeconds: 10 }
readinessProbe: { httpGet: { path: /health/ready, port: 3000 }, initialDelaySeconds: 5, periodSeconds: 10 }
```

Liveness is unconditional; a failure restarts the container. Readiness checks dependencies;
a failure only removes the instance from rotation. A liveness probe that pings the database
restarts healthy pods during a brief outage and makes things worse.

## Migrations on deploy

`sqlx::migrate!` at startup is fine for most applications, especially combined with the
readiness probe (traffic waits until migrations finish). With rolling deploys across many
instances, a dedicated migration job or init container gives clearer failure separation.
