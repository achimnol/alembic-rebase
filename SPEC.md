# Alembic Rebase Logic Specification

This document describes the technical implementation and logic behind the alembic migration rebasing tool. It serves as a reference for understanding how the rebasing process works and can be used as context for future development.

## Overview

The alembic rebase tool solves the problem of diverged migration heads in git repositories by allowing one branch of migrations to be rebased onto another. This is conceptually similar to git rebase but operates on alembic migration files and database state.

## Core Concepts

### Migration Chain
A migration chain is a sequence of migrations where each migration points to its predecessor via the `down_revision` field. For example:
```
base001 -> branch_a1 -> branch_a2
```

### Diverged Heads
When working with git branches, multiple developers may create migrations simultaneously, leading to diverged heads:
```
                base001
               /       \
        branch_a1   branch_b1
            |           |
        branch_a2   branch_b2
```

### Common Ancestor
The common ancestor is the last migration that both branches share. In the example above, `base001` is the common ancestor of branches A and B.

## Rebasing Algorithm

The rebasing process consists of several phases:

### Phase 1: Analysis and Validation

1. **Configuration Loading**
   - Parse `alembic.ini` to extract `script_location` and `sqlalchemy.url`
   - Convert database URL to async format (`postgresql+asyncpg://`)
   - Initialize alembic Config and ScriptDirectory objects

2. **Revision Validation**
   - Verify both target_head and base_head are current database heads
   - Ensure they are different revisions
   - Validate that both revisions exist in the migration files

3. **Chain Analysis**
   - Build migration chains for both heads by following `down_revision` links
   - Find the common ancestor between the two chains
   - Identify migrations to rebase (base_head chain from common ancestor onwards)

### Phase 2: File Modification

This is the core innovation of this tool - it actually modifies migration files to reflect the new structure.

1. **Revision ID Generation**
   - Generate new UUIDs for each migration being rebased
   - Store mapping: `old_revision -> new_revision`

2. **File Rewriting**
   - For each migration file being rebased:
     - Update `revision = 'old_id'` to `revision = 'new_id'`
     - Update `down_revision` to point to the correct parent:
       - First rebased migration points to `target_head`
       - Subsequent migrations point to previous rebased migration
     - Rename file to include new revision ID
     - Preserve all other content (upgrade/downgrade functions, imports, etc.)

3. **Integrity Validation**
   - Validate Python syntax of modified files
   - Ensure all required alembic elements are present
   - Verify migration chain linkage is correct

### Phase 3: Database Operations

1. **Downgrade to Common Ancestor**
   - Use alembic to downgrade database to the common ancestor state
   - This removes all migrations from both diverged branches

2. **Apply Target Branch**
   - Upgrade database to the target_head
   - This applies the branch that will serve as the new base

3. **Apply Rebased Migrations**
   - Apply each rebased migration in order using new revision IDs
   - Database now reflects the rebased state

## Implementation Details

### File Parsing

Migration files are parsed using regex patterns to extract:
- `revision = 'string'` - the migration ID
- `down_revision = 'string'|None` - the parent migration ID

Key regex patterns:
```python
revision_pattern = r"^revision\s*=\s*['\"]([^'\"]+)['\"]"
down_revision_pattern = r"^down_revision\s*=\s*(['\"]([^'\"]*)['\"]|None)"
```

### File Modification Strategy

The tool uses a safe file modification approach:
1. Generate new content with updated revision IDs
2. Write to new filename (if revision ID is in filename)
3. Delete original file only after successful write
4. This ensures atomicity and prevents data loss

### Error Handling

The tool includes comprehensive error handling for:
- Missing or malformed configuration files
- Invalid revision IDs
- Database connection issues
- File parsing errors
- Migration integrity validation failures
- Broken migration chain linkage

## Example Workflow

Given this initial state:
```
Database heads: [branch_a2, branch_b2]

Migration structure:
base001 (in DB and file)
├── branch_a1 (in DB and file)
│   └── branch_a2 (in DB and file) [HEAD]
└── branch_b1 (in DB and file)
    └── branch_b2 (in DB and file) [HEAD]
```

Running: `python alembic_rebase.py branch_a2 branch_b2`

**Phase 1 - Analysis:**
- Common ancestor: `base001`
- Migrations to rebase: `[branch_b1, branch_b2]`
- Target head: `branch_a2`

**Phase 2 - File Modification:**
- Generate new IDs: `branch_b1 -> abc123`, `branch_b2 -> def456`
- Update files:
  - `branch_b1` file: `down_revision = 'branch_a2'`, `revision = 'abc123'`
  - `branch_b2` file: `down_revision = 'abc123'`, `revision = 'def456'`
- Rename files to include new revision IDs

**Phase 3 - Database Operations:**
- Downgrade to `base001`
- Upgrade to `branch_a2`
- Upgrade to `abc123` (rebased branch_b1)
- Upgrade to `def456` (rebased branch_b2)

**Final state:**
```
Database heads: [def456]

Migration structure:
base001
└── branch_a1
    └── branch_a2
        └── abc123 (rebased branch_b1)
            └── def456 (rebased branch_b2) [HEAD]
```

## Key Features

### Migration Content Preservation
- All upgrade/downgrade logic is preserved exactly
- Only revision IDs and linkage are modified
- Comments, imports, and custom code remain unchanged

### Validation and Safety
- Comprehensive file integrity validation
- Python syntax checking after modification
- Migration chain linkage verification
- Atomic file operations to prevent corruption

### Async Operations
- Uses asyncpg for efficient database operations
- Async/await pattern throughout database interactions
- Compatible with SQLAlchemy 1.4 async patterns

## Testing Strategy

The project includes two test suites:

### Simple Tests (`test_alembic_rebase_simple.py`)
- Unit tests with mocked dependencies
- Configuration loading and validation
- Chain analysis logic
- Error handling scenarios

### Comprehensive Tests (`test_alembic_rebase_full.py`)
- Integration tests with actual file manipulation
- Real migration file creation and modification
- End-to-end workflow testing
- File cleanup verification

## Limitations and Considerations

### Current Limitations
1. **Merge Migrations**: Complex merge scenarios with multiple parents are simplified
2. **Manual Resolution**: Some conflicts may require manual intervention
3. **PostgreSQL Only**: Currently optimized for PostgreSQL with asyncpg

### Safety Considerations
1. **Backup Recommended**: Always backup migration files before rebasing
2. **Team Coordination**: Ensure team members are aware of rebasing operations
3. **Testing Required**: Thoroughly test rebased migrations before deployment

## Future Enhancement Opportunities

1. **Multi-database Support**: Extend beyond PostgreSQL
2. **Interactive Mode**: Allow user to resolve conflicts interactively
3. **Dry Run Mode**: Preview changes before applying them
4. **Git Integration**: Automatic git operations alongside rebasing
5. **Conflict Resolution**: Better handling of complex merge scenarios

## Configuration Reference

### Required alembic.ini Sections
```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://user:pass@host/db
```

### Environment Variables
The tool respects standard alembic environment variable overrides:
- `ALEMBIC_CONFIG`: Path to alembic.ini file
- `DATABASE_URL`: Override for sqlalchemy.url

## Dependencies

### Runtime Dependencies
- Python 3.12+
- SQLAlchemy 1.4.x
- alembic
- asyncpg
- configparser (built-in)

### Development Dependencies
- pytest (testing)
- pytest-asyncio (async testing)
- ruff (formatting and linting)
- mypy (type checking)
- pre-commit (git hooks for code quality)
- uv (dependency management)

This specification provides a complete understanding of the rebasing logic and can serve as a reference for future development, debugging, or enhancement of the tool.
