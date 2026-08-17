# Authentication, Authorization, Security

## Choosing a strategy

| Client | Strategy |
|--------|----------|
| First-party browser app | Server-side sessions in `HttpOnly; Secure; SameSite=Strict` cookies (`tower-sessions`, `axum-login`). Revocable immediately. Requires CSRF protection. |
| Service-to-service, machine clients | Stateless JWT in `Authorization: Bearer`. No session store, but no revocation before expiry either. |
| Public API with third-party consumers | OAuth2 / OIDC, tokens issued by an identity provider (`jwt-authorizer` handles discovery and key rotation). |

`HttpOnly` does not prevent XSS; it prevents the token itself from being read by injected
script, which is why OWASP still recommends it.

## JWT via a custom extractor

```rust
#[derive(Debug, Clone)]
pub struct AuthUser { pub user_id: Uuid, pub email: String, pub role: Role }

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Claims {
    pub sub: Uuid, pub email: String, pub role: Role,
    pub iss: String, pub aud: String, pub exp: usize, pub iat: usize,
}

impl<S> FromRequestParts<S> for AuthUser
where AppState: FromRef<S>, S: Send + Sync,
{
    type Rejection = AppError;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let app_state = AppState::from_ref(state);

        let TypedHeader(Authorization(bearer)) = parts
            .extract::<TypedHeader<Authorization<Bearer>>>()
            .await
            .map_err(|_| AppError::Unauthorized)?;

        // Be explicit about what you accept. Never trust the token's own `alg` header.
        let mut validation = Validation::new(Algorithm::HS256);
        validation.set_issuer(&["myapp"]);
        validation.set_audience(&["myapp-api"]);
        validation.leeway = 30;

        let token_data = decode::<Claims>(
            bearer.token(),
            &DecodingKey::from_secret(app_state.config.jwt_secret.expose_secret().as_bytes()),
            &validation,
        ).map_err(|_| AppError::Unauthorized)?;

        Ok(AuthUser {
            user_id: token_data.claims.sub,
            email: token_data.claims.email,
            role: token_data.claims.role,
        })
    }
}
```

Adding `user: AuthUser` to a handler signature is now the entire auth requirement; an
invalid token means the body never runs.

### Optional auth

Do not use `Option<AuthUser>`: it collapses "no header" (anonymous) and "bad token"
(should be 401) into the same value. Use a dedicated extractor:

```rust
pub struct MaybeAuthUser(pub Option<AuthUser>);

// no Authorization header  -> Ok(None)
// header present but invalid -> Err(AppError::Unauthorized)
```

### Issuing tokens

```rust
let now = chrono::Utc::now();
let claims = Claims {
    sub: *user.id().as_uuid(),
    email: user.email().as_str().to_string(),
    role: user.role().clone(),
    iss: "myapp".into(),
    aud: "myapp-api".into(),
    iat: now.timestamp() as usize,
    exp: (now + chrono::TimeDelta::try_minutes(15).expect("valid duration")).timestamp() as usize,
};

let token = encode(&Header::default(), &claims,
    &EncodingKey::from_secret(state.config.jwt_secret.expose_secret().as_bytes()))
    .map_err(|e| AppError::Internal(e.into()))?;
```

Production considerations:

- Short access tokens (15 minutes to a few hours). Longer sessions need a refresh token in
  a secure, revocable cookie.
- Pin the algorithm explicitly. Accepting the token's declared `alg` is a known attack.
- Set and validate `iss` and `aud` so a token minted for one service is rejected by another.
- Roles embedded in a token do not change until it expires. If immediate revocation matters,
  use short lifetimes, a token version checked against the database, or a deny-list.

## Password hashing

```rust
pub fn hash_password(password: &str) -> anyhow::Result<String> {
    let salt = SaltString::generate(&mut OsRng);
    let hash = Argon2::default()               // Argon2id, OWASP-recommended variant
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| anyhow::anyhow!("failed to hash password: {e}"))?
        .to_string();
    Ok(hash)
}

pub fn verify_password(password: &str, hash: &str) -> anyhow::Result<bool> {
    let parsed = PasswordHash::new(hash).map_err(|e| anyhow::anyhow!("bad hash: {e}"))?;
    Ok(Argon2::default().verify_password(password.as_bytes(), &parsed).is_ok())
}
```

Argon2 for new projects (not SHA-256, MD5, or bcrypt). Tune memory cost and iterations to
current OWASP minimums and your hardware. Hashing is deliberately slow, so always run it off
the async runtime:

```rust
let hash = tokio::task::spawn_blocking(move || hash_password(&password))
    .await.context("password hashing task failed")??;
```

## Authorization

Inline check for a one-off:

```rust
if user.role != Role::Admin { return Err(AppError::Forbidden); }
```

Repeated checks become an extractor:

```rust
pub struct RequireAdmin(pub AuthUser);

impl<S> FromRequestParts<S> for RequireAdmin
where AppState: FromRef<S>, S: Send + Sync,
{
    type Rejection = AppError;
    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let user = AuthUser::from_request_parts(parts, state).await?;
        if user.role != Role::Admin { return Err(AppError::Forbidden); }
        Ok(Self(user))
    }
}
```

Extractors are per-handler and give direct access to the user; middleware
(`route_layer(from_fn_with_state(state, auth_middleware))`) is better for whole route
groups. Combining both is normal: middleware for the baseline, extractors for finer checks.

## CORS

```rust
fn cors_layer(config: &Config) -> CorsLayer {
    if config.environment == Environment::Development {
        CorsLayer::permissive()
    } else {
        CorsLayer::new()
            .allow_origin(config.cors_origins.iter()
                .map(|o| o.parse().expect("invalid CORS origin in config"))
                .collect::<Vec<HeaderValue>>())
            .allow_methods([Method::GET, Method::POST, Method::PUT, Method::DELETE])
            .allow_headers([header::CONTENT_TYPE, header::AUTHORIZATION])
            .allow_credentials(true)
    }
}
```

Drive the policy from runtime configuration, never `cfg!(debug_assertions)`: a release
build in staging still wants relaxed CORS, a debug build against production data does not.
`CorsLayer::very_permissive()` also enables credentials; never let it reach production.

## CSRF

Needed when authentication rides on cookies. `axum-csrf-sync-pattern` implements the OWASP
Synchronizer Token Pattern: server issues a random token in a response header, client echoes
it in a request header on state-changing calls, server compares. It works because a
cross-origin page can make the browser send cookies but cannot set custom headers.

Bearer-token APIs do not need CSRF protection.

## Rate limiting

```rust
let governor_config = GovernorConfigBuilder::default()
    .per_second(2)
    .burst_size(10)
    .finish()
    .unwrap();

let app = Router::new().merge(api_routes()).layer(GovernorLayer { config: governor_config });
```

Stricter limits on authentication endpoints (roughly 5 attempts per minute per IP) make
credential stuffing impractical. With multiple instances, per-process counters are not
enough: use a Redis-backed limiter or enforce at the load balancer or API gateway.

## Security headers

```rust
async fn security_headers(req: Request, next: Next) -> Response {
    let mut response = next.run(req).await;
    let headers = response.headers_mut();

    headers.insert(HeaderName::from_static("x-content-type-options"),
                   HeaderValue::from_static("nosniff"));
    headers.insert(HeaderName::from_static("x-frame-options"),
                   HeaderValue::from_static("DENY"));
    headers.insert(HeaderName::from_static("content-security-policy"),
                   HeaderValue::from_static("default-src 'none'; frame-ancestors 'none'"));
    headers.insert(HeaderName::from_static("strict-transport-security"),
                   HeaderValue::from_static("max-age=63072000; includeSubDomains"));
    headers.insert(HeaderName::from_static("referrer-policy"),
                   HeaderValue::from_static("strict-origin-when-cross-origin"));

    response
}
```

CSP is the real XSS defense; `X-Frame-Options` covers older browsers alongside CSP's
`frame-ancestors`. Do **not** set `X-XSS-Protection`: it is deprecated by OWASP and MDN and
can introduce vulnerabilities.

## Dependency auditing

```sh
cargo install cargo-audit
cargo audit          # checks Cargo.lock against the RustSec advisory database
```

Run it in CI. Keeping dependencies current is among the highest-value security habits.

## Pre-deployment checklist

- [ ] All SQL parameterized, no string interpolation
- [ ] `RequestBodyLimitLayer` and `TimeoutLayer` configured
- [ ] Input validated at the API boundary; domain types enforce invariants
- [ ] Passwords hashed with Argon2 via `spawn_blocking`
- [ ] JWT secret at least 48 random characters, in `SecretString`, never logged
- [ ] Token expiry set; algorithm, issuer, audience validated explicitly
- [ ] CORS restricted to configured origins in production, driven by runtime config
- [ ] CSRF protection enabled if authentication uses cookies
- [ ] Rate limiting on public endpoints, stricter on auth endpoints
- [ ] CSP, HSTS, X-Content-Type-Options, Referrer-Policy set; X-XSS-Protection absent
- [ ] Internal error details never returned to clients
- [ ] Response DTOs exclude password hashes and internal fields
- [ ] `.env` git-ignored, `.env.example` committed
- [ ] `cargo audit` and `cargo sqlx prepare --check` run in CI
