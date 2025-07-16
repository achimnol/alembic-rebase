# Alembic Rebase Tool

A standalone Python script to rebase alembic migrations when heads are diverged while working on a git repository.

## Features

- **Async operations** using asyncio and asyncpg
- **Compatible** with SQLAlchemy 1.4 and Alembic
- **Migration file rewriting** - automatically updates revision IDs and file links
- **Supports custom alembic.ini locations** for monorepo setups
- **Migration integrity validation** - ensures files are valid after rebase
- **Comprehensive error handling** and validation
- **Full test suite** with real migration files and proper cleanup

## Installation

This script requires Python 3.12+ and can be run in any virtual environment with the required dependencies:

```bash
# Using uv (recommended)
uv add "sqlalchemy>=1.4,<2.0" alembic asyncpg yarl

# Or using pip
pip install "sqlalchemy>=1.4,<2.0" alembic asyncpg yarl
```

## Usage

```bash
python alembic-rebase.py [options] <base_head> <top_head>
```

### Arguments

- `top_head`: The revision ID that will remain at the top of the history after rebasing
- `base_head`: The revision ID that will be moved below the top head in the history

### Options

- `-f, --config PATH`: Path to alembic.ini file (default: alembic.ini)
- `--verbose, -v`: Enable verbose logging
- `--show-heads`: Show current migration file heads and exit
- `--help, -h`: Show help message

### Examples

```bash
# Basic usage with default alembic.ini
python alembic-rebase.py 1000a1b2c3d4e5 2000f6e7d8c9ba

# Using custom alembic.ini location
python alembic-rebase.py -f ./configs/db1/alembic.ini 1000a1b2c3d4e5 2000f6e7d8c9ba
# Or using long form
python alembic-rebase.py --config ./configs/db1/alembic.ini 1000a1b2c3d4e5 2000f6e7d8c9ba

# Verbose output
python alembic-rebase.py -v 1000a1b2c3d4e5 2000f6e7d8c9ba

# Show current migration file heads
python alembic-rebase.py --show-heads
```

## How It Works

The rebasing process consists of four main phases:

### Phase 1: Analysis and Validation

1. **Configuration Loading**
   - Parse `alembic.ini` to extract `script_location` and `sqlalchemy.url`
   - Convert database URL to async format (`postgresql+asyncpg://`)
   - Initialize alembic Config and ScriptDirectory objects

2. **Revision Validation**
   - Verify both top_head and base_head are solely current database heads
   - Ensure they are different revisions
   - Validate that both revisions exist in the migration files

3. **Chain Analysis**
   - Build migration chains for both heads by following `down_revision` links
   - Find the common ancestor between the two chains
   - Identify migrations to rebase (the base_head chain followed by the top_head chain from the common ancestor onwards)

### Phase 2: Downgrade to Common Ancestor

1. **Downgrade to Common Ancestor**
   - Use alembic to downgrade database to the common ancestor revision
   - This removes all migrations from both diverged branches

### Phase 3: History Rewriting

This tool modifies migration files to reflect the new linearized revision history.

1. **Find the rebasing point**
   - Get the revision ID of the last migration in the base_head chain after the common ancestor
   - Get the revision ID of the first migration in the top_head chain after the common ancestor

2. **File Rewriting**
   - For the first migration, update the `down_revision` field to the revision ID of the last migration of the base_head chain
   - Preserve all other content (upgrade/downgrade functions, imports, etc.)

3. **Integrity Validation**
   - Validate Python syntax of modified files
   - Ensure all required alembic elements are present
   - Verify migration chain linkage is correct and there is only a single head revision in the history

### Phase 4: Apply Linearized History

1. **Apply Rebased Migrations**
   - Run the regular alembic upgrade procedure using the new history chain
   - Database now reflects the rebased state

## Configuration Requirements

Your `alembic.ini` file must contain:

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://user:password@host:port/database
```

The script automatically converts PostgreSQL URLs to async format (postgresql+asyncpg://).

## Testing

Run the test suite:

```bash
# Run all tests
python -m pytest test_alembic_rebase_simple.py test_alembic_rebase_full.py -v

# Run simple tests only
python -m pytest test_alembic_rebase_simple.py -v

# Run comprehensive file modification tests
python -m pytest test_alembic_rebase_full.py -v
```

The test suite includes:

**Basic Tests (`test_alembic_rebase_simple.py`)**:
- Configuration loading and validation
- Migration chain analysis
- Common ancestor detection
- Error handling scenarios
- CLI argument parsing

**Comprehensive Tests (`test_alembic_rebase_full.py`)**:
- Real migration file creation and modification
- Mock schema with users, posts, and tags tables
- File integrity validation
- Migration chain rewriting and validation
- Complete end-to-end rebase workflow
- Proper cleanup of generated test files

## Error Handling

The script provides detailed error messages for common issues:

- Missing or invalid alembic.ini file
- Missing required configuration sections
- Invalid revision IDs
- No common ancestor between branches
- Database connection issues
- Migration file parsing errors
- Migration integrity validation failures
- Broken migration chain linkage

## Development Setup

```bash
# Clone and setup with uv
git clone <repository>
cd alembic-rebase
uv sync

# Run tests
uv run python -m pytest test_alembic_rebase_simple.py test_alembic_rebase_full.py -v

# Run code formatting and linting
uv run ruff format .
uv run ruff check --fix .

# Run type checking
uv run mypy alembic-rebase.py

# Install pre-commit hooks (runs ruff and mypy automatically on commit)
uv run pre-commit install

# Run pre-commit hooks manually on all files
uv run pre-commit run --all-files

# Run the script
uv run python alembic-rebase.py --help
```

## License

This project is provided as-is for educational and development purposes.
