# Integration Tests

This directory contains integration tests that require real API credentials and external services.

## Why Integration Tests Are Separate

- **Real Dependencies**: These tests need actual Discord tokens, Supabase API keys, Google Calendar credentials, etc.
- **Network Dependent**: They make real HTTP requests to external services
- **Environment Specific**: They require specific configuration files (like `tenants.json`) with real data
- **CI Exclusion**: They're excluded from CI/CD pipelines to avoid dependency on external services

## Running Integration Tests

Integration tests should only be run in development environments where you have:

1. **Valid API Credentials**: All required environment variables set with real API keys
2. **Network Access**: Stable internet connection to reach external APIs
3. **Real Configuration**: Actual `tenants.json` with valid guild/channel IDs

### Example Usage

```bash
# From project root
python tests/integration/integration_test_sync_token_error.py
```

## Adding New Integration Tests

When adding new integration tests:

1. Place them in this directory (`tests/integration/`)
2. Use descriptive filenames starting with `integration_test_`
3. Include proper path setup for imports (see existing examples)
4. Document any specific requirements or setup steps
5. Make sure they're excluded from CI (via `pytest.ini` configuration)

## Current Integration Tests

- `integration_test_sync_token_error.py`: Tests HTTP 410 error handling in calendar sync
- `test_query_parser.py`: Tests OpenAI-based natural language query parsing (requires OPENAI_API_KEY)
