# HTTP Layer Rules

<!-- Copy to src/api/CLAUDE.md -->

## Handlers

- 5 to 20 lines: extract, call a service, respond.
- Parse raw input into domain types inside the handler (`UserName::parse(&payload.name)`).
- Return `AppResult<T>` (alias for `Result<T, AppError>`).
- `StatusCode::CREATED` for POST, `StatusCode::NO_CONTENT` for DELETE.
- `#[tracing::instrument(skip(state, payload))]` on every handler.
- `#[debug_handler]` while developing gives readable trait-bound errors.

## Extractors

- `ValidatedJson<T>` instead of bare `Json<T>` for bodies that need validation.
- `ValidatedQuery<T>` for query parameters that need validation.
- `AuthUser` for authenticated endpoints; `MaybeAuthUser` when authentication is optional
  (it distinguishes "no header" from "invalid header").
- Body-consuming extractors (`Json`, `ValidatedJson`, `Form`) come last in the signature.

## Middleware

- `route_layer()` for authentication, so unmatched paths still return 404.
- `.layer()` for global concerns (tracing, compression, timeouts).
- Order: set request id → TraceLayer → propagate request id → timeout → body limit → CORS,
  with compression outermost.
- CORS policy comes from runtime configuration, never `cfg!(debug_assertions)`.

## DTOs

- Request DTOs derive `Deserialize` and `Validate`.
- Response DTOs derive `Serialize` (and `ToSchema` with utoipa).
- Response DTOs must not contain password hashes, internal ids, or other sensitive fields.
- Convert with `From<DomainEntity>`.

## Routes

- PATCH for partial updates, PUT only for full replacement.
- Nest and version: `/api/v1/users`, `/api/v1/posts`.
- Health endpoints sit outside the versioned API: `/health`, `/health/ready`.
- Every list endpoint paginates, with `per_page` clamped to a maximum.
