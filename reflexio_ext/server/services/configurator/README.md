# Configurator & Config Storage

Manages organization configuration persistence and user-data storage creation using the **Ports & Adapters** pattern.

## Config Storage

Stores/loads organization configuration (API keys, LLM settings, storage settings) with encryption.

```
ConfigStorage (ABC — 3 methods: get_default_config, load_config, save_config)
├── LocalJsonConfigStorage   (open-source, local JSON files)
├── S3ConfigStorage          (enterprise, S3 + encryption)
├── SupabaseConfigStorage    (enterprise, Supabase PostgREST + encryption)
└── SqliteConfigStorage      (enterprise, SQLAlchemy + encryption)
```

### Selection priority (in `SimpleConfigurator.__init__`)

1. **LocalJsonConfigStorage** — if `base_dir` explicitly provided (testing)
2. **S3ConfigStorage** — if all `CONFIG_S3_*` env vars are set (self-host mode)
3. **SupabaseConfigStorage** — if `SessionLocal is None` (cloud Supabase mode)
4. **SqliteConfigStorage** — local SQLite fallback

## Storage Factory

Creates `BaseStorage` instances for user data (profiles, interactions, feedbacks, etc.).

```python
# Registry maps config type → factory function
_STORAGE_FACTORIES = {
    StorageConfigLocal: _create_local_json_storage,
    StorageConfigSupabase: _create_supabase_storage,
}
```

### Adding a new user-data storage backend

1. Create a `BaseStorage` subclass implementing all abstract methods
2. Add a `StorageConfig*` Pydantic model in `reflexio_commons/config_schema.py`
3. Write a factory function `_create_*_storage(configurator, config) -> BaseStorage`
4. Register it: `_STORAGE_FACTORIES[StorageConfigNew] = _create_new_storage`

## Files

| File | Purpose |
|------|---------|
| `configurator.py` | `SimpleConfigurator` — config storage selection + `_STORAGE_FACTORIES` registry |
| `supabase_config_storage.py` | Supabase config adapter (PostgREST + Fernet encryption) |
| `sqlite_config_storage.py` | SQLite config adapter (SQLAlchemy + Fernet encryption) |
| `s3_config_storage.py` | S3 config adapter (S3 + optional Fernet encryption) |

## Anti-patterns

- **NEVER** mix multiple backends in one adapter — each adapter handles exactly one storage backend
- **NEVER** add `isinstance()` checks in `create_storage()` — use the `_STORAGE_FACTORIES` registry instead
