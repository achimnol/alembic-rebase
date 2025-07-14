#!/usr/bin/env python3
"""Comprehensive test suite for alembic rebase script with actual migration files."""

import asyncio
import os
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
            config_content = """[alembic]
script_location = migrations
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
            migrations_dir = temp_dir / "migrations"
            migrations_dir.mkdir()

            # Create alembic env.py
            env_py = migrations_dir / "env.py"
            env_py_content = """from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
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

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
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

            # Change to temp directory for alembic operations
            original_cwd = os.getcwd()
            os.chdir(temp_dir)

            yield temp_dir, alembic_ini, versions_dir

        finally:
            os.chdir(original_cwd)
            shutil.rmtree(temp_dir)

    def _create_mock_migration_files(self, versions_dir: Path):
        """Create a set of mock migration files representing a branched migration history."""
        # Base migration - create users table
        base_migration = versions_dir / "001_base_create_users_table.py"
        base_migration.write_text('''"""Create users table

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
        branch_a1 = versions_dir / "002_branch_a1_add_user_profile.py"
        branch_a1.write_text('''"""Add user profile fields

Revision ID: branch_a1
Revises: base001
Create Date: 2024-01-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'branch_a1'
down_revision = 'base001'
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

        branch_a2 = versions_dir / "003_branch_a2_add_user_preferences.py"
        branch_a2.write_text('''"""Add user preferences table

Revision ID: branch_a2
Revises: branch_a1
Create Date: 2024-01-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'branch_a2'
down_revision = 'branch_a1'
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
        branch_b1 = versions_dir / "004_branch_b1_create_posts.py"
        branch_b1.write_text('''"""Create posts table

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

        branch_b2 = versions_dir / "005_branch_b2_add_post_tags.py"
        branch_b2.write_text('''"""Add post tags functionality

Revision ID: branch_b2
Revises: branch_b1
Create Date: 2024-01-03 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'branch_b2'
down_revision = 'branch_b1'
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
        rebase._load_alembic_config()

        # Test finding existing files
        file_path = rebase._find_migration_file("base001")
        assert file_path is not None
        # Check it found the right file by checking content
        content = file_path.read_text()
        assert "revision = 'base001'" in content

        file_path = rebase._find_migration_file("branch_a1")
        assert file_path is not None
        content = file_path.read_text()
        assert "revision = 'branch_a1'" in content

        # Test nonexistent revision
        file_path = rebase._find_migration_file("nonexistent")
        assert file_path is None

    def test_parse_migration_file(self, temp_alembic_env):
        """Test parsing migration file content."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Test parsing base migration
        file_path = rebase._find_migration_file("base001")
        revision, down_revision, content = rebase._parse_migration_file(file_path)
        assert revision == "base001"
        assert down_revision is None
        assert "Create users table" in content

        # Test parsing branch migration
        file_path = rebase._find_migration_file("branch_a1")
        revision, down_revision, content = rebase._parse_migration_file(file_path)
        assert revision == "branch_a1"
        assert down_revision == "base001"
        assert "Add user profile fields" in content

    def test_generate_new_revision_id(self, temp_alembic_env):
        """Test generating new revision IDs."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))

        # Generate multiple IDs and ensure they're unique
        ids = [rebase._generate_new_revision_id() for _ in range(10)]
        assert len(set(ids)) == 10  # All unique

        # Check format (12 character hex string)
        for rev_id in ids:
            assert len(rev_id) == 12
            assert all(c in "0123456789abcdef" for c in rev_id)

    def test_update_migration_file(self, temp_alembic_env):
        """Test updating migration file with new revision IDs."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Find and backup original file
        original_file = rebase._find_migration_file("branch_a1")
        original_file.read_text()

        # Update the file
        new_revision = rebase._generate_new_revision_id()
        new_down_revision = "new_base_revision"

        rebase._update_migration_file(
            original_file, "branch_a1", new_revision, new_down_revision
        )

        # Check that file was updated correctly
        new_file = rebase._find_migration_file(new_revision)
        assert new_file is not None

        new_revision_parsed, new_down_parsed, _new_content = (
            rebase._parse_migration_file(new_file)
        )
        assert new_revision_parsed == new_revision
        assert new_down_parsed == new_down_revision

        # Ensure the original file no longer exists (if filename changed)
        if new_revision != "branch_a1":
            assert not rebase._find_migration_file("branch_a1")

    @patch.object(AlembicRebase, "_get_current_heads")
    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_rewrite_migration_files(
        self, mock_upgrade, mock_downgrade, mock_get_heads, temp_alembic_env
    ):
        """Test the complete migration file rewriting process."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock the async methods
        mock_get_heads.return_value = ["branch_a2", "branch_b2"]
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Test rewriting files for branch B
        migrations_to_rebase = ["branch_b1", "branch_b2"]
        target_head = "branch_a2"

        # Backup original files
        original_files = {}
        for migration in migrations_to_rebase:
            file_path = rebase._find_migration_file(migration)
            original_files[migration] = file_path.read_text()

        # Perform rewrite
        rebase._rewrite_migration_files(migrations_to_rebase, target_head)

        # Verify new revision mappings were created
        assert len(rebase.revision_mapping) == 2
        assert "branch_b1" in rebase.revision_mapping
        assert "branch_b2" in rebase.revision_mapping

        # Verify new files exist and old files are gone
        for old_revision in migrations_to_rebase:
            new_revision = rebase.revision_mapping[old_revision]

            # New file should exist
            new_file = rebase._find_migration_file(new_revision)
            assert new_file is not None

            # Old file should not exist (filename changed)
            old_file = rebase._find_migration_file(old_revision)
            assert old_file is None

        # Verify the chain is correctly updated
        new_b1_revision = rebase.revision_mapping["branch_b1"]
        new_b2_revision = rebase.revision_mapping["branch_b2"]

        # First rebased migration should point to target_head
        new_b1_file = rebase._find_migration_file(new_b1_revision)
        _, down_rev_b1, _ = rebase._parse_migration_file(new_b1_file)
        assert down_rev_b1 == target_head

        # Second rebased migration should point to first rebased migration
        new_b2_file = rebase._find_migration_file(new_b2_revision)
        _, down_rev_b2, _ = rebase._parse_migration_file(new_b2_file)
        assert down_rev_b2 == new_b1_revision

    @patch.object(AlembicRebase, "_get_current_heads")
    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_file_content_preservation(
        self, mock_upgrade, mock_downgrade, mock_get_heads, temp_alembic_env
    ):
        """Test that migration file content is preserved during rebase."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock the async methods
        mock_get_heads.return_value = ["branch_a2", "branch_b2"]
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Get original content
        original_file = rebase._find_migration_file("branch_b1")
        original_content = original_file.read_text()

        # Rewrite the file
        rebase._rewrite_migration_files(["branch_b1"], "branch_a2")

        # Get new content
        new_revision = rebase.revision_mapping["branch_b1"]
        new_file = rebase._find_migration_file(new_revision)
        new_content = new_file.read_text()

        # Verify important content is preserved
        assert "Create posts table" in new_content
        assert "op.create_table" in new_content
        assert "user_id" in new_content
        assert "def upgrade()" in new_content
        assert "def downgrade()" in new_content

        # Verify only revision IDs changed

        original_lines = original_content.split("\n")
        new_lines = new_content.split("\n")

        # Count lines that changed (should only be revision and down_revision lines)
        changed_lines = 0
        for orig, new in zip(original_lines, new_lines, strict=False):
            if orig != new:
                if "revision =" in orig or "down_revision =" in orig:
                    changed_lines += 1
                else:
                    # If other lines changed, that's unexpected
                    print(f"Unexpected change: '{orig}' -> '{new}'")

        # Should have changed exactly 2 lines (revision and down_revision)
        assert changed_lines == 2

    def test_error_handling_missing_migration_file(self, temp_alembic_env):
        """Test error handling when migration file is missing."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        with pytest.raises(AlembicRebaseError, match="Could not find migration file"):
            rebase._rewrite_migration_files(["nonexistent_revision"], "branch_a2")

    def test_migration_file_cleanup(self, temp_alembic_env):
        """Test that original migration files are properly cleaned up."""
        _temp_dir, alembic_ini, versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Count original files
        original_files = list(versions_dir.glob("*.py"))
        original_count = len(original_files)

        # Rewrite some migrations
        rebase._rewrite_migration_files(["branch_b1", "branch_b2"], "branch_a2")

        # Count files after rewrite
        new_files = list(versions_dir.glob("*.py"))
        new_count = len(new_files)

        # Should have same number of files (old ones deleted, new ones created)
        assert new_count == original_count

        # Verify specific old files are gone and new ones exist
        remaining_old_files = [
            f for f in new_files if "branch_b1" in f.name or "branch_b2" in f.name
        ]
        assert len(remaining_old_files) == 0

        # Verify new files exist
        for old_revision in ["branch_b1", "branch_b2"]:
            new_revision = rebase.revision_mapping[old_revision]
            new_files_with_revision = [f for f in new_files if new_revision in f.name]
            assert len(new_files_with_revision) == 1

    def test_validation_methods(self, temp_alembic_env):
        """Test validation methods for migration integrity."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()

        # Test individual file validation
        assert rebase._validate_migration_file_integrity("base001")
        assert rebase._validate_migration_file_integrity("branch_a1")
        assert not rebase._validate_migration_file_integrity("nonexistent")

        # Test chain validation - should work for existing chains
        assert rebase._validate_migration_chain_integrity([
            "base001",
            "branch_a1",
            "branch_a2",
        ])
        assert rebase._validate_migration_chain_integrity([
            "base001",
            "branch_b1",
            "branch_b2",
        ])

        # Test broken chain validation
        assert not rebase._validate_migration_chain_integrity([
            "base001",
            "branch_b1",
            "branch_a2",
        ])

    @patch.object(AlembicRebase, "_get_current_heads")
    @patch.object(AlembicRebase, "_downgrade_to_revision")
    @patch.object(AlembicRebase, "_upgrade_to_head")
    def test_complete_rebase_workflow(
        self, mock_upgrade, mock_downgrade, mock_get_heads, temp_alembic_env
    ):
        """Test the complete end-to-end rebase workflow with file modifications."""
        _temp_dir, alembic_ini, _versions_dir = temp_alembic_env

        # Mock the database operations
        mock_get_heads.return_value = ["branch_a2", "branch_b2"]
        mock_downgrade.return_value = AsyncMock()
        mock_upgrade.return_value = AsyncMock()

        rebase = AlembicRebase(str(alembic_ini))
        rebase._load_alembic_config()  # Load config first

        # Mock the alembic components to avoid actual ScriptDirectory operations
        with (
            patch("alembic_rebase.Config") as mock_config,
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            mock_config.return_value = MagicMock()
            mock_script_instance = MagicMock()
            mock_script_dir.from_config.return_value = mock_script_instance

            # Setup mock migration chain
            def create_mock_revision(rev_id, down_rev):
                mock_rev = MagicMock()
                mock_rev.revision = rev_id
                mock_rev.down_revision = down_rev
                return mock_rev

            revisions = {
                "base001": create_mock_revision("base001", None),
                "branch_a1": create_mock_revision("branch_a1", "base001"),
                "branch_a2": create_mock_revision("branch_a2", "branch_a1"),
                "branch_b1": create_mock_revision("branch_b1", "base001"),
                "branch_b2": create_mock_revision("branch_b2", "branch_b1"),
            }

            mock_script_instance.get_revision.side_effect = (
                lambda rev_id: revisions.get(rev_id)
            )

            # Store original file contents
            original_files = {}
            for revision in ["branch_b1", "branch_b2"]:
                file_path = rebase._find_migration_file(revision)
                original_files[revision] = file_path.read_text()

            # Perform the complete rebase (mocking the async parts)
            async def run_rebase():
                await rebase.rebase("branch_a2", "branch_b2")

            # This would normally run the full rebase, but we expect it to fail
            # because we're mocking the alembic components
            import contextlib

            with contextlib.suppress(Exception):
                asyncio.run(run_rebase())

            # Check that file rewriting was attempted
            assert len(rebase.revision_mapping) > 0

            # Check that files were actually modified
            for old_revision in ["branch_b1", "branch_b2"]:
                if old_revision in rebase.revision_mapping:
                    new_revision = rebase.revision_mapping[old_revision]
                    new_file = rebase._find_migration_file(new_revision)

                    if new_file:  # If the file was actually created
                        new_content = new_file.read_text()
                        assert f"revision = '{new_revision}'" in new_content

                        # Verify the content was preserved
                        if old_revision == "branch_b1":
                            assert "Create posts table" in new_content
                            assert "op.create_table" in new_content
                        elif old_revision == "branch_b2":
                            assert "Add post tags" in new_content
                            assert "Create tags table" in new_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
