# Domain Modeling

Principle: **parse, don't validate**. Define types that can only be constructed from valid
data, so downstream code never re-checks anything.

## Newtypes

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Email(String);

impl Email {
    /// Illustrative validator. In production use a well-tested email validator; the
    /// `validator` crate's `#[validate(email)]` covers the DTO layer.
    pub fn parse(raw: &str) -> Result<Self, DomainError> {
        let trimmed = raw.trim().to_lowercase();
        if trimmed.contains('@') && trimmed.len() >= 3 {
            Ok(Self(trimmed))
        } else {
            Err(DomainError::InvalidEmail(raw.to_string()))
        }
    }

    pub fn as_str(&self) -> &str { &self.0 }
}

impl AsRef<str> for Email {
    fn as_ref(&self) -> &str { &self.0 }
}
```

Requirements for every newtype:

- Inner field **private**. No public constructor other than `parse` / `new`.
- No `&mut` access to the inner value, so the invariant cannot be broken later.
- `parse` returns `Result`; the error is a domain error, not a string in production code.
- Read access via `as_str` / `as_uuid` / `AsRef`.
- Zero runtime cost. The wrapper disappears after monomorphization.

Identifier newtypes usually skip validation but still buy type safety:

```rust
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct UserId(Uuid);

impl UserId {
    pub fn new() -> Self { Self(Uuid::new_v4()) }
    pub fn from_uuid(id: Uuid) -> Self { Self(id) }
    pub fn as_uuid(&self) -> &Uuid { &self.0 }
}
```

The payoff is in the signatures:

```rust
fn create_user(name: String, email: String) -> Result<User, Error>       // swappable, silent bug
fn create_user(name: UserName, email: Email) -> Result<User, CreateUserError>  // uncallable wrongly
```

## Entities

An entity has identity and a lifecycle. Fields are private; mutation goes through methods
that enforce the rules.

```rust
#[derive(Debug, Clone)]
pub struct User {
    id: UserId,
    name: UserName,
    email: Email,
    created_at: DateTime<Utc>,
    updated_at: DateTime<Utc>,
}

impl User {
    /// Used by the repository when hydrating from the database.
    pub fn hydrate(
        id: UserId, name: UserName, email: Email,
        created_at: DateTime<Utc>, updated_at: DateTime<Utc>,
    ) -> Self {
        Self { id, name, email, created_at, updated_at }
    }

    pub fn id(&self) -> &UserId { &self.id }
    pub fn name(&self) -> &UserName { &self.name }
    pub fn email(&self) -> &Email { &self.email }
    pub fn created_at(&self) -> DateTime<Utc> { self.created_at }
}
```

`User` deliberately has no `password_hash`. What you need to *create* a thing is not the
thing itself:

```rust
/// All fields already parsed and the password already hashed.
pub struct NewUser {
    pub name: UserName,
    pub email: Email,
    pub password_hash: String,
}
```

## Four types, four boundaries

| Type | Layer | Derives | Purpose |
|------|-------|---------|---------|
| `CreateUserDto` | api | `Deserialize`, `Validate` | wire format in |
| `User` / `NewUser` | domain | plain structs | business truth |
| `UserRow` | infra | `sqlx::FromRow` | database schema |
| `UserResponse` | api | `Serialize` (`ToSchema`) | wire format out |

Share a type across boundaries only when the shapes are structurally identical *and* have
identical invariants. Otherwise a new DB column silently becomes part of the public API.

## Conversions

```rust
// infra: row -> entity. TryFrom, because stored data may violate current invariants
// (legacy rows, manual SQL fixes, migrations, past bugs).
impl TryFrom<UserRow> for User {
    type Error = anyhow::Error;

    fn try_from(row: UserRow) -> Result<Self, Self::Error> {
        Ok(User::hydrate(
            UserId::from_uuid(row.id),
            UserName::parse(&row.name)
                .map_err(|e| anyhow::anyhow!("corrupt user name in row {}: {e}", row.id))?,
            Email::parse(&row.email)
                .map_err(|e| anyhow::anyhow!("corrupt email in row {}: {e}", row.id))?,
            row.created_at,
            row.updated_at,
        ))
    }
}

// api: entity -> response. From, because the domain value is always valid.
impl From<User> for UserResponse {
    fn from(user: User) -> Self {
        Self {
            id: *user.id().as_uuid(),
            name: user.name().as_str().to_string(),
            email: user.email().as_str().to_string(),
            created_at: user.created_at(),
        }
    }
}
```

The response type has no password hash field, so leaking it is not a code-review question,
it is a compile error.

## Domain errors

Domain errors describe business failures, never infrastructure ones. If a domain error enum
imports `sqlx` or `axum`, the layering broke.

```rust
#[derive(Debug, thiserror::Error)]
pub enum DomainError {
    #[error("invalid email address: {0}")]
    InvalidEmail(String),
    #[error("name cannot be empty")]
    EmptyName,
    #[error("name exceeds maximum length")]
    NameTooLong,
}

#[derive(Debug, thiserror::Error)]
pub enum CreateUserError {
    #[error("a user with email {email} already exists")]
    Duplicate { email: Email },
    #[error(transparent)]
    Unknown(#[from] anyhow::Error),
}
```

One error enum per operation (`CreateUserError`, `AuthError`) plus an `Unknown(anyhow::Error)`
catch-all so infra can pass through unexpected failures without the domain enumerating them.

## Two levels of validation

- **API layer** checks shape: required fields, lengths, email format, ranges. Use
  `validator` derives on DTOs plus a `ValidatedJson` extractor. Returns 400 with per-field
  messages.
- **Domain layer** enforces invariants at construction: normalization (lowercase email),
  forbidden characters, business ranges. Applies no matter whether data arrives from HTTP,
  a queue, a CSV import, or a test.

Both are needed. The first gives good error messages; the second gives guarantees.

## Typestate: invalid transitions as compile errors

Newtypes make invalid *values* unrepresentable. Typestate makes invalid *transitions*
unrepresentable: the state is a type parameter, and each method exists only in the state
where it is legal.

```rust
use std::marker::PhantomData;

pub struct Created;
pub struct Paid;
pub struct Shipped;

pub struct Order<State> {
    id: Uuid,
    total_cents: i64,
    _state: PhantomData<State>,
}

impl Order<Created> {
    pub fn pay(self, payment_id: String) -> Order<Paid> {
        Order { id: self.id, total_cents: self.total_cents, _state: PhantomData }
    }
}

impl Order<Paid> {
    pub fn ship(self, tracking: String) -> Order<Shipped> { /* ... */ }
    pub fn refund(self) -> Order<Created> { /* ... */ }
}
```

`Order::<Created>::ship()` does not exist, so shipping an unpaid order is a compile error.
The same pattern covers connection lifecycles (`Connection<Unauthenticated>` has no
`send_notification`) and builders with mandatory fields (`build()` only on
`ServerBuilder<HasAddr>`).

Use typestate when invalid transitions would corrupt data or breach security, the states
are few and mostly linear, and the types stay inside one module. Prefer an enum state
machine when entities in different states go in the same collection, when the state must be
serialized to a database or API, or when the transition graph is large. Many systems use
both: typestate for internal transition logic, an enum for persistence.
