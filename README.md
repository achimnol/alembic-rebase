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
uv add "sqlalchemy>=1.4,<2.0" alembic asyncpg

# Or using pip
pip install "sqlalchemy>=1.4,<2.0" alembic asyncpg
```

## Usage

```bash
python alembic_rebase.py <target_head> <base_head> [options]
```

### Arguments

- `target_head`: The revision ID that will remain at the top of the history after rebasing
- `base_head`: The revision ID that will be moved below the target head in the history

### Options

- `--alembic-ini PATH`: Path to alembic.ini file (default: alembic.ini)
- `--verbose, -v`: Enable verbose logging
- `--help, -h`: Show help message

### Examples

```bash
# Basic usage with default alembic.ini
python alembic_rebase.py abc123def456 789ghi012jkl

# Using custom alembic.ini location
python alembic_rebase.py --alembic-ini ./configs/db1/alembic.ini abc123 def456

# Verbose output
python alembic_rebase.py -v abc123 def456
```

## How It Works

The script performs the following steps:

1. **Configuration Loading**: Reads the alembic.ini file to get:
   - Script location (migration files directory)
   - Database connection URL (automatically converts to async format)

2. **Validation**: Ensures both revision IDs are valid current heads

3. **Analysis**: Finds the common ancestor between the two diverged branches

4. **File Rewriting**: 
   - Generates new revision IDs for migrations to be rebased
   - Updates migration files with new revision IDs and proper linkage
   - Preserves all migration content (upgrade/downgrade functions)
   - Renames files to reflect new revision IDs

5. **Integrity Validation**:
   - Validates Python syntax of modified files
   - Ensures proper migration chain linkage
   - Confirms all required alembic elements are present

6. **Database Operations**:
   - Downgrades to the common ancestor
   - Upgrades to the target head
   - Applies the rebased migrations with new revision IDs

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

# Run the script
uv run python alembic_rebase.py --help
```

## License

This project is provided as-is for educational and development purposes.