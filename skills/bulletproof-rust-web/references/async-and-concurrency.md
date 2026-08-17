# Async, Concurrency, Outbound I/O

## Cancellation safety

`tokio::select!` polls all branches, and when one completes it **drops the others**. A
future is cancellation safe if dropping it mid-flight loses nothing.

| Cancellation safe | Not cancellation safe |
|-------------------|------------------------|
| `channel.recv()`, `TcpListener::accept()`, `sleep()`, `CancellationToken::cancelled()`, `interval.tick()` | `read_exact()`, `write_all()`, `read_to_string()` |

```rust
// BROKEN: write_all/read_exact may be dropped after partial progress, corrupting the stream
loop {
    tokio::select! {
        result = socket.read_exact(&mut buf) => process(&buf).await,
        _ = shutdown.cancelled() => return,
    }
}
```

Fix: keep only cancel-safe operations inside `select!` branches and run everything else to
completion in the body.

## The actor loop

The most reliable structure for a concurrent component: wait in `select!`, then process one
message to completion outside it.

```rust
async fn run_worker(mut commands: mpsc::Receiver<Command>, shutdown: CancellationToken) {
    loop {
        let command = tokio::select! {
            cmd = commands.recv() => match cmd {
                Some(c) => c,
                None => return,                 // all senders dropped
            },
            _ = shutdown.cancelled() => {
                tracing::info!("worker shutting down");
                return;
            }
        };

        // Runs to completion. Nothing to cancel halfway.
        process_command(command).await;
    }
}
```

## Common select! mistakes

- Using `select!` where `join!` / `try_join!` was meant. `select!` abandons the loser.
- A `select!` loop where any branch is not cancel-safe: each iteration drops last
  iteration's futures.
- Holding a `MutexGuard` across an await. With `std::sync::Mutex` this blocks the runtime
  thread; with `tokio::sync::Mutex` it serializes for as long as the critical section awaits.
  Prefer an actor that owns the state.
- No `else` branch when every channel can close: `select!` panics once all branches are
  disabled. Keep one branch that cannot close (a cancellation token) or handle `None`.
- Reusing a stored future across iterations requires `tokio::pin!`:

```rust
let sleep_future = tokio::time::sleep(Duration::from_secs(30));
tokio::pin!(sleep_future);

loop {
    tokio::select! {
        _ = &mut sleep_future => break,
        msg = rx.recv() => { /* the sleep continues from where it was */ }
    }
}
```

## Channels

| Type | Shape | Notes |
|------|-------|-------|
| `mpsc::channel(n)` | many senders, one receiver | Bounded by default choice: `send().await` applies backpressure. |
| `mpsc::unbounded_channel()` | same, no limit | Never blocks, can grow without bound. Use only with a reason. |
| `oneshot::channel()` | one message, one direction | Reply channel bundled into a command. |
| `broadcast::channel(n)` | one sender, many receivers | Each subscriber gets a copy; slow ones get `RecvError::Lagged(n)`. |
| `watch::channel(v)` | latest value, many observers | Reloadable configuration, health status. |

## Actor with a typed client

```rust
enum CacheCommand {
    Get { key: String, reply: oneshot::Sender<Option<String>> },
    Set { key: String, value: String },
    Invalidate { key: String },
}

#[derive(Clone)]
pub struct CacheClient { sender: mpsc::Sender<CacheCommand> }

impl CacheClient {
    pub async fn get(&self, key: &str) -> Option<String> {
        let (tx, rx) = oneshot::channel();
        self.sender.send(CacheCommand::Get { key: key.to_string(), reply: tx }).await.ok()?;
        rx.await.ok()?
    }
}

pub fn spawn_cache(shutdown: CancellationToken) -> CacheClient {
    let (tx, rx) = mpsc::channel(64);
    tokio::spawn(run_cache_actor(rx, shutdown));
    CacheClient { sender: tx }
}

async fn run_cache_actor(mut commands: mpsc::Receiver<CacheCommand>, shutdown: CancellationToken) {
    let mut store: HashMap<String, String> = HashMap::new();
    loop {
        let cmd = tokio::select! {
            cmd = commands.recv() => match cmd { Some(c) => c, None => return },
            _ = shutdown.cancelled() => return,
        };
        match cmd {
            CacheCommand::Get { key, reply } => { let _ = reply.send(store.get(&key).cloned()); }
            CacheCommand::Set { key, value } => { store.insert(key, value); }
            CacheCommand::Invalidate { key } => { store.remove(&key); }
        }
    }
}
```

Why it holds up: no locks (the actor owns the state), cancellation resilient, testable by
sending commands, and `CacheClient` is `Clone + Send` so it drops straight into `AppState`.

Choose channels when state needs sequential processing or must be coordinated inside a
`select!` loop. Choose `Arc<RwLock<T>>` or `dashmap` when reads dominate, writes are rare,
and no coordination is needed.

## Multi-subsystem shutdown

```rust
let root_token = CancellationToken::new();

let http_handle    = tokio::spawn(run_http_server(root_token.child_token(), /* ... */));
let worker_handle  = tokio::spawn(run_job_worker(pool.clone(), root_token.child_token()));
let metrics_handle = tokio::spawn(run_metrics_reporter(root_token.child_token()));

wait_for_signal().await;
tracing::info!("shutdown signal received");
root_token.cancel();

let _ = tokio::join!(http_handle, worker_handle, metrics_handle);

pool.close().await;          // only after every consumer has stopped
tracing::info!("shutdown complete");
```

Cancelling the parent cancels every child. Teardown order is the reverse of the dependency
chain: stop accepting connections, drain in-flight requests, stop workers, flush telemetry,
then close the pool. Steps in the middle run concurrently under `join!`.

Axum takes the token directly: `.with_graceful_shutdown(http_token.cancelled_owned())`.

Dynamic task pools drain with `FuturesUnordered`:

```rust
let mut active = FuturesUnordered::new();
loop {
    tokio::select! {
        conn = new_connections.recv() => if let Some(stream) = conn {
            active.push(tokio::spawn(handle_connection(stream, shutdown.child_token())));
        },
        Some(result) = active.next() => { if let Err(e) = result {
            tracing::error!(error = ?e, "connection task panicked"); } },
        _ = shutdown.cancelled() => {
            tracing::info!(active = active.len(), "draining active connections");
            break;
        }
    }
}
while let Some(result) = active.next().await { /* drain phase */ }
```

For long-lived connections, finish pending outbound work (flush buffers, send remaining
notifications, acknowledge messages) before closing the transport.

## Background jobs

```rust
// Fire and forget, acceptable only for non-critical side effects.
tokio::spawn(async move {
    if let Err(e) = email_client.send_welcome(&email).await {
        tracing::error!(error = ?e, "failed to send welcome email");
    }
});
```

Caveats: a panic in an un-awaited task is swallowed with the `JoinHandle`, and a restart
loses in-progress work entirely. Anything that must eventually succeed needs a persistent
queue.

`JoinSet` for a known batch, with results collected and concurrency bounded:

```rust
let mut set = JoinSet::new();
for item in items { let pool = pool.clone(); set.spawn(async move { process_item(&pool, &item).await }); }
while let Some(result) = set.join_next().await {
    match result {
        Ok(Ok(())) => {}
        Ok(Err(e)) => tracing::error!(error = ?e, "item processing failed"),
        Err(e) => tracing::error!(error = ?e, "task panicked"),
    }
}
```

Periodic work:

```rust
let mut ticker = interval(Duration::from_secs(300));
ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);  // default Burst catches up

loop {
    tokio::select! {
        _ = ticker.tick() => { if let Err(e) = cleanup_expired_sessions(&pool).await {
            tracing::error!(error = ?e, "session cleanup failed"); } },
        _ = shutdown.cancelled() => return,
    }
}
```

Persistent queues: `apalis` (Postgres/Redis/SQLite, monitoring, graceful shutdown), `fang`
(cron scheduling, retry backoff, auto-restart on panic), `backie` (Postgres, horizontal
scaling). The shape is always: enqueue a row or message, a worker polls, processes, marks
done or failed, retries with backoff, dead-letters after N attempts.

Background failures have no client to receive them, so make them visible: structured
`tracing::error!` with the correlating ids, retry with backoff, dead-letter, and emit
metrics (success rate, duration, queue depth, retries). Rising queue depth is usually the
first symptom of trouble.

## Outbound HTTP

One shared `reqwest::Client` in `AppState`; it pools connections internally.

```rust
pub fn create_http_client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(10))
        .connect_timeout(Duration::from_secs(3))
        .pool_max_idle_per_host(10)
        .build()
        .expect("failed to create HTTP client")
}
```

Three timeout levels: connect (3 to 5 s), per-request (10 to 30 s), and an overall operation
deadline wrapping the entire retry loop with `tokio::time::timeout`.

Retries: only for connection errors, timeouts, 5xx, and 429. Never for other 4xx or
permanent failures. Exponential backoff with jitter, three to five attempts:

```rust
let base = Duration::from_millis(100 * 2u64.pow(attempt - 1));
let jitter = Duration::from_millis(rand::random::<u64>() % 50);
sleep(base + jitter).await;
```

Retried writes need idempotency: send a stable `Idempotency-Key` header generated once per
operation (not per attempt), or design the call to be naturally idempotent (PUT with a known
id), or do not retry writes at all.

Circuit breaking stops hammering a failing dependency: closed (normal) → open (reject
immediately after a failure threshold) → half-open (one probe) → closed or open again.
`tower-resilience` provides breaker, bulkhead, and retry layers.

Propagate trace context on every outbound call: `traceparent` via `reqwest-tracing` /
`reqwest-middleware`, or at minimum forward `x-request-id`.

Wrap each downstream in a typed client struct (base URL, auth, timeouts, retries, error
mapping in one place). It is the outbound equivalent of the repository pattern:

```rust
pub struct PaymentClient { http: Client, base_url: String, api_key: String }

impl PaymentClient {
    pub async fn charge(&self, amount_cents: i64, currency: &str, idempotency_key: &str)
        -> Result<PaymentResult, PaymentError>
    {
        let response = self.http.post(format!("{}/v1/charges", self.base_url))
            .bearer_auth(&self.api_key)
            .header("Idempotency-Key", idempotency_key)
            .json(&serde_json::json!({ "amount": amount_cents, "currency": currency }))
            .send().await.map_err(PaymentError::Network)?;

        match response.status() {
            s if s.is_success() => response.json().await.map_err(PaymentError::Parse),
            StatusCode::UNPROCESSABLE_ENTITY =>
                Err(PaymentError::Validation(response.text().await.unwrap_or_default())),
            s => Err(PaymentError::Upstream(s)),
        }
    }
}
```

## gRPC with Tonic

Use gRPC for service-to-service calls you control (shared schema, compact wire format,
first-class streaming). Stay with HTTP/JSON for browsers, public APIs, and simple CRUD.

Layout `proto/<service>/v1/*.proto` and version the proto package from day one; generated
client code makes schema changes breaking for every consumer.

```toml
[dependencies]
tonic = "0.14"
tonic-prost = "0.14"
prost = "0.14"

[build-dependencies]
tonic-prost-build = "0.14"     # replaced direct tonic-build usage as of tonic 0.14
```

```rust
// build.rs
tonic_prost_build::configure()
    .build_server(true)
    .build_client(true)
    .compile_protos(&["proto/myservice/v1/users.proto"], &["proto/"])?;
```

Service implementations follow the handler rules exactly: extract from the request, call the
same domain service, map the result. Errors reuse the existing chain through
`impl From<AppError> for tonic::Status`.

Run gRPC and HTTP on separate ports, each in its own `tokio::spawn`, sharing `AppState`, the
pool, and the domain services, each with `serve_with_shutdown(addr, token.cancelled_owned())`.
Same-port protocol detection is possible but rarely worth the edge cases.

Interceptors handle auth; Tower layers (trace, timeout, metrics) apply to Tonic as they do
to Axum. Add `tonic-reflection` so `grpcurl` can explore the service.
