#!/usr/bin/env python3
"""Simplified test suite for alembic rebase script without Docker dependencies."""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alembic_rebase import AlembicRebase, AlembicRebaseError


class TestAlembicRebaseSimple:
    """Simplified test suite for AlembicRebase functionality."""

    @pytest.fixture
    def temp_alembic_env(self):
        """Create a temporary alembic environment for testing."""
        temp_dir = Path(tempfile.mkdtemp())

        try:
            # Create alembic.ini
            alembic_ini = temp_dir / "alembic.ini"
            config_content = """[alembic]
script_location = migrations
sqlalchemy.url = postgresql://user:pass@localhost/testdb

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

            # Create versions directory
            versions_dir = migrations_dir / "versions"
            versions_dir.mkdir()

            yield temp_dir, alembic_ini

        finally:
            shutil.rmtree(temp_dir)

    def test_alembic_rebase_initialization(self, temp_alembic_env):
        """Test AlembicRebase initialization and configuration loading."""
        _temp_dir, alembic_ini = temp_alembic_env

        # Mock the alembic components
        with (
            patch("alembic_rebase.Config") as mock_config,
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://user:pass@localhost/testdb"
            )
            mock_config.return_value = mock_config_instance
            mock_script_dir.from_config.return_value = MagicMock()

            rebase = AlembicRebase(str(alembic_ini))

            assert rebase.config is not None
            assert rebase.script_dir is not None
            assert "postgresql+asyncpg://" in rebase.db_url

    def test_load_nonexistent_config(self):
        """Test error handling for nonexistent config file."""
        with pytest.raises(AlembicRebaseError, match="Alembic config file not found"):
            AlembicRebase("nonexistent.ini")

    def test_load_config_missing_db_url(self, temp_alembic_env):
        """Test error handling for missing database URL."""
        _temp_dir, alembic_ini = temp_alembic_env

        with (
            patch("alembic_rebase.Config") as mock_config,
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = None  # No DB URL
            mock_config.return_value = mock_config_instance
            mock_script_dir.from_config.return_value = MagicMock()

            with pytest.raises(AlembicRebaseError, match=r"No sqlalchemy\.url found"):
                AlembicRebase(str(alembic_ini))

    def create_migration_files(self, temp_dir, migrations_data):
        """Helper to create migration files for testing."""
        versions_dir = temp_dir / "migrations" / "versions"

        for migration in migrations_data:
            migration_file = versions_dir / f"{migration['revision']}_test_migration.py"
            content = f'''"""Test migration

Revision ID: {migration["revision"]}
Revises: {migration.get("down_revision", None)}
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '{migration["revision"]}'
down_revision = {migration.get("down_revision")!r}
branch_labels = None
depends_on = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
'''
            migration_file.write_text(content)

    def test_migration_chain_analysis(self, temp_alembic_env):
        """Test migration chain analysis functionality."""
        temp_dir, alembic_ini = temp_alembic_env

        # Create a linear chain of migrations
        migrations = [
            {"revision": "00004a7b9c2e1f", "down_revision": None},
            {"revision": "1000f3e4d5c6b7", "down_revision": "00004a7b9c2e1f"},
            {"revision": "10008a9b0c1d2e", "down_revision": "1000f3e4d5c6b7"},
        ]

        self.create_migration_files(temp_dir, migrations)

        with (
            patch("alembic_rebase.Config"),
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            # Mock the script directory and revisions
            mock_script_instance = MagicMock()
            mock_script_dir.from_config.return_value = mock_script_instance

            # Mock revision objects
            rev1 = MagicMock()
            rev1.revision = "00004a7b9c2e1f"
            rev1.down_revision = None

            rev2 = MagicMock()
            rev2.revision = "1000f3e4d5c6b7"
            rev2.down_revision = "00004a7b9c2e1f"

            rev3 = MagicMock()
            rev3.revision = "10008a9b0c1d2e"
            rev3.down_revision = "1000f3e4d5c6b7"

            # Setup mock get_revision method
            def mock_get_revision(rev_id):
                if rev_id == "00004a7b9c2e1f":
                    return rev1
                if rev_id == "1000f3e4d5c6b7":
                    return rev2
                if rev_id == "10008a9b0c1d2e":
                    return rev3
                return None

            mock_script_instance.get_revision.side_effect = mock_get_revision

            # Mock config to return a valid DB URL
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://user:pass@localhost/testdb"
            )

            with patch("alembic_rebase.Config") as mock_config:
                mock_config.return_value = mock_config_instance
                rebase = AlembicRebase(str(alembic_ini))

            chain = rebase._get_migration_chain("10008a9b0c1d2e")
            assert chain == ["00004a7b9c2e1f", "1000f3e4d5c6b7", "10008a9b0c1d2e"]

            chain = rebase._get_migration_chain("1000f3e4d5c6b7")
            assert chain == ["00004a7b9c2e1f", "1000f3e4d5c6b7"]

    def test_find_common_ancestor(self, temp_alembic_env):
        """Test finding common ancestor between branches."""
        _temp_dir, alembic_ini = temp_alembic_env

        with (
            patch("alembic_rebase.Config"),
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            # Mock the script directory and revisions
            mock_script_instance = MagicMock()
            mock_script_dir.from_config.return_value = mock_script_instance

            # Mock revision objects for branched structure
            base = MagicMock()
            base.revision = "00004a7b9c2e1f"
            base.down_revision = None

            branch_a1 = MagicMock()
            branch_a1.revision = "1000f3e4d5c6b7"
            branch_a1.down_revision = "00004a7b9c2e1f"

            branch_a2 = MagicMock()
            branch_a2.revision = "10008a9b0c1d2e"
            branch_a2.down_revision = "1000f3e4d5c6b7"

            branch_b1 = MagicMock()
            branch_b1.revision = "2000e7f8a9b4c5"
            branch_b1.down_revision = "00004a7b9c2e1f"

            branch_b2 = MagicMock()
            branch_b2.revision = "20003d6e7f8a9b"
            branch_b2.down_revision = "2000e7f8a9b4c5"

            # Setup mock get_revision method
            def mock_get_revision(rev_id):
                revisions = {
                    "00004a7b9c2e1f": base,
                    "1000f3e4d5c6b7": branch_a1,
                    "10008a9b0c1d2e": branch_a2,
                    "2000e7f8a9b4c5": branch_b1,
                    "20003d6e7f8a9b": branch_b2,
                }
                return revisions.get(rev_id)

            mock_script_instance.get_revision.side_effect = mock_get_revision

            # Mock config to return a valid DB URL
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://user:pass@localhost/testdb"
            )

            with patch("alembic_rebase.Config") as mock_config:
                mock_config.return_value = mock_config_instance
                rebase = AlembicRebase(str(alembic_ini))

            ancestor = rebase._find_common_ancestor("10008a9b0c1d2e", "20003d6e7f8a9b")
            assert ancestor == "00004a7b9c2e1f"

    def test_find_common_ancestor_deep_history(self, temp_alembic_env):
        """Test finding common ancestor with multiple revisions before the common ancestor.

        This test prevents regression where the algorithm would return the first
        revision instead of the most recent common ancestor.
        """
        _temp_dir, alembic_ini = temp_alembic_env

        with (
            patch("alembic_rebase.Config"),
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
        ):
            # Mock the script directory and revisions
            mock_script_instance = MagicMock()
            mock_script_dir.from_config.return_value = mock_script_instance

            # Create a deeper revision history with multiple revisions before common ancestor
            # Structure:
            # 00001 -> 00002 -> 00003 -> 00004 (common ancestor)
            #                              ├── 1000 -> 1001 (branch A)
            #                              └── 2000 -> 2001 (branch B)

            rev_00001 = MagicMock()
            rev_00001.revision = "00001a1b2c3d4e"
            rev_00001.down_revision = None

            rev_00002 = MagicMock()
            rev_00002.revision = "00002b2c3d4e5f"
            rev_00002.down_revision = "00001a1b2c3d4e"

            rev_00003 = MagicMock()
            rev_00003.revision = "00003c3d4e5f6a"
            rev_00003.down_revision = "00002b2c3d4e5f"

            common_ancestor = MagicMock()
            common_ancestor.revision = "00004d4e5f6a7b"
            common_ancestor.down_revision = "00003c3d4e5f6a"

            branch_a1 = MagicMock()
            branch_a1.revision = "1000f3e4d5c6b7"
            branch_a1.down_revision = "00004d4e5f6a7b"

            branch_a2 = MagicMock()
            branch_a2.revision = "10008a9b0c1d2e"
            branch_a2.down_revision = "1000f3e4d5c6b7"

            branch_b1 = MagicMock()
            branch_b1.revision = "2000e7f8a9b4c5"
            branch_b1.down_revision = "00004d4e5f6a7b"

            branch_b2 = MagicMock()
            branch_b2.revision = "20003d6e7f8a9b"
            branch_b2.down_revision = "2000e7f8a9b4c5"

            # Setup mock get_revision method
            def mock_get_revision(rev_id):
                revisions = {
                    "00001a1b2c3d4e": rev_00001,
                    "00002b2c3d4e5f": rev_00002,
                    "00003c3d4e5f6a": rev_00003,
                    "00004d4e5f6a7b": common_ancestor,
                    "1000f3e4d5c6b7": branch_a1,
                    "10008a9b0c1d2e": branch_a2,
                    "2000e7f8a9b4c5": branch_b1,
                    "20003d6e7f8a9b": branch_b2,
                }
                return revisions.get(rev_id)

            mock_script_instance.get_revision.side_effect = mock_get_revision

            # Mock config to return a valid DB URL
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://user:pass@localhost/testdb"
            )

            with patch("alembic_rebase.Config") as mock_config:
                mock_config.return_value = mock_config_instance
                rebase = AlembicRebase(str(alembic_ini))

            # Test that we find the most recent common ancestor, not the first revision
            ancestor = rebase._find_common_ancestor("10008a9b0c1d2e", "20003d6e7f8a9b")
            assert (
                ancestor == "00004d4e5f6a7b"
            )  # Should be the common ancestor, not 00001a1b2c3d4e

            # Test with reversed order
            ancestor = rebase._find_common_ancestor("20003d6e7f8a9b", "10008a9b0c1d2e")
            assert ancestor == "00004d4e5f6a7b"  # Should be the same common ancestor

    def test_validate_revisions_error_cases(self, temp_alembic_env):
        """Test validation error cases."""
        _temp_dir, alembic_ini = temp_alembic_env

        with (
            patch("alembic_rebase.Config") as mock_config,
            patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
            patch.object(
                AlembicRebase, "_get_current_heads_from_files"
            ) as mock_get_heads,
            patch.object(AlembicRebase, "_find_migration_file") as mock_find_file,
        ):
            mock_config.return_value = MagicMock()
            mock_script_dir.from_config.return_value = MagicMock()

            # Mock config to return a valid DB URL
            mock_config_instance = MagicMock()
            mock_config_instance.get_main_option.return_value = (
                "postgresql://user:pass@localhost/testdb"
            )
            mock_config.return_value = mock_config_instance

            rebase = AlembicRebase(str(alembic_ini))

            # Test with same revision
            mock_get_heads.return_value = ["1000a1b2c3d4e5"]
            mock_find_file.return_value = MagicMock()  # Mock file exists
            with pytest.raises(AlembicRebaseError, match="cannot be the same"):
                rebase._validate_revisions("1000a1b2c3d4e5", "1000a1b2c3d4e5")

            # Test with nonexistent migration file
            mock_find_file.return_value = None  # Mock file doesn't exist
            with pytest.raises(
                AlembicRebaseError, match="does not exist in migration files"
            ):
                rebase._validate_revisions("nonexistent1", "nonexistent2")

            # Test with no current heads
            mock_get_heads.return_value = []
            mock_find_file.return_value = MagicMock()  # Mock file exists
            with pytest.raises(AlembicRebaseError, match="No current heads found"):
                rebase._validate_revisions("revision1", "revision2")

    def test_db_url_conversion(self, temp_alembic_env):
        """Test database URL conversion to async format during initialization."""
        _temp_dir, alembic_ini = temp_alembic_env

        test_cases = [
            (
                "postgresql://user:pass@host/db",
                "postgresql+asyncpg://user:pass@host/db",
            ),
            (
                "postgresql+psycopg2://user:pass@host/db",
                "postgresql+asyncpg://user:pass@host/db",
            ),
            (
                "postgresql+asyncpg://user:pass@host/db",
                "postgresql+asyncpg://user:pass@host/db",
            ),
        ]

        for input_url, expected_output in test_cases:
            with (
                patch("alembic_rebase.Config") as mock_config,
                patch("alembic_rebase.ScriptDirectory") as mock_script_dir,
            ):
                mock_config_instance = MagicMock()
                mock_config_instance.get_main_option.return_value = input_url
                mock_config.return_value = mock_config_instance
                mock_script_dir.from_config.return_value = MagicMock()

                rebase = AlembicRebase(str(alembic_ini))
                assert rebase.db_url == expected_output


def test_main_cli_args():
    """Test command line argument parsing."""
    import argparse

    # Test basic argument parsing
    parser = argparse.ArgumentParser()
    parser.add_argument("base_head")
    parser.add_argument("top_head")
    parser.add_argument("-f", "--config", default="alembic.ini")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--show-heads", action="store_true")

    args = parser.parse_args(["1000a1b2c3d4e5", "2000f6e7d8c9ba"])
    assert args.base_head == "1000a1b2c3d4e5"
    assert args.top_head == "2000f6e7d8c9ba"
    assert args.config == "alembic.ini"
    assert not args.verbose

    args = parser.parse_args([
        "1000a1b2c3d4e5",
        "2000f6e7d8c9ba",
        "--config",
        "custom.ini",
        "-v",
    ])
    assert args.base_head == "1000a1b2c3d4e5"
    assert args.top_head == "2000f6e7d8c9ba"
    assert args.config == "custom.ini"
    assert args.verbose


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
