# Error Handling

Two audiences: the client needs a status code and an actionable message; the team needs the
full chain and context. Serve both without leaking internals.

Axum handlers must produce a response, so fallible handlers return `Result<T, E>` where
`E: IntoResponse`.

## AppError

```rust
use std::collections::HashMap;
use axum::{http::StatusCode, response::{IntoResponse, Response}, Json};

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("resource not found")]
    NotFound,

    #[error("{0}")]
    Validation(String),

    #[error("validation failed")]
    ValidationFields(HashMap<String, Vec<String>>),

    #[error("authentication required")]
    Unauthorized,

    #[error("insufficient permissions")]
    Forbidden,

    #[error("{0}")]
    Conflict(String),

    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

pub type AppResult<T> = Result<T, AppError>;

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_type, message) = match &self {
            AppError::NotFound => (StatusCode::NOT_FOUND, "not_found", self.to_string()),
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, "validation_error", msg.clone()),
            AppError::ValidationFields(fields) => {
                let body = serde_json::json!({
                    "error": {
                        "type": "validation_error",
                        "message": "request validation failed",
                        "fields": fields,
                    }
                });
                return (StatusCode::BAD_REQUEST, Json(body)).into_response();
            }
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, "unauthorized", self.to_string()),
            AppError::Forbidden => (StatusCode::FORBIDDEN, "forbidden", self.to_string()),
            AppError::Conflict(msg) => (StatusCode::CONFLICT, "conflict", msg.clone()),
            AppError::Internal(err) => {
                // The only place the real error is visible. Never sent to the client.
                tracing::error!(error = ?err, "internal server error");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal_error",
                 "an internal error occurred".to_string())
            }
        };

        let body = serde_json::json!({ "error": { "type": error_type, "message": message } });
        (status, Json(body)).into_response()
    }
}
```

## The error chain

```
sqlx::Error  →  CreateUserError (domain)  →  AppError (api)  →  HTTP response
```

Infra translates infrastructure failures into business terms:

```rust
.map_err(|e| match e {
    sqlx::Error::Database(ref db) if db.is_unique_violation() =>
        CreateUserError::Duplicate { email: req.email.clone() },
    other => CreateUserError::Unknown(other.into()),
})
```

The api layer maps business failures onto HTTP:

```rust
impl From<CreateUserError> for AppError {
    fn from(err: CreateUserError) -> Self {
        match err {
            CreateUserError::Duplicate { email } => AppError::Conflict(
                format!("a user with email {} already exists", email.as_str())),
            CreateUserError::Unknown(inner) => AppError::Internal(inner),
        }
    }
}
```

With those impls the handler is just the happy path:

```rust
async fn create_user(
    State(state): State<AppState>,
    ValidatedJson(payload): ValidatedJson<CreateUserDto>,
) -> AppResult<(StatusCode, Json<UserResponse>)> {
    let user = state.user_service.register(payload).await?;   // ? walks the whole chain
    Ok((StatusCode::CREATED, Json(user.into())))
}
```

## thiserror vs anyhow

| | `thiserror` | `anyhow` |
|---|---|---|
| Use for | errors callers **match on**: domain errors, `AppError` | errors that are only **propagated and logged** |
| Where | domain error enums, api error enum | `AppError::Internal`, infra plumbing |
| Gives | typed variants, `#[from]`, `Display` | one type for anything, `.context()` chains |

Never return `anyhow::Error` from a handler directly: you lose the ability to map different
failures to different status codes.

## Context

```rust
use anyhow::Context;

pub async fn create_pool(database_url: &str) -> anyhow::Result<PgPool> {
    PgPoolOptions::new()
        .max_connections(10)
        .acquire_timeout(Duration::from_secs(3))
        .connect(database_url)
        .await
        .context("failed to connect to the database")
}
```

Add `.context()` liberally in infra. The logged chain then reads "failed to persist user
registration: connection reset by peer" instead of only the latter.

## Rules

- No `unwrap()` / `expect()` in request paths. Use `?`, and `.ok_or(AppError::NotFound)?`
  to turn `Option` into an error. `expect()` is acceptable in startup code where a missing
  value means the process cannot run, and for provably-present values such as a compiled
  regex.
- Never send internal error text to a client. Log it at `error`, return a generic message.
- Use `#[from]` so `?` performs conversions for you.
- Give each failing operation its own error enum rather than one god enum with 40 variants.
- gRPC surfaces reuse the same chain: `impl From<AppError> for tonic::Status` maps
  `NotFound → not_found`, `Validation → invalid_argument`, `Unauthorized → unauthenticated`,
  `Forbidden → permission_denied`, `Conflict → already_exists`, `Internal → internal`.
