# Database Layer

Default: SQLx with Postgres. Diesel (`diesel-async`) and SeaORM are reasonable
alternatives; the layering rules are identical.

## Connection pool

```rust
use anyhow::Context;
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::time::Duration;

pub async fn create_pool(database_url: &str) -> anyhow::Result<PgPool> {
    PgPoolOptions::new()
        .max_connections(10)
        .min_connections(2)
        .acquire_timeout(Duration::from_secs(3))
        .idle_timeout(Duration::from_secs(600))
        .connect(database_url)
        .await
        .context("failed to connect to the database")
}
```

Sizing: start at 2 to 4 connections per CPU core on the app instance (8 to 16 on a 4-core
box) and tune from measured DB wait time. Total connections across all instances must stay
under the server limit (Postgres defaults to 100). `acquire_timeout` prevents requests from
hanging forever when the pool is exhausted.

## Migrations

```
migrations/
├── 20240101000000_create_users.sql
└── 20240102000000_add_user_bio.sql
```

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    name          VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    bio           TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

Conventions:

- `UUID PRIMARY KEY DEFAULT gen_random_uuid()` (built in, no extension). Consider UUIDv7
  for write-heavy tables (index-friendly ordering; native `uuidv7()` in Postgres 18+, the
  `uuid` crate's `v7` feature otherwise), or bigserial when an external spec demands integers.
- `TIMESTAMPTZ`, never `TIMESTAMP`.
- Index every column used in `WHERE` or `JOIN`. GIN for array containment and full-text.
- Keep `updated_at` correct with a trigger, so manual SQL fixes cannot skip it.
- Enforce case-insensitive uniqueness in the database (`citext` or an ICU `COLLATE`), not
  by lowercasing in application code that other writers can bypass.

Run at startup:

```rust
sqlx::migrate!("./migrations").run(&pool).await.context("failed to run migrations")?;
```

`migrate!` embeds the SQL in the binary. With multiple instances, SQLx takes an advisory
lock so only one applies them; for rolling deploys a dedicated migration job or init
container gives clearer failure handling.

## Offline compile-time checking

`query!` / `query_as!` validate SQL against a live database at compile time. For CI:

```sh
cargo sqlx prepare          # generates .sqlx/, commit it
SQLX_OFFLINE=true cargo build
cargo sqlx prepare --check  # CI gate: metadata in sync with queries and migrations
```

## Repository pattern

One repository per aggregate. It owns the pool, speaks SQL inward and domain types outward.

```rust
#[derive(Clone)]
pub struct UserRepository { pool: PgPool }

impl UserRepository {
    pub fn new(pool: PgPool) -> Self { Self { pool } }

    pub async fn create(&self, req: &NewUser) -> Result<User, CreateUserError> {
        let row = sqlx::query_as!(
            UserRow,
            r#"
            INSERT INTO users (id, email, name, password_hash)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, name, password_hash, bio, created_at, updated_at
            "#,
            Uuid::new_v4(),
            req.email.as_str(),
            req.name.as_str(),
            &req.password_hash,
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| match e {
            sqlx::Error::Database(ref db) if db.is_unique_violation() =>
                CreateUserError::Duplicate { email: req.email.clone() },
            other => CreateUserError::Unknown(other.into()),
        })?;

        row.try_into().map_err(CreateUserError::Unknown)
    }

    pub async fn find_by_id(&self, id: &UserId) -> anyhow::Result<Option<User>> {
        let row = sqlx::query_as!(
            UserRow,
            "SELECT id, email, name, password_hash, bio, created_at, updated_at
             FROM users WHERE id = $1",
            id.as_uuid(),
        )
        .fetch_optional(&self.pool)
        .await
        .context("failed to fetch user by id")?;

        row.map(TryInto::try_into).transpose()
    }
}
```

Patterns to keep:

- `query_as!` checks columns and types at compile time and builds the mapping itself (it
  does not use `FromRow`; the non-macro `query_as::<_, UserRow>()` does).
- Separate `UserRow` from `User`, bridged by `TryFrom` (see `domain-modeling.md`).
- `fetch_optional` for lookups. "Not found" is `Ok(None)`, not an error; the caller decides
  whether that is a problem.
- `RETURNING` on INSERT/UPDATE for a single round-trip.
- Every user value is a bind parameter (`$1`, `$2`). No format strings in SQL.
- `COALESCE($2, column)` gives partial updates without a read first. Limitation: it cannot
  distinguish "field omitted" from "explicitly set to null". If clearing must be supported,
  use a sentinel, a separate clear list, or explicit SQL.

## FromRef for ergonomic access

```rust
#[derive(Clone, FromRef)]
pub struct AppState {
    pub config: Arc<Config>,
    pub db: PgPool,
    pub user_repo: UserRepository,
}

async fn get_user(
    State(repo): State<UserRepository>,
    Path(id): Path<Uuid>,
) -> AppResult<Json<UserResponse>> {
    let user = repo.find_by_id(&UserId::from_uuid(id)).await?.ok_or(AppError::NotFound)?;
    Ok(Json(user.into()))
}
```

Handlers then declare exactly the dependency they use.

## Transactions

```rust
pub async fn transfer_credits(&self, from: &UserId, to: &UserId, amount: i64)
    -> anyhow::Result<()>
{
    let mut tx = self.pool.begin().await.context("failed to begin transaction")?;

    sqlx::query!("UPDATE accounts SET credits = credits - $1 WHERE user_id = $2",
                 amount, from.as_uuid())
        .execute(&mut *tx).await.context("failed to debit source account")?;

    sqlx::query!("UPDATE accounts SET credits = credits + $1 WHERE user_id = $2",
                 amount, to.as_uuid())
        .execute(&mut *tx).await.context("failed to credit target account")?;

    tx.commit().await.context("failed to commit transfer")?;
    Ok(())
}
```

An early `?` drops `tx` and rolls back automatically. For request-scoped transactions that
commit or roll back based on the response, see `axum-sqlx-tx`.

## Trait-based repositories

Introduce a port trait in the domain when you want to unit test services without a
database, or when a second implementation (cache wrapper, in-memory fake) is realistic. See
`architecture.md`. Otherwise a concrete repository struct is enough.
