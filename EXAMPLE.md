# Alembic Rebase Example

This document shows what happens to migration files when using the alembic rebase tool.

## Before Rebase

You have two diverged migration branches:

**Branch A (User Features)**:
```
base001 -> branch_a1 -> branch_a2
```

**Branch B (Posts Features)**:
```
base001 -> branch_b1 -> branch_b2
```

### Example Migration Files

**`001_base_create_users_table.py`**:
```python
"""Create users table

Revision ID: base001
Revises: 
Create Date: 2024-01-01 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'base001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(100), nullable=False)
    )

def downgrade() -> None:
    op.drop_table('users')
```

**`004_branch_b1_create_posts.py`**:
```python
"""Create posts table

Revision ID: branch_b1
Revises: base001
Create Date: 2024-01-02 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'branch_b1'
down_revision = 'base001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('posts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text, nullable=False)
    )

def downgrade() -> None:
    op.drop_table('posts')
```

## Running the Rebase

To rebase branch B onto branch A:

```bash
python alembic_rebase.py branch_a2 branch_b2
```

This command means:
- `branch_a2` (target_head): Keep this branch as the main line
- `branch_b2` (base_head): Rebase this branch onto the target

## After Rebase

The script will:

1. **Generate new revision IDs** for the rebased migrations
2. **Update the migration files** with new IDs and proper linkage
3. **Rename the files** to reflect new revision IDs

### Transformed Migration Files

**`004_abc123def456_create_posts.py`** (renamed and updated):
```python
"""Create posts table

Revision ID: abc123def456
Revises: branch_a2
Create Date: 2024-01-02 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'abc123def456'      # <- NEW: Generated revision ID
down_revision = 'branch_a2'   # <- UPDATED: Now points to branch_a2
branch_labels = None
depends_on = None

# Content is preserved exactly as-is
def upgrade() -> None:
    op.create_table('posts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text, nullable=False)
    )

def downgrade() -> None:
    op.drop_table('posts')
```

**`005_xyz789abc123_add_post_tags.py`** (renamed and updated):
```python
"""Add post tags functionality

Revision ID: xyz789abc123
Revises: abc123def456
Create Date: 2024-01-03 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'xyz789abc123'      # <- NEW: Generated revision ID  
down_revision = 'abc123def456' # <- UPDATED: Points to previous rebased migration
branch_labels = None
depends_on = None

# Content is preserved exactly as-is
def upgrade() -> None:
    op.create_table('tags',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False)
    )
    # ... rest of migration content unchanged

def downgrade() -> None:
    # ... unchanged
```

## Final Migration History

After the rebase, your migration history becomes linear:

```
base001 -> branch_a1 -> branch_a2 -> abc123def456 -> xyz789abc123
```

The posts features are now properly built on top of the user features, maintaining all functionality while creating a clean, linear migration history.

## Key Benefits

1. **Content Preservation**: All upgrade/downgrade logic is kept exactly as written
2. **Proper Linkage**: Migration dependencies are automatically updated
3. **File Management**: Old files are removed, new files use updated names
4. **Validation**: Script ensures all files are syntactically valid after modification
5. **Database Sync**: The database state is properly updated to match the new file structure

This approach is much safer than manually editing migration files and ensures consistency between your migration files and database state.