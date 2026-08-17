# HTTP Layer

## Routing

```rust
use axum::{routing::{get, post}, Router};

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health_live))
        .route("/health/ready", get(health_ready))
        .nest("/api/v1", api_routes())
        .with_state(state)
}

fn api_routes() -> Router<AppState> {
    Router::new()
        .nest("/users", user_routes())
        .nest("/posts", post_routes())
}

fn user_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(list_users).post(create_user))
        .route("/{id}", get(get_user).patch(update_user).delete(delete_user))
}
```

- Plural resource nouns, one function (or file) per route group.
- Health endpoints live outside the versioned prefix so they stay stable.
- `PATCH` for partial updates, `PUT` only for full replacement.
- Path params in axum 0.8 use `{id}`, not `:id`.

## Handlers

Shape: extract, parse into domain types, call one service method, respond.

```rust
#[tracing::instrument(skip(state, payload))]
async fn create_user(
    State(state): State<AppState>,
    ValidatedJson(payload): ValidatedJson<CreateUserDto>,
) -> AppResult<(StatusCode, Json<UserResponse>)> {
    let name = UserName::parse(&payload.name).map_err(|e| AppError::Validation(e.to_string()))?;
    let email = Email::parse(&payload.email).map_err(|e| AppError::Validation(e.to_string()))?;

    let user = state.user_service.register(name, email, &payload.password).await?;

    Ok((StatusCode::CREATED, Json(user.into())))
}

async fn get_user(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<UserResponse>> {
    let user = state.user_service
        .get_by_id(UserId::from_uuid(id)).await?
        .ok_or(AppError::NotFound)?;
    Ok(Json(user.into()))
}

async fn delete_user(State(state): State<AppState>, Path(id): Path<Uuid>)
    -> AppResult<StatusCode>
{
    state.user_service.delete(UserId::from_uuid(id)).await?;
    Ok(StatusCode::NO_CONTENT)
}
```

Belongs in a handler: extraction, parsing raw input into domain types, one service call,
response construction. Does not belong: SQL, business rules, coordinating several services,
complex branching, emails and other side effects.

Over ~20 lines means logic leaked in. Push it into a service method.

`#[axum::debug_handler]` turns opaque trait-bound errors into readable ones; it has no
runtime cost, so leaving it on is fine.

## Extractors

Built-ins: `State`, `Path`, `Query`, `Json`, `TypedHeader`. Body-consuming extractors
(`Json`, `Form`, `ValidatedJson`) implement `FromRequest` and must come **last** in the
argument list; everything else implements `FromRequestParts`.

Custom extractor combining deserialization and validation:

```rust
pub struct ValidatedJson<T>(pub T);

impl<T, S> FromRequest<S> for ValidatedJson<T>
where
    T: serde::de::DeserializeOwned + Validate,
    S: Send + Sync,
{
    type Rejection = AppError;

    async fn from_request(req: Request, state: &S) -> Result<Self, Self::Rejection> {
        let Json(value) = Json::<T>::from_request(req, state)
            .await
            .map_err(|e| AppError::Validation(format!("invalid JSON: {e}")))?;

        value.validate()
            .map_err(|e| AppError::ValidationFields(format_validation_errors(&e)))?;

        Ok(Self(value))
    }
}

fn format_validation_errors(errors: &validator::ValidationErrors) -> HashMap<String, Vec<String>> {
    errors.field_errors().iter().map(|(field, errs)| {
        let messages = errs.iter().map(|e| {
            e.message.as_ref().map(|m| m.to_string())
                .unwrap_or_else(|| format!("{field} is invalid"))
        }).collect();
        (field.to_string(), messages)
    }).collect()
}
```

`ValidatedQuery<T>` is the same idea on `FromRequestParts` wrapping `Query<T>`.
Ready-made alternatives: `axum-valid`, `axum-validated-extractors`. Rolling your own is
worth it when you have opinions about the error body.

DTO validation:

```rust
#[derive(Debug, Deserialize, Validate)]
pub struct CreateUserDto {
    #[validate(length(min = 2, max = 50, message = "name must be 2 to 50 characters"))]
    pub name: String,
    #[validate(email(message = "must be a valid email address"))]
    pub email: String,
    #[validate(length(min = 8, message = "password must be at least 8 characters"))]
    pub password: String,
}
```

Error body clients can act on:

```json
{ "error": { "type": "validation_error", "message": "request validation failed",
             "fields": { "email": ["must be a valid email address"] } } }
```

## Middleware

Tower layers wrap the service. The first layer added is the outermost: it sees the request
first and the response last.

```rust
let app = Router::new()
    .merge(api_routes())
    .layer(
        ServiceBuilder::new()
            .layer(CompressionLayer::new())
            .layer(SetRequestIdLayer::x_request_id(MakeRequestUuid))
            .layer(TraceLayer::new_for_http())
            .layer(PropagateRequestIdLayer::x_request_id())
            .layer(TimeoutLayer::new(Duration::from_secs(30)))
            .layer(RequestBodyLimitLayer::new(1024 * 1024))   // 1 MB
            .layer(cors_layer(&config))
    )
    .with_state(state);
```

Order rationale: compression outermost so it wraps the finished body; request id before
tracing so spans carry it; propagate after tracing so the response header is set before the
span closes; timeout and body limit protect everything inside.

`.layer()` vs `.route_layer()`: `.layer()` applies to everything including the fallback, so
an auth layer there turns 404s into 401s. `.route_layer()` applies only to matched routes.
Use `route_layer` for authentication and authorization.

Custom middleware as a function:

```rust
async fn auth_middleware(
    State(state): State<AppState>,
    mut req: Request,
    next: Next,
) -> Result<Response, AppError> {
    let token = req.headers().get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(AppError::Unauthorized)?;

    let claims = decode_jwt(token, state.config.jwt_secret.expose_secret())
        .map_err(|_| AppError::Unauthorized)?;

    req.extensions_mut().insert(AuthUser::from(claims));
    Ok(next.run(req).await)
}

let protected = Router::new()
    .nest("/users", user_routes())
    .route_layer(middleware::from_fn_with_state(state.clone(), auth_middleware));
```

Check tower-http before writing your own: CORS, compression, trace, timeout, request id,
body limit, and more. Also `tower-governor` (rate limiting), `tower-sessions`,
`tower-cookies`, `axum-csrf-sync-pattern`.

## State

```rust
#[derive(Clone, FromRef)]
pub struct AppState {
    pub config: Arc<Config>,
    pub db: PgPool,
    pub user_service: UserService<PostgresUserRepo>,
    pub post_service: PostService<PostgresPostRepo>,
}

impl AppState {
    pub fn new(config: Config, pool: PgPool) -> Self {
        let user_repo = PostgresUserRepo::new(pool.clone());
        Self {
            config: Arc::new(config),
            db: pool.clone(),
            user_service: UserService::new(user_repo),
            post_service: PostService::new(PostgresPostRepo::new(pool)),
        }
    }
}
```

- `AppState` must be `Clone`; Axum clones it per handler call. `Arc` the large read-only
  parts; `PgPool` is already cheap to clone.
- `#[derive(FromRef)]` lets handlers extract a single field: `State(user_service): State<UserService<...>>`.
- `State` is compile-time checked; `Extension` is a runtime type map. Use `State` for
  startup-wired dependencies, `Extension` only for per-request values injected by middleware.
- Do not put `std::sync::Mutex` in state. Use `tokio::sync::RwLock`, `dashmap`, or `moka`
  for shared mutable state, or an actor task (see `async-and-concurrency.md`).
- Build state once at startup. Never construct services or repositories inside a handler.

## Configuration

```rust
#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    #[serde(default = "default_port")]
    pub port: u16,
    #[serde(default = "default_environment")]
    pub environment: Environment,
    pub database_url: SecretString,
    pub jwt_secret: SecretString,
    #[serde(default = "default_log_level")]
    pub log_level: String,
    #[serde(default)]
    pub cors_origins: Vec<String>,
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        dotenvy::dotenv().ok();                 // absent in production, that is fine

        let parsed: Config = config::Config::builder()
            .add_source(config::Environment::default().separator("__"))
            .build().context("failed to build configuration")?
            .try_deserialize().context("failed to deserialize configuration")?;

        parsed.validate()?;
        Ok(parsed)
    }

    fn validate(&self) -> anyhow::Result<()> {
        if self.jwt_secret.expose_secret().len() < 48 {
            anyhow::bail!("JWT_SECRET must be at least 48 characters");
        }
        Ok(())
    }
}
```

- Fail at startup, loudly, on missing or invalid config. Never discover it on first request.
- `Environment` is an enum, not a string, so behaviour switches are exhaustive and typo-proof.
- Secrets are `SecretString`: redacted in `Debug`, zeroed on drop, exposed only at the point
  of use via `.expose_secret()`.
- `.env` is git-ignored; ship a `.env.example` documenting the variables.
- Runtime behaviour (CORS policy, log format) keys off `config.environment`, never
  `cfg!(debug_assertions)`.

## API design

| Code | Use |
|------|-----|
| 200 | successful read or update |
| 201 | resource created |
| 204 | success with no body (delete) |
| 400 | invalid input, validation failure |
| 401 | missing or invalid authentication |
| 403 | authenticated but not permitted |
| 404 | resource does not exist |
| 409 | business rule violation (duplicate) |
| 422 | semantically invalid request |
| 500 | unexpected server failure |

Consistent envelopes:

```rust
#[derive(Serialize)] pub struct ApiResponse<T: Serialize> { pub data: T }

#[derive(Serialize)] pub struct PaginatedResponse<T: Serialize> {
    pub data: Vec<T>,
    pub meta: PaginationMeta,
}

#[derive(Serialize)] pub struct PaginationMeta {
    pub page: u32, pub per_page: u32, pub total: u64, pub total_pages: u32,
}
```

Pagination on every list endpoint. Offset-based is fine for moderate, stable datasets;
clamp `per_page`:

```rust
let per_page = params.per_page.clamp(1, 100);
let offset = params.page.saturating_sub(1) * per_page;
```

Cursor-based pagination for large or churning datasets (or the `paginator-axum` crate).
Only allow sorting on indexed columns.

Versioning: `/api/v1` from day one for public APIs; add `/api/v2` alongside when needed and
keep handlers decoupled from the version prefix. For internal services shipping in lockstep,
disciplined additive schema evolution matters more than a prefix.

OpenAPI with `utoipa`: annotate handlers with `#[utoipa::path(...)]`, derive `ToSchema` on
DTOs, collect them in an `#[derive(OpenApi)]` struct, and serve `utoipa-swagger-ui`. The
spec is generated from the code, so it cannot drift.

Health endpoints:

```rust
async fn health_live() -> StatusCode { StatusCode::OK }   // unconditional

async fn health_ready(State(state): State<AppState>) -> StatusCode {
    match sqlx::query("SELECT 1").execute(&state.db).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::SERVICE_UNAVAILABLE,
    }
}
```

Liveness never checks dependencies; readiness does.
