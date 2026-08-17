# Architecture

## The three layers

```
┌──────────────────────────────────────────────┐
│  API           handlers, routes, middleware,  │
│                extractors, DTOs               │  knows: axum, http, json
├──────────────────────────────────────────────┤
│  Domain        models, services, ports,       │
│                business rules, domain errors  │  knows: nothing external
├──────────────────────────────────────────────┤
│  Infra         repositories, db, http clients │  knows: sqlx, reqwest, tonic
└──────────────────────────────────────────────┘
```

Dependencies point inward. API depends on domain. Infra depends on domain. Domain depends
on neither. The payoffs are concrete:

- Business logic is testable with an in-memory repository, no Postgres required.
- The domain is reusable from a CLI, a worker, or a gRPC service.
- Swapping the database rewrites `infra/` only.

## Single-crate layout (start here)

```
my-app/
├── Cargo.toml
├── .env.example                 # documents required vars, no real values
├── migrations/
│   └── 20240101000000_create_users.sql
├── src/
│   ├── main.rs                  # config, tracing, serve. Nothing else.
│   ├── lib.rs                   # module declarations + create_app()
│   ├── config.rs
│   ├── error.rs                 # AppError, AppResult
│   ├── observability.rs
│   ├── domain/
│   │   ├── models/              # entities and value objects
│   │   ├── errors.rs
│   │   ├── ports/               # trait definitions (optional)
│   │   └── services/
│   ├── infra/
│   │   ├── db.rs                # pool creation
│   │   └── repositories/
│   └── api/
│       ├── routes.rs
│       ├── state.rs             # AppState
│       ├── handlers/
│       ├── extractors/          # ValidatedJson, AuthUser
│       ├── middleware/
│       └── dtos/
└── tests/
    ├── common/                  # test_app() helper
    └── api/
```

Rules that make the layout work:

- Group by layer first, by concern second. Once a layer holds more than roughly 5 to 10
  domain concepts, regroup by feature slice inside it (`domain/users/{model,service,port,errors}.rs`).
- `main.rs` does three things: load config, build the app, serve.
- `lib.rs` exposes `create_app()` so integration tests exercise the same wiring production does.
- Use `pub(crate)` and private visibility to keep implementation details from escaping a module.

```rust
// main.rs
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config = Config::from_env()?;
    observability::init_tracing(&config.log_level);

    let app = my_app::create_app(config.clone()).await?;

    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{}", config.port)).await?;
    tracing::info!("listening on {}", listener.local_addr()?);
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}
```

```rust
// lib.rs
pub async fn create_app(config: Config) -> anyhow::Result<Router> {
    let pool = infra::db::create_pool(config.database_url.expose_secret()).await?;
    sqlx::migrate!("./migrations").run(&pool).await?;

    let state = AppState::new(config, pool);
    Ok(api::routes::router(state))
}
```

## Workspace layout (when it earns its keep)

Move to a workspace when compile times hurt, when several teams need hard boundaries, when
crates must be published separately, or when multiple binaries (api, worker, cli) share a
domain.

```
crates/
├── domain/   # deps: serde, thiserror, uuid, chrono          (no axum, no sqlx)
├── infra/    # deps: domain, sqlx, reqwest
├── api/      # deps: domain, infra, axum, tower, tower-http
└── shared/   # deps: config, observability
```

```toml
[workspace]
members = ["crates/*"]
resolver = "2"

[workspace.dependencies]
tokio = { version = "1", features = ["full"] }
axum = { version = "0.8", features = ["macros"] }
sqlx = { version = "0.8", features = ["runtime-tokio-rustls", "postgres", "uuid", "chrono", "migrate"] }
tower-http = { version = "0.6", features = ["cors", "compression-gzip", "trace", "timeout", "request-id", "limit"] }
thiserror = "2"
anyhow = "1"
```

Member crates inherit with `serde.workspace = true`. The win: Cargo, not code review,
enforces the dependency rule. A `use sqlx::…` in the domain crate fails to build.

## Ports and adapters

The domain declares what it needs; infra provides it.

```rust
// domain/ports/user_repository.rs  - imports only domain types
use std::future::Future;

pub trait UserRepository: Send + Sync + 'static {
    fn create(&self, new_user: &NewUser)
        -> impl Future<Output = Result<User, CreateUserError>> + Send;

    fn find_by_id(&self, id: &UserId)
        -> impl Future<Output = Result<Option<User>, anyhow::Error>> + Send;

    fn find_by_email(&self, email: &Email)
        -> impl Future<Output = Result<Option<User>, anyhow::Error>> + Send;
}
```

Notes on the bounds:

- `Send + Sync + 'static` because Axum shares state across tasks and threads.
- Native `async fn` / `-> impl Future` in traits is stable since Rust 1.75. No
  `#[async_trait]` needed for internal ports.
- Such traits are **not object safe**: `Arc<dyn UserRepository>` will not compile. Use
  generics (static dispatch) by default; reach for `#[async_trait]` only when you truly
  need `dyn`.
- For public library traits, `trait_variant::make` generates a `Send` variant so callers
  can add bounds without a breaking change.
- Do not put `Clone` on the trait. Cloneability belongs to the holder (`Arc`, `AppState`).

The adapter lives in infra and translates infrastructure errors into domain errors:

```rust
// infra/repositories/user_repo.rs
impl UserRepository for PostgresUserRepo {
    async fn create(&self, new_user: &NewUser) -> Result<User, CreateUserError> {
        let row = sqlx::query_as!(UserRow, r#"..."#, /* binds */)
            .fetch_one(&self.pool)
            .await
            .map_err(|e| match e {
                sqlx::Error::Database(ref db) if db.is_unique_violation() =>
                    CreateUserError::Duplicate { email: new_user.email.clone() },
                other => CreateUserError::Unknown(
                    anyhow::anyhow!(other).context("failed to insert user")),
            })?;

        row.try_into().map_err(CreateUserError::Unknown)
    }
}
```

## Services

Services live in the domain, hold ports as generic parameters, and own the business logic.
They never see HTTP status codes or SQL errors.

```rust
#[derive(Clone)]
pub struct UserService<R: UserRepository> { repo: R }

impl<R: UserRepository> UserService<R> {
    pub fn new(repo: R) -> Self { Self { repo } }

    pub async fn register(&self, name: UserName, email: Email, password: &str)
        -> Result<User, CreateUserError>
    {
        let password = password.to_string();
        let password_hash = tokio::task::spawn_blocking(move || hash_password(&password))
            .await
            .map_err(|e| CreateUserError::Unknown(e.into()))?
            .map_err(CreateUserError::Unknown)?;

        self.repo.create(&NewUser { name, email, password_hash }).await
    }
}
```

## Static vs dynamic dispatch

|              | Static (`UserService<R: UserRepository>`) | Dynamic (`Arc<dyn UserRepository>`)                |
| ------------ | ----------------------------------------- | -------------------------------------------------- |
| Cost         | Monomorphized, zero runtime overhead      | One vtable hop, negligible next to a DB round-trip |
| Async traits | Works with native `async fn` in traits    | Requires `#[async_trait]` (object safety)          |
| Signatures   | Type parameters propagate through layers  | Simpler, uniform signatures                        |

Default to static dispatch. Switch when you need to pick an implementation at runtime, or
when generic parameters have spread far enough to hurt readability.

## Hexagonal, onion, clean

Different names for the same rule: domain at the centre, frameworks at the edges,
dependencies inward. Inbound adapters (HTTP handlers, gRPC services, CLI) call into the
domain; outbound adapters (repositories, HTTP clients) are called by it. Adopt the rule,
not the vocabulary.

## Composition root

`main.rs` (or `create_app`) is the single place that picks concrete types:

```rust
let pool = create_pool(config.database_url.expose_secret()).await?;
sqlx::migrate!("./migrations").run(&pool).await?;

let user_repo    = PostgresUserRepo::new(pool.clone());   // infra
let user_service = UserService::new(user_repo);           // domain
let state        = AppState { config: Arc::new(config), db: pool, user_service };
let app          = api::routes::router(state);            // api
```

## One complete vertical slice

`POST /api/v1/users`, layer by layer:

1. `domain/models/user.rs` - `UserId`, `Email`, `UserName`, `User` (private fields,
   getters, `hydrate` constructor), `NewUser { name, email, password_hash }`.
   `User` has no `password_hash` field, so it cannot be leaked.
2. `domain/errors.rs` - `CreateUserError::{Duplicate { email }, Unknown(#[from] anyhow::Error)}`.
3. `domain/ports/user_repository.rs` - the trait shown above.
4. `domain/services/user_service.rs` - hashes the password on a blocking thread, builds
   `NewUser`, calls `repo.create`.
5. `infra/repositories/user_repo.rs` - `UserRow` (`sqlx::FromRow`), `TryFrom<UserRow> for User`,
   `query_as!` with `RETURNING`, unique violation mapped to `CreateUserError::Duplicate`.
6. `api/dtos/user_dto.rs` - `CreateUserDto` (`Deserialize + Validate`), `UserResponse`
   (`Serialize`, no hash), `impl From<User> for UserResponse`.
7. `error.rs` - `AppError`, `IntoResponse`, `impl From<CreateUserError> for AppError`.
8. `api/handlers/users.rs` - fourteen lines: parse into domain types, call the service,
   return `(StatusCode::CREATED, Json(user.into()))`.
9. `api/routes.rs` - `.route("/", post(create_user))` nested under `/api/v1/users`.

Request flow:

```
CreateUserDto → ValidatedJson checks shape → handler parses UserName/Email
  → service hashes password → NewUser → repo.create → INSERT ... RETURNING
  → UserRow → TryFrom → User → UserResponse → 201 Created
unique violation → CreateUserError::Duplicate → AppError::Conflict → 409
```

Every boundary converts explicitly. Once the first feature is built this way, every later
feature is the same shape.
