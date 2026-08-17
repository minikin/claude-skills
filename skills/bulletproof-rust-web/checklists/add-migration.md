# Add a Migration

## 1. Create the file

```sh
cargo sqlx migrate add <description>
```

Produces a timestamped `.sql` file in `migrations/` (`YYYYMMDDHHMMSS_description.sql`).

## 2. Write the SQL

- `UUID PRIMARY KEY DEFAULT gen_random_uuid()` for ids (UUIDv7 for write-heavy tables).
- `TIMESTAMPTZ NOT NULL DEFAULT NOW()` for timestamps, never `TIMESTAMP`.
- Index every column used in `WHERE` or `JOIN`. GIN for array containment and text search.
- Reuse the `update_updated_at_column()` trigger function on any table with `updated_at`.
- Case-insensitive uniqueness for user-facing text (`citext` or an ICU collation), enforced
  in the database rather than by application lowercasing.
- Foreign keys with an explicit `ON DELETE` behaviour.

## 3. Check backward compatibility

Before applying, answer:

- Will the currently deployed application still work against the new schema?
- Does a new `NOT NULL` column have a `DEFAULT`?
- Is a renamed or dropped column still referenced by the running version?

Destructive changes use expand/contract:

1. Add the new structure (nullable or defaulted), deploy.
2. Backfill and write to both, deploy.
3. Switch reads to the new structure, deploy.
4. Remove the old structure in a later migration.

Long-running index builds on large tables should use `CREATE INDEX CONCURRENTLY` in its own
migration (it cannot run inside a transaction).

## 4. Apply and prepare

```sh
cargo sqlx migrate run
cargo sqlx prepare
```

## 5. Update queries

Update any `query!` / `query_as!` referencing changed columns or tables, and the
corresponding row structs and `TryFrom` impls.

## 6. Verify

```sh
cargo sqlx prepare --check
cargo test --workspace
```

## 7. Commit

Commit the migration file **and** the updated `.sqlx/` metadata directory together.
