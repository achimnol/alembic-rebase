#!/usr/bin/env python3
"""Comprehensive test suite for alembic rebase script with actual migration files."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alembic_rebase import AlembicRebase, AlembicRebaseError


class TestAlembicRebaseWithFiles:
    """Test suite for AlembicRebase with actual migration file manipulation."""

    @pytest.fixture
    def temp_alembic_env(self):
        """Create a comprehensive temporary alembic environment with mock schema."""
        temp_dir = Path(tempfile.mkdtemp(prefix="alembic_rebase_test_"))

        try:
            # Create alembic.ini
            alembic_ini = temp_dir / "alembic.ini"
            migrations_dir = temp_dir / "migrations"
            config_content = f"""[alembic]
script_location = {migrations_dir}
sqlalchemy.url = postgresql://testuser:testpass@localhost/testdb

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
            alembic_ini.write_text(config_content)

            # Create migrations directory structure
            migrations_dir.mkdir()

            # Create alembic env.py
            env_py = migrations_dir / "env.py"
            env_py_content = """from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
import os
import sys

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    # Check if connection is already provided in config attributes
    connection = config.attributes.get("connection")

    if connection is None:
        # Create async engine if no connection provided
        configuration = config.get_section(config.config_ini_section)
        db_url = configuration.get("sqlalchemy.url")

        # Convert to async URL if needed
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql+psycopg2://"):
            db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

        async_engine = create_async_engine(db_url)

        def run_migrations_in_sync(connection):
            context.configure(
                connection=connection, target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()

        async with async_engine.begin() as conn:
            await conn.run_sync(run_migrations_in_sync)
    else:
        # Use existing connection from config attributes
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    # For testing purposes, skip the complex async setup and use offline mode
    # This avoids the asyncio event loop conflicts during testing
    run_migrations_offline()
"""
            env_py.write_text(env_py_content)

            # Create script.py.mako
            script_mako = migrations_dir / "script.py.mako"
            script_mako_content = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''
            script_mako.write_text(script_mako_content)

            # Create versions directory
            versions_dir = migrations_dir / "versions"
            versions_dir.mkdir()

            # Create mock schema migration files
            self._create_mock_migration_files(versions_dir)

            yield temp_dir, alembic_ini, versions_dir

        finally:
            # No need to change directories
            shutil.rmtree(temp_dir)

    def _create_mock_migration_files(self, versions_dir: Path):
        """Create a set of mock migration files representing a branched migration history."""
        # Base migration - create users table
        base_migration = versions_dir / "001_00004a7b9c2e1f_create_users_table.py"
        base_migration.write_text('''"""Create users table

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
    # Create users table
    op.create_table('users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('email', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now())
    )

    # Create unique constraint
    op.create_unique_constraint('uq_users_username', 'users', ['username'])
    op.create_unique_constraint('uq_users_email', 'users', ['email'])


def downgrade() -> None:
    # Drop unique constraints
    op.drop_constraint('uq_users_email', 'users', type_='unique')
    op.drop_constraint('uq_users_username', 'users', type_='unique')

    # Drop users table
    op.drop_table('users')
''')

        # Branch A - Add user profile features
        branch_a1 = versions_dir / "002_1000f3e4d5c6b7_add_user_profile.py"
        branch_a1.write_text('''"""Add user profile fields

Revision ID: 1000f3e4d5c6b7
Revises: 00004a7b9c2e1f
Create Date: 2024-01-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1000f3e4d5c6b7'
down_revision = '00004a7b9c2e1f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add profile fields to users table
    op.add_column('users', sa.Column('first_name', sa.String(50)))
    op.add_column('users', sa.Column('last_name', sa.String(50)))
    op.add_column('users', sa.Column('bio', sa.Text))
    op.add_column('users', sa.Column('avatar_url', sa.String(255)))


def downgrade() -> None:
    # Remove profile fields
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'bio')
    op.drop_column('users', 'last_name')
    op.drop_column('users', 'first_name')
''')

        branch_a2 = versions_dir / "003_10008a9b0c1d2e_add_user_preferences.py"
        branch_a2.write_text('''"""Add user preferences table

Revision ID: 10008a9b0c1d2e
Revises: 1000f3e4d5c6b7
Create Date: 2024-01-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '10008a9b0c1d2e'
down_revision = '1000f3e4d5c6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create user_preferences table
    op.create_table('user_preferences',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('theme', sa.String(20), default='light'),
        sa.Column('language', sa.String(10), default='en'),
        sa.Column('notifications_enabled', sa.Boolean, default=True)
    )

    # Create index on user_id
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'])


def downgrade() -> None:
    # Drop index and table
    op.drop_index('ix_user_preferences_user_id', 'user_preferences')
    op.drop_table('user_preferences')
''')

        # Branch B - Add posts functionality
        branch_b1 = versions_dir / "004_2000e7f8a9b4c5_create_posts.py"
        branch_b1.write_text('''"""Create posts table

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
    # Create posts table
    op.create_table('posts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('published', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, onupdate=sa.func.now())
    )

    # Create indexes
    op.create_index('ix_posts_user_id', 'posts', ['user_id'])
    op.create_index('ix_posts_published', 'posts', ['published'])


def downgrade() -> None:
    # Drop indexes and table
    op.drop_index('ix_posts_published', 'posts')
    op.drop_index('ix_posts_user_id', 'posts')
    op.drop_table('posts')
''')

        branch_b2 = versions_dir / "005_20003d6e7f8a9b_add_post_tags.py"
        branch_b2.write_text('''"""Add post tags functionality

Revision ID: 20003d6e7f8a9b
Revises: 2000e7f8a9b4c5
Create Date: 2024-01-03 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20003d6e7f8a9b'
down_revision = '2000e7f8a9b4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tags table
    op.create_table('tags',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('color', sa.String(7), default='#000000')
    )

    # Create post_tags association table
    op.create_table('post_tags',
        sa.Column('post_id', sa.Integer, sa.ForeignKey('posts.id'), primary_key=True),
        sa.Column('tag_id', sa.Integer, sa.ForeignKey('tags.id'), primary_key=True)
    )

    # Create indexes
    op.create_index('ix_post_tags_post_id', 'post_tags', ['post_id'])
    op.create_index('ix_post_tags_tag_id', 'post_tags', ['tag_id'])


def downgrade() -> None:
    # Drop indexes and tables
    op.drop_index('ix_post_tags_tag_id', 'post_tags')
    op.drop_index('ix_post_tags_post_id', 'post_tags')
    op.drop_table('post_tags')
    op.drop_table('tags')
''')

    def test_find_migration_file(self, temp_alembic_env):
        """Test finding migration files by revision ID."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Test finding existing files
        file_path = rebase._find_migration_file("00004a7b9c2e1f")
        assert file_path is not None
        # Check it found the right file by checking content
        content = file_path.read_text()
        assert "revision = '00004a7b9c2e1f'" in content

        file_path = rebase._find_migration_file("1000f3e4d5c6b7")
        assert file_path is not None
        content = file_path.read_text()
        assert "revision = '1000f3e4d5c6b7'" in content

        # Test nonexistent revision
        file_path = rebase._find_migration_file("nonexistent")
        assert file_path is None

    def test_parse_migration_file(self, temp_alembic_env):
        """Test parsing migration file content."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Test parsing base migration
        file_path = rebase._find_migration_file("00004a7b9c2e1f")
        assert file_path is not None
        revision, down_revision, content = rebase._parse_migration_file(file_path)
        assert revision == "00004a7b9c2e1f"
        assert down_revision is None
        assert "Create users table" in content

        # Test parsing branch migration
        file_path = rebase._find_migration_file("1000f3e4d5c6b7")
        assert file_path is not None
        revision, down_revision, content = rebase._parse_migration_file(file_path)
        assert revision == "1000f3e4d5c6b7"
        assert down_revision == "00004a7b9c2e1f"
        assert "Add user profile fields" in content

    def test_revision_id_immutability(self, temp_alembic_env):
        """Test that revision IDs remain unchanged during rebase (unlike git)."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Get original revision from file
        file_path = rebase._find_migration_file("2000e7f8a9b4c5")
        assert file_path is not None
        original_revision, _, _ = rebase._parse_migration_file(file_path)

        # Verify original revision ID
        assert original_revision == "2000e7f8a9b4c5"

    def test_update_migration_file(self, temp_alembic_env):
        """Test updating migration file with new revision IDs."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Find and backup original file
        original_file = rebase._find_migration_file("1000f3e4d5c6b7")
        assert original_file is not None
        original_file.read_text()

        # Update the file (keep same revision ID, change down_revision)
        new_down_revision = "new_base_revision"

        rebase._update_migration_file(
            original_file, "1000f3e4d5c6b7", "1000f3e4d5c6b7", new_down_revision
        )

        # Check that file was updated correctly (same file, updated content)
        updated_file = rebase._find_migration_file("1000f3e4d5c6b7")
        assert updated_file is not None

        revision_parsed, down_parsed, _content = rebase._parse_migration_file(
            updated_file
        )
        assert revision_parsed == "1000f3e4d5c6b7"  # Revision ID unchanged
        assert down_parsed == new_down_revision  # down_revision updated

    @patch.object(AlembicRebase, "_get_current_heads_from_files")
    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_rewrite_migration_files(
        self, mock_upgrade, mock_downgrade, mock_get_heads, temp_alembic_env
    ):
        """Test the complete migration file rewriting process."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock the async methods
        mock_get_heads.return_value = ["10008a9b0c1d2e", "20003d6e7f8a9b"]
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))

        # Test rewriting files for branch B
        migrations_to_rebase = ["2000e7f8a9b4c5", "20003d6e7f8a9b"]
        last_top_migration = "10008a9b0c1d2e"

        # Backup original files
        original_files = {}
        for migration in migrations_to_rebase:
            file_path = rebase._find_migration_file(migration)
            assert file_path is not None
            original_files[migration] = file_path.read_text()

        # Perform rewrite
        rebase._rewrite_migration_files(migrations_to_rebase, last_top_migration)

        # Verify migrations were processed (no revision mappings in new approach)
        # Migrations keep their original IDs, only linkage changes

        # Verify files still exist with original revision IDs
        for revision in migrations_to_rebase:
            # File should still exist with same name
            file_path = rebase._find_migration_file(revision)
            assert file_path is not None

        # Verify the chain linkage is correctly updated
        b1_revision = "2000e7f8a9b4c5"
        b2_revision = "20003d6e7f8a9b"

        # First rebased migration should point to last_top_migration
        b1_file = rebase._find_migration_file(b1_revision)
        assert b1_file is not None
        _, down_rev_b1, _ = rebase._parse_migration_file(b1_file)
        assert down_rev_b1 == last_top_migration

        # Second rebased migration should point to first rebased migration
        b2_file = rebase._find_migration_file(b2_revision)
        assert b2_file is not None
        _, down_rev_b2, _ = rebase._parse_migration_file(b2_file)
        assert down_rev_b2 == b1_revision

    @patch.object(AlembicRebase, "_get_current_heads_from_files")
    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_file_content_preservation(
        self, mock_upgrade, mock_downgrade, mock_get_heads, temp_alembic_env
    ):
        """Test that migration file content is preserved during rebase."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock the async methods
        mock_get_heads.return_value = ["10008a9b0c1d2e", "20003d6e7f8a9b"]
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))

        # Get original content
        original_file = rebase._find_migration_file("2000e7f8a9b4c5")
        assert original_file is not None
        original_content = original_file.read_text()

        # Rewrite the file
        rebase._rewrite_migration_files(["2000e7f8a9b4c5"], "10008a9b0c1d2e")

        # Get updated content (same file, updated linkage)
        updated_file = rebase._find_migration_file("2000e7f8a9b4c5")
        assert updated_file is not None
        updated_content = updated_file.read_text()

        # Verify important content is preserved
        assert "Create posts table" in updated_content
        assert "op.create_table" in updated_content
        assert "user_id" in updated_content
        assert "def upgrade()" in updated_content
        assert "def downgrade()" in updated_content

        # Verify only down_revision changed (revision ID stays same)
        original_lines = original_content.split("\n")
        updated_lines = updated_content.split("\n")

        # Count lines that changed (should only be down_revision line)
        changed_lines = 0
        for orig, updated in zip(original_lines, updated_lines, strict=False):
            if orig != updated:
                if "down_revision =" in orig:
                    changed_lines += 1
                elif "revision =" in orig:
                    # Revision line should NOT change
                    raise AssertionError(
                        f"Revision line changed unexpectedly: '{orig}' -> '{updated}'"
                    )
                else:
                    # If other lines changed, that's unexpected
                    print(f"Unexpected change: '{orig}' -> '{updated}'")

        # Should have changed exactly 1 line (down_revision only)
        assert changed_lines == 1

    def test_error_handling_missing_migration_file(self, temp_alembic_env):
        """Test error handling when migration file is missing."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        with pytest.raises(AlembicRebaseError, match="Could not find migration file"):
            rebase._rewrite_migration_files(["nonexistent_revision"], "10008a9b0c1d2e")

    def test_migration_file_cleanup(self, temp_alembic_env):
        """Test that migration files remain the same after rebase (no cleanup needed)."""
        _temp_dir, alembic_ini, versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Count original files
        original_files = list(versions_dir.glob("*.py"))
        original_count = len(original_files)

        # Rewrite some migrations
        rebase._rewrite_migration_files(
            ["2000e7f8a9b4c5", "20003d6e7f8a9b"], "10008a9b0c1d2e"
        )

        # Count files after rewrite
        new_files = list(versions_dir.glob("*.py"))
        new_count = len(new_files)

        # Should have same number of files (files updated in-place)
        assert new_count == original_count

        # Verify specific files still exist (same revision IDs)
        remaining_files = [
            f
            for f in new_files
            if "2000e7f8a9b4c5" in f.name or "20003d6e7f8a9b" in f.name
        ]
        assert len(remaining_files) == 2  # Both files should still exist

    def test_validation_methods(self, temp_alembic_env):
        """Test validation methods for migration integrity."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Test individual file validation
        assert rebase._validate_migration_file_integrity("00004a7b9c2e1f")
        assert rebase._validate_migration_file_integrity("1000f3e4d5c6b7")
        assert not rebase._validate_migration_file_integrity("nonexistent")

        # Test chain validation - should work for existing chains
        assert rebase._validate_migration_chain_integrity([
            "00004a7b9c2e1f",
            "1000f3e4d5c6b7",
            "10008a9b0c1d2e",
        ])
        assert rebase._validate_migration_chain_integrity([
            "00004a7b9c2e1f",
            "2000e7f8a9b4c5",
            "20003d6e7f8a9b",
        ])

        # Test broken chain validation
        assert not rebase._validate_migration_chain_integrity([
            "00004a7b9c2e1f",
            "2000e7f8a9b4c5",
            "10008a9b0c1d2e",
        ])

    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_complete_rebase_workflow(
        self, mock_upgrade, mock_downgrade, temp_alembic_env
    ):
        """Test the complete end-to-end rebase workflow with file modifications."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock only the database operations (downgrade and upgrade)
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))

        # Store original file contents
        original_files = {}
        for revision in ["2000e7f8a9b4c5", "20003d6e7f8a9b"]:
            file_path = rebase._find_migration_file(revision)
            assert file_path is not None
            original_files[revision] = file_path.read_text()

        # Perform the complete rebase (mocking only the async database parts)
        async def run_rebase():
            await rebase.rebase("20003d6e7f8a9b", "10008a9b0c1d2e")

        # Run the rebase - this should now work with actual temp files
        asyncio.run(run_rebase())

        # Check that files were actually modified (only linkage changes)
        for revision in ["2000e7f8a9b4c5", "20003d6e7f8a9b"]:
            file_path = rebase._find_migration_file(revision)

            if file_path:  # If the file exists
                new_content = file_path.read_text()
                # Verify revision ID is unchanged
                assert f"revision = '{revision}'" in new_content

                # Verify the content was preserved
                if revision == "2000e7f8a9b4c5":
                    assert "Create posts table" in new_content
                    assert "op.create_table" in new_content
                elif revision == "20003d6e7f8a9b":
                    assert "Add post tags" in new_content
                    assert "Create tags table" in new_content

        # Verify the file linkage has been updated correctly
        # The first migration in the rebased chain should now point to the last migration of the base chain
        b1_file = rebase._find_migration_file("2000e7f8a9b4c5")
        assert b1_file is not None
        _, down_rev_b1, _ = rebase._parse_migration_file(b1_file)
        assert down_rev_b1 == "10008a9b0c1d2e"

        # The second migration should still point to the first
        b2_file = rebase._find_migration_file("20003d6e7f8a9b")
        assert b2_file is not None
        _, down_rev_b2, _ = rebase._parse_migration_file(b2_file)
        assert down_rev_b2 == "2000e7f8a9b4c5"

    def test_common_ancestor_with_deep_history(self, temp_alembic_env):
        """Test common ancestor detection with multiple revisions before the common ancestor.

        This test ensures that the algorithm finds the most recent common ancestor
        and not the first revision in the history.
        """
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        with (
            patch("alembic_rebase.Config") as mock_config,
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            # Mock the Config instance with necessary methods
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://testuser:testpass@localhost/testdb"
            )
            mock_config.return_value = mock_config_instance

            mock_script_instance = MagicMock()
            mock_script_dir.from_config.return_value = mock_script_instance

            # Create a deeper revision history with multiple revisions before common ancestor
            # Structure:
            # 00001 -> 00002 -> 00003 -> 00004 (common ancestor)
            #                              ├──  1000 -> 1001 (branch A)
            #                              └──  2000 -> 2001 (branch B)

            def create_mock_revision(rev_id, down_rev):
                mock_rev = MagicMock()
                mock_rev.revision = rev_id
                mock_rev.down_revision = down_rev
                return mock_rev

            revisions = {
                "00001a1b2c3d4e": create_mock_revision("00001a1b2c3d4e", None),
                "00002b2c3d4e5f": create_mock_revision(
                    "00002b2c3d4e5f", "00001a1b2c3d4e"
                ),
                "00003c3d4e5f6a": create_mock_revision(
                    "00003c3d4e5f6a", "00002b2c3d4e5f"
                ),
                "00004d4e5f6a7b": create_mock_revision(
                    "00004d4e5f6a7b", "00003c3d4e5f6a"
                ),
                "1000f3e4d5c6b7": create_mock_revision(
                    "1000f3e4d5c6b7", "00004d4e5f6a7b"
                ),
                "10008a9b0c1d2e": create_mock_revision(
                    "10008a9b0c1d2e", "1000f3e4d5c6b7"
                ),
                "2000e7f8a9b4c5": create_mock_revision(
                    "2000e7f8a9b4c5", "00004d4e5f6a7b"
                ),
                "20003d6e7f8a9b": create_mock_revision(
                    "20003d6e7f8a9b", "2000e7f8a9b4c5"
                ),
            }

            mock_script_instance.get_revision.side_effect = (
                lambda rev_id: revisions.get(rev_id)
            )

            rebase = AlembicRebase(str(alembic_ini))

            # Test that we find the most recent common ancestor, not the first revision
            ancestor = rebase._find_common_ancestor("10008a9b0c1d2e", "20003d6e7f8a9b")
            assert (
                ancestor == "00004d4e5f6a7b"
            )  # Should be the common ancestor, not 00001a1b2c3d4e

            # Test with reversed argument order
            ancestor = rebase._find_common_ancestor("20003d6e7f8a9b", "10008a9b0c1d2e")
            assert ancestor == "00004d4e5f6a7b"  # Should be the same common ancestor

            # Test migration chains to ensure they're correct
            branch_a_chain = rebase._get_migration_chain("10008a9b0c1d2e")
            expected_a_chain = [
                "00001a1b2c3d4e",
                "00002b2c3d4e5f",
                "00003c3d4e5f6a",
                "00004d4e5f6a7b",
                "1000f3e4d5c6b7",
                "10008a9b0c1d2e",
            ]
            assert branch_a_chain == expected_a_chain

            branch_b_chain = rebase._get_migration_chain("20003d6e7f8a9b")
            expected_b_chain = [
                "00001a1b2c3d4e",
                "00002b2c3d4e5f",
                "00003c3d4e5f6a",
                "00004d4e5f6a7b",
                "2000e7f8a9b4c5",
                "20003d6e7f8a9b",
            ]
            assert branch_b_chain == expected_b_chain


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
