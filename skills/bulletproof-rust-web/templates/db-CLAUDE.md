# Database Layer Rules

<!-- Copy to src/infra/db/CLAUDE.md (or src/infra/CLAUDE.md) -->

## Repositories

- One repository struct per domain aggregate (`UserRepository`, `PostRepository`).
- Repositories hold a `PgPool` and implement the domain's port traits where ports exist.
- Return domain types via `TryFrom<Row>`, never raw database rows.
- `fetch_optional()` for lookups. "Not found" is `Ok(None)`, not an error.
- Map database-specific errors (unique violations) to domain errors here, not upstream.

## Queries

- `sqlx::query_as!` for compile-time checked queries.
- Parameterized placeholders (`$1`, `$2`) exclusively. Never interpolate values into SQL.
- `RETURNING` on INSERT and UPDATE to avoid a second round-trip.
- `COALESCE` for partial updates; document that it cannot express "clear this field".
- Select the columns you need instead of `SELECT *`.

## Migrations

- `migrations/` with timestamp prefixes: `YYYYMMDDHHMMSS_description.sql`.
- `gen_random_uuid()` for UUID primary keys (built in, no extension needed).
- `TIMESTAMPTZ`, never `TIMESTAMP`.
- Index every column used in `WHERE` or `JOIN`.
- Database triggers keep `updated_at` correct regardless of the writer.
- Backward compatible, or expand/contract for destructive changes.
- Run `cargo sqlx prepare` after changing queries or migrations; commit `.sqlx/`.

## Transactions

- Wrap multi-step writes in an explicit transaction.
- An early return via `?` drops the transaction and rolls back automatically.
- `axum-sqlx-tx` provides request-scoped transactions when a whole handler should be atomic.

## Row types

- Row structs live in the infra layer and derive `sqlx::FromRow`.
- They are separate from domain entities and API response types.
- `impl TryFrom<Row> for Entity` with real error handling for corrupt or legacy data.
