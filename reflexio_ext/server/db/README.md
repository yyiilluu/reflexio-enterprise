# Organization Database Layer

Manages organization, API token, and invitation code persistence using the **Ports & Adapters** pattern.

## Architecture

```
db_operations.py  (backward-compatible wrapper functions)
  └── create_org_repository(session)  — factory
        ├── S3OrgRepository        (SELF_HOST=true + S3 config)
        ├── SupabaseOrgRepository  (LOGIN_SUPABASE_URL set)
        └── SQLiteOrgRepository    (local fallback)
```

### Port

**`org_repository.py`** — `OrgRepository` Protocol with 14 methods covering:
- Organization CRUD (`get_organization_by_email`, `create_organization`, etc.)
- API token management (`create_api_token`, `get_org_by_api_token`, etc.)
- Invitation codes (`claim_invitation_code`, `release_invitation_code`, etc.)

### Adapters

| Adapter | Backend | When used |
|---------|---------|-----------|
| `SQLiteOrgRepository` | SQLAlchemy + SQLite | Local dev (default fallback) |
| `SupabaseOrgRepository` | Supabase PostgREST | Cloud mode (`LOGIN_SUPABASE_URL` set) |
| `S3OrgRepository` | S3 JSON file | Self-host mode (`SELF_HOST=true`) |

### Adding a new backend

1. Create `reflexio_ext/server/db/new_org_repository.py` implementing all `OrgRepository` methods
2. Add detection logic to `create_org_repository()` in `db_operations.py`
3. Add protocol compliance test in `tests/server/db/test_org_repository.py`

## Files

| File | Purpose |
|------|---------|
| `org_repository.py` | `OrgRepository` Protocol definition (port) |
| `sqlite_org_repository.py` | SQLite/SQLAlchemy adapter |
| `supabase_org_repository.py` | Supabase PostgREST adapter |
| `s3_org_repository.py` | S3 self-host adapter (wraps `S3OrganizationStorage`) |
| `db_operations.py` | Factory + backward-compatible wrapper functions |
| `database.py` | SQLAlchemy engine/session configuration |
| `db_models.py` | SQLAlchemy ORM models (`Organization`, `ApiToken`, `InvitationCode`) |
| `login_supabase_client.py` | Supabase client singleton |
| `s3_org_storage.py` | S3 organization storage (used by `S3OrgRepository`) |

## Anti-patterns

- **NEVER** call adapter methods directly from API endpoints — use `db_operations.py` wrapper functions
- **NEVER** add `if backend == ...` branching inside an adapter — each adapter handles exactly one backend
