# Claude Guidelines

## Contexts

Refer to `README.md` for user-side instructions and usage.
Refer to `SPEC.md` for technical implementation details.

## Project Structure

This project targets to write a single-file script `alembic-rebase.py` that could be vendored inside another repository as a helper script.

## Development Environment

This project uses `uv` as the primary build toolchain and the dependency manager.

```bash
# Auto-formatting
uv run ruff format {source-files}

# Linting
uv run ruff check {source-files}

# Typechecking
uv run mypy {source-files}

# Testing
uv run pytest {test-files}
```

This project also uses `pre-commit` as a pre-commit hook.

There are corresponding tool configurations as `ruff.toml`, `mypy.ini`, and `.pre-commint-config.yaml`.

To make the results of `uv run mypy` and `pre-commit run` consistent by having the same dependencies,
the pre-commit config for `mirrors-mypy` is set to use the "system" language with an explicit entry command prefix.

Whenever making major changes, run auto-formatting, linting, typechecking using uv.
Then, fix any issue reported by them.

## Code Patterns

This project uses `asyncpg` with `sqlalchemy` and `asyncio`.

Since `alembic` provides only synchronous APIs, executing alembic APIs inside async contexts require a special construct like:
```python
from alembic import command
from alembic.config import Config

alembic_config = Config(alembic_ini_path)
db_url = alembic_config.get_main_option("sqlalchemy.url")

def invoke_alembic_command():
    # Call the alembic command APIs
    command.downgrade(...)
    command.upgrade(...)

async_engine = create_async_engine(db_url)
async with async_engine.begin() as conn:
    alembic_config.attributes["connection"] = conn
    await conn.run_sync(invoke_alembic_command)
```

When you make code changes, ensure the function/method arguments and return values are explicitly type-annotated.
