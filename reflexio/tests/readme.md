# /user_profiler/reflexio/tests
Description: Test suites for Reflexio - unit, integration, and e2e tests

## Main Entry Points

| Directory | Purpose |
|-----------|---------|
| `e2e_tests/` | End-to-end workflow tests |
| `server/` | Unit tests for server components |
| `evaluation/` | Evaluation metrics and quality tests |
| `test_scripts/` | Manual test scripts |

## Setup

```shell
# Set OpenAI API key in reflexio/tests/__init__.py (don't commit)
OPENAI_API_KEY = "sk-proj-..."
```

## Running Tests

```shell
# Single test file
pytest <test_file_name>

# Single test
pytest <test_file_name>::test_name -v

# All e2e tests
pytest reflexio/tests/e2e_tests/ -v

# All unit tests
pytest reflexio/tests
```

## E2E Tests (`e2e_tests/`)

| File | Purpose |
|------|---------|
| `test_complete_workflows.py` | Full interaction → profile → feedback workflows |
| `test_profile_workflows.py` | Profile generation, status, upgrades/downgrades |
| `test_interaction_workflows.py` | Interaction publishing and retrieval |
| `test_feedback_workflows.py` | Feedback extraction and aggregation |
| `test_agent_success_workflows.py` | Agent success evaluation |
| `test_configuration.py` | Configuration and setup validation |
| `conftest.py` | Shared fixtures and utilities |

### E2E Test Behavior

- **Real LLM requirement** — e2e tests call the real LLM (MiniMax) for profile and feedback extraction. There are no mocks; every test run makes actual API calls.
- **Non-deterministic output** — LLM responses vary between runs. Tests assert structural correctness (non-null values, correct types, expected fields present) rather than exact values. Occasional failures from LLM variance are expected and by design — retry before investigating.
- **Long runtime** — the full e2e suite takes several minutes due to real API calls. Use `pytest -k <test_name>` to run specific tests during development rather than the entire suite.

## Integration Tests

```shell
# Set test-specific Supabase env vars (these are separate from app config)
export TEST_SUPABASE_URL=http://127.0.0.1:54321
export TEST_SUPABASE_KEY=...
export TEST_SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
export OPENAI_API_KEY=...

pytest tests/server/services/storage/test_supabase_storage_integration.py
pytest tests/server/services/feedback/test_feedback_generation_service_integration.py
```

## Verification Checklist

1. Run unit tests: `pytest reflexio/tests`
2. Run integration tests (with Supabase running)
3. Run e2e tests: `pytest reflexio/tests/e2e_tests/ -v`
4. Validate with notebook: `notebooks/reflexio_lib_cookbook.ipynb`
