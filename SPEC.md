# Alembic Rebase Logic Specification

This document describes the technical implementation and logic behind the alembic migration rebasing tool. It serves as a reference for understanding how the rebasing process works and can be used as context for future development.

## Overview

The alembic rebase tool solves the problem of diverged migration heads in git repositories by allowing one branch of migrations to be rebased onto another.
This is conceptually similar to git rebase but operates on alembic migration files and database state.

This usually happens when:
- The current Git branch has its own migrations.
- The base Git branch (e.g., main) is updated and has new migrations merged from other branches.
- The current Git branch is rebased on the new base branch or the base branch is merged into the current branch.
- Now the current Git branch has diverged alembic migration heads.

In this case, we have two options:
- Make an alembic merge-point migration which has multi-value `down_revision` fields as a tuple.
- Rebase the alembic migration history for linearization.

We take the rebasing approach because it makes it easier to backport the Git squash-merge commits into the older release branches and selectively run the non-backported migrations when upgrading the release (using another separate script to do this).

## Core Concepts

### Migration Chain
A migration chain is a sequence of migrations where each migration points to its predecessor via the `down_revision` field. For example:
```
00004a7b9c2e1f -> 1000f3e4d5c6b7 -> 10008a9b0c1d2e
```

Note that the revision IDs in alembic migrations are just random unique hexademical numbers, which do not change based on its history and content, unlike Git.

### Diverged Heads
When working with git branches, multiple developers may create migrations simultaneously, leading to diverged heads:
```
                00004a7b9c2e1f
               /              \
        1000f3e4d5c6b7   2000e7f8a9b4c5
            |                 |
        10008a9b0c1d2e   20003d6e7f8a9b
```

### Common Ancestor
The common ancestor is the last migration that both branches share.
In the example above, `00004a7b9c2e1f` is the common ancestor of branches A (revisions prefixed with `1000`) and B (revisions prefixed with `2000`).

## Rebasing Algorithm

The rebasing process consists of several phases:

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
   - Get the revision ID of the last migration in the base_head chain after the common ancestor.
   - Get the revision ID of the first migration in the top_head chain after the common ancestor.

2. **File Rewriting**
   - For the first migration, update the `down_revision` field to the revision ID of the last migration of the base_head chain.
   - Preserve all other content (upgrade/downgrade functions, imports, etc.)

3. **Integrity Validation**
   - Validate Python syntax of modified files
   - Ensure all required alembic elements are present
   - Verify migration chain linkage is correct and there is only a single head revision in the history

### Phase 4: Apply Linearized History

1. **Apply Rebased Migrations**
   - Run the regular alembic upgrade procedure using the new history chain
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
1. Update only the `down_revision` field to reflect new parent relationships
2. Keep original revision IDs unchanged (files don't need renaming)
3. Preserve all other migration content exactly
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
Database heads: [10008a9b0c1d2e, 20003d6e7f8a9b]

Migration structure:
00004a7b9c2e1f
├── 1000f3e4d5c6b7 (not in DB yet because it is from the updated base Git branch)
│   └── 10008a9b0c1d2e (not in DB yet because it is from the updated base Git branch) [HEAD]
└── 2000e7f8a9b4c5 (maybe in DB)
    └── 20003d6e7f8a9b (maybe in DB) [HEAD]
```

Running: `python alembic-rebase.py 10008a9b0c1d2e 20003d6e7f8a9b`

**Phase 1 - Analysis:**
- Common ancestor: `00004a7b9c2e1f`
- The migration chains to rebase: `[2000e7f8a9b4c5, 20003d6e7f8a9b]`
- The head revision that will become the base of the top chain: `10008a9b0c1d2e`

**Phase 2 - Downgrade to Common Ancestor:**
- Run alembic downgrade towards `00004a7b9c2e1f`
- This step ensures we could safely apply the new migrations (`1000f3e4d5c6b7` and `10008a9b0c1d2e`) merged into the base git branch
  by rolling back the migrations in the current git branch (`2000e7f8a9b4c5` and `20003d6e7f8a9b`) if already applied during development.

**Phase 3 - History Rewriting:**
- Update the first migration of the top_head chain to follow the new head migration:
  - `2000e7f8a9b4c5` file: `down_revision = '10008a9b0c1d2e'`
- Note that revision IDs and filenames remain unchanged

**Phase 4 - Apply Linearized History:**
- The order of upgrade becomes:
  - `1000f3e4d5c6b7`
  - `10008a9b0c1d2e`
  - `2000e7f8a9b4c5`
  - `20003d6e7f8a9b`

**Final state:**
```
Database heads: [20003d6e7f8a9b]

Migration structure:
00004a7b9c2e1f
└── 1000f3e4d5c6b7
    └── 10008a9b0c1d2e
        └── 2000e7f8a9b4c5
            └── 20003d6e7f8a9b [HEAD]
```

## Key Features

### Migration Content Preservation
- All upgrade/downgrade logic is preserved exactly
- Revision IDs remain unchanged (unlike git commits)
- Only `down_revision` linkage is modified to reflect new parent relationships
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
- yarl

### Development Dependencies
- pytest (testing)
- pytest-asyncio (async testing)
- ruff (formatting and linting)
- mypy (type checking)
- pre-commit (git hooks for code quality)
- uv (dependency management)

This specification provides a complete understanding of the rebasing logic and can serve as a reference for future development, debugging, or enhancement of the tool.
