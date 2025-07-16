# Alembic Rebase Example

This document shows what happens to migration files when using the alembic rebase tool.

## Before Rebase

You have two diverged migration branches:

**Branch A (User Features)**:
```
00004a7b9c2e1f -> 1000f3e4d5c6b7 -> 10008a9b0c1d2e
```

**Branch B (Posts Features)**:
```
00004a7b9c2e1f -> 2000e7f8a9b4c5 -> 20003d6e7f8a9b
```

### Example Migration Files

**`001_00004a7b9c2e1f_create_users_table.py`**:
```python
"""Create users table

Revision ID: 00004a7b9c2e1f
Revises:
Create Date: 2024-01-01 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '00004a7b9c2e1f'
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

**`004_2000e7f8a9b4c5_create_posts.py`**:
```python
"""Create posts table

Revision ID: 2000e7f8a9b4c5
Revises: 00004a7b9c2e1f
Create Date: 2024-01-02 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2000e7f8a9b4c5'
down_revision = '00004a7b9c2e1f'
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
python alembic-rebase.py 10008a9b0c1d2e 20003d6e7f8a9b
```

This command means:
- `10008a9b0c1d2e` (target_head): Keep this branch as the main line
- `20003d6e7f8a9b` (base_head): Rebase this branch onto the target

## After Rebase

The script will:

1. **Keep original revision IDs** (Alembic IDs are immutable unlike git commits)
2. **Update only the linkage** by modifying `down_revision` fields
3. **Files stay in place** with same names since revision IDs don't change

### Transformed Migration Files

**`004_2000e7f8a9b4c5_create_posts.py`** (updated linkage only):
```python
"""Create posts table

Revision ID: 2000e7f8a9b4c5
Revises: 10008a9b0c1d2e
Create Date: 2024-01-02 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2000e7f8a9b4c5'      # <- UNCHANGED: Original revision ID
down_revision = '10008a9b0c1d2e'   # <- UPDATED: Now points to 10008a9b0c1d2e
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

**`005_20003d6e7f8a9b_add_post_tags.py`** (updated linkage only):
```python
"""Add post tags functionality

Revision ID: 20003d6e7f8a9b
Revises: 2000e7f8a9b4c5
Create Date: 2024-01-03 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20003d6e7f8a9b'      # <- UNCHANGED: Original revision ID
down_revision = '2000e7f8a9b4c5' # <- UPDATED: Points to previous rebased migration
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
00004a7b9c2e1f -> 1000f3e4d5c6b7 -> 10008a9b0c1d2e -> 2000e7f8a9b4c5 -> 20003d6e7f8a9b
```

The posts features are now properly built on top of the user features, maintaining all functionality while creating a clean, linear migration history.

## Key Benefits

1. **Content Preservation**: All upgrade/downgrade logic is kept exactly as written
2. **ID Immutability**: Revision IDs remain unchanged (unlike git commits)
3. **Linkage Updates**: Only `down_revision` fields are modified to reflect new parent relationships
4. **File Stability**: Files keep their original names since revision IDs don't change
5. **Validation**: Script ensures all files are syntactically valid after modification
6. **Database Sync**: The database state is properly updated to match the new linkage structure

This approach is much safer than manually editing migration files and ensures consistency between your migration files and database state.
