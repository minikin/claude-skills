# Testing

Most effort goes into the bottom two tiers: many fast unit tests over domain logic, a solid
set of integration tests through the real router, a few end-to-end smoke tests.

## Unit tests with an in-memory repository

Because the domain has no framework dependencies, testing it needs no server and no
database. Implement the port with a fake:

```rust
#[derive(Clone)]
struct InMemoryUserRepo { users: Arc<Mutex<Vec<User>>> }

impl UserRepository for InMemoryUserRepo {
    async fn create(&self, req: &NewUser) -> Result<User, CreateUserError> {
        let mut users = self.users.lock().await;
        if users.iter().any(|u| u.email() == &req.email) {
            return Err(CreateUserError::Duplicate { email: req.email.clone() });
        }
        let user = User::hydrate(UserId::new(), req.name.clone(), req.email.clone(),
                                 Utc::now(), Utc::now());
        users.push(user.clone());
        Ok(user)
    }

    async fn find_by_id(&self, id: &UserId) -> anyhow::Result<Option<User>> {
        Ok(self.users.lock().await.iter().find(|u| u.id() == id).cloned())
    }
}

#[tokio::test]
async fn registering_duplicate_email_fails() {
    let service = UserService::new(InMemoryUserRepo::new());
    let name = UserName::parse("Alice").unwrap();
    let email = Email::parse("alice@example.com").unwrap();

    service.register(name.clone(), email.clone(), "password123").await.unwrap();
    let result = service.register(name, email, "password456").await;

    assert!(matches!(result, Err(CreateUserError::Duplicate { .. })));
}
```

`unwrap()` in tests is fine; the rule against it applies to request-handling code.

Hand-written fakes are usually clearer than generated mocks for core domain tests. `mockall`
is a fair choice once the trait surface is large.

## Integration tests with oneshot

`tower::ServiceExt::oneshot` pushes a request through the real router (middleware,
extractors, serialization, error mapping) without binding a socket.

```rust
use axum::body::Body;
use http::Request;
use http_body_util::BodyExt;
use tower::ServiceExt;

async fn test_app() -> Router {
    let pool = create_test_pool().await;
    create_app_with_pool(pool).await     // the same wiring production uses
}

#[tokio::test]
async fn creating_a_user_returns_201() {
    let app = test_app().await;

    let response = app.oneshot(
        Request::builder()
            .method("POST")
            .uri("/api/v1/users")
            .header("Content-Type", "application/json")
            .body(Body::from(r#"{"name":"Alice","email":"alice@example.com","password":"securepassword"}"#))
            .unwrap(),
    ).await.unwrap();

    assert_eq!(response.status(), StatusCode::CREATED);

    let body = response.into_body().collect().await.unwrap().to_bytes();
    let user: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(user["data"]["email"], "alice@example.com");
}

#[tokio::test]
async fn creating_a_user_with_invalid_email_returns_400() { /* ... */ }
```

Build the test router from the same `create_app` function as production so the middleware
stack and error handling under test are the real ones.

What `oneshot` does not cover: TLS termination, reverse proxies, load balancer probes,
socket-level behaviour. Keep a smoke test against a running instance in staging.

`axum-test` offers a friendlier `TestClient` API over the same mechanism.

## Test databases

```rust
#[sqlx::test(migrations = "./migrations")]
async fn test_user_creation(pool: PgPool) {
    let repo = PostgresUserRepo::new(pool);
    let user = repo.create(&new_user()).await.unwrap();
    assert_eq!(user.email().as_str(), "alice@example.com");
}
```

`#[sqlx::test]` creates a uniquely named database per test, runs migrations, and drops it
afterwards. Perfect isolation with no bookkeeping. Alternatives: one shared database with
truncation or per-test transactions (faster, more fragile), or in-memory SQLite when the SQL
is portable.

## Helpers

```rust
// tests/common/mod.rs
pub async fn test_app() -> Router { /* pool + migrations + create_app */ }

pub fn test_database_url() -> String {
    std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://localhost/myapp_test".to_string())
}

pub async fn create_test_user(app: &Router) -> (Uuid, String) { /* returns (id, token) */ }

pub async fn response_json(response: Response) -> serde_json::Value {
    let body = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&body).unwrap()
}
```

## What to cover

- Happy path per endpoint: status code and body shape.
- Validation failures, so weakened rules are caught.
- Authorization: unauthenticated rejected, users cannot reach other users' data, role
  restrictions enforced.
- Error mapping: a duplicate email returns 409, not 500.
- Domain edge cases at the unit level: empty strings, max lengths, boundary values.
- Shutdown paths, if the service runs background subsystems:

```rust
#[tokio::test]
async fn shutdown_completes_within_timeout() {
    let token = CancellationToken::new();
    let handle = tokio::spawn(run_my_subsystem(token.clone()));
    tokio::time::sleep(Duration::from_millis(100)).await;
    token.cancel();

    assert!(tokio::time::timeout(Duration::from_secs(5), handle).await.is_ok(),
            "shutdown did not complete within timeout");
}
```

Do not chase a coverage number. A suite that covers the important behaviours and edge cases
beats one that tests getters to hit 90 percent.
