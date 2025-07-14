#!/usr/bin/env python3
"""Standalone script to rebase alembic migrations when heads are diverged.

This script allows you to rebase one migration branch onto another when
working with diverged alembic heads in a git repository.
"""

import argparse
import asyncio
import configparser
import logging
import re
import sys
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlembicRebaseError(Exception):
    """Custom exception for alembic rebase operations."""


class AlembicRebase:
    """Main class for handling alembic migration rebasing."""

    def __init__(self, alembic_ini_path: str | None = None):
        self.alembic_ini_path = alembic_ini_path or "alembic.ini"
        self.config = None
        self.script_dir = None
        self.db_url = None
        self.script_location = None
        self.revision_mapping: dict[str, str] = {}  # old_revision -> new_revision

    def _load_alembic_config(self) -> None:
        """Load alembic configuration from alembic.ini file."""
        if not Path(self.alembic_ini_path).exists():
            raise AlembicRebaseError(
                f"Alembic config file not found: {self.alembic_ini_path}"
            )

        # Parse the INI file
        config_parser = configparser.ConfigParser()
        config_parser.read(self.alembic_ini_path)

        # Get script location
        if "alembic" not in config_parser:
            raise AlembicRebaseError("No [alembic] section found in config file")

        self.script_location = config_parser.get(
            "alembic", "script_location", fallback=None
        )
        if not self.script_location:
            raise AlembicRebaseError("script_location not found in alembic config")

        # Get database URL
        self.db_url = config_parser.get("alembic", "sqlalchemy.url", fallback=None)
        if not self.db_url:
            raise AlembicRebaseError("sqlalchemy.url not found in alembic config")

        # Convert sync postgres URL to async if needed
        if self.db_url.startswith("postgresql://"):
            self.db_url = self.db_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        elif self.db_url.startswith("postgresql+psycopg2://"):
            self.db_url = self.db_url.replace(
                "postgresql+psycopg2://", "postgresql+asyncpg://", 1
            )

        # Initialize alembic config
        self.config = Config(self.alembic_ini_path)
        self.script_dir = ScriptDirectory.from_config(self.config)

        logger.info(f"Loaded alembic config from {self.alembic_ini_path}")
        logger.info(f"Script location: {self.script_location}")
        logger.info(f"Database URL: {self.db_url.split('@')[0]}@***")

    async def _get_current_heads(self) -> list[str]:
        """Get current heads from the database."""
        engine = create_async_engine(self.db_url)
        async with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            current_heads = context.get_current_heads()
        await engine.dispose()
        return list(current_heads)

    async def _validate_revisions(self, target_head: str, base_head: str) -> None:
        """Validate that the provided revision IDs exist and are actually heads."""
        current_heads = await self._get_current_heads()

        if target_head not in current_heads:
            raise AlembicRebaseError(
                f"Target head '{target_head}' is not a current head. Current heads: {current_heads}"
            )

        if base_head not in current_heads:
            raise AlembicRebaseError(
                f"Base head '{base_head}' is not a current head. Current heads: {current_heads}"
            )

        if target_head == base_head:
            raise AlembicRebaseError("Target head and base head cannot be the same")

    def _get_migration_chain(self, revision: str) -> list[str]:
        """Get the chain of migrations leading to a specific revision."""
        script = self.script_dir.get_revision(revision)
        chain = []

        while script:
            chain.append(script.revision)
            if script.down_revision:
                if isinstance(script.down_revision, (list, tuple)):
                    # Handle merge points - take the first parent for simplicity
                    script = self.script_dir.get_revision(script.down_revision[0])
                else:
                    script = self.script_dir.get_revision(script.down_revision)
            else:
                break

        return list(reversed(chain))

    def _find_common_ancestor(self, target_head: str, base_head: str) -> str | None:
        """Find the common ancestor of two migration heads."""
        target_chain = set(self._get_migration_chain(target_head))
        base_chain = self._get_migration_chain(base_head)

        for revision in base_chain:
            if revision in target_chain:
                return revision

        return None

    def _generate_new_revision_id(self) -> str:
        """Generate a new revision ID."""
        return str(uuid.uuid4()).replace("-", "")[:12]

    def _find_migration_file(self, revision: str) -> Path | None:
        """Find the migration file for a given revision."""
        # Resolve script location relative to alembic.ini directory
        ini_dir = Path(self.alembic_ini_path).parent
        script_location = ini_dir / self.script_location
        versions_dir = script_location / "versions"

        if not versions_dir.exists():
            logger.debug(f"Versions directory does not exist: {versions_dir}")
            return None

        # First try to find by revision in filename
        for file_path in versions_dir.glob("*.py"):
            if revision in file_path.name:
                return file_path

        # If not found by filename, search within file content for exact revision match
        for file_path in versions_dir.glob("*.py"):
            try:
                content = file_path.read_text()
                # Use regex to match exact revision assignment
                revision_pattern = rf"^revision\s*=\s*['\"]({re.escape(revision)})['\"]"
                if re.search(revision_pattern, content, re.MULTILINE):
                    return file_path
            except Exception:
                continue

        return None

    def _parse_migration_file(self, file_path: Path) -> tuple[str, str | None, str]:
        """Parse migration file to extract revision, down_revision, and content."""
        content = file_path.read_text()

        # Extract revision ID
        revision_match = re.search(
            r"^revision\s*=\s*['\"]([^'\"]+)['\"]", content, re.MULTILINE
        )
        if not revision_match:
            raise AlembicRebaseError(f"Could not find revision in {file_path}")
        revision = revision_match.group(1)

        # Extract down_revision
        down_revision_match = re.search(
            r"^down_revision\s*=\s*(['\"]([^'\"]*)['\"]|None)", content, re.MULTILINE
        )
        down_revision = None
        if down_revision_match and down_revision_match.group(1) != "None":
            down_revision = down_revision_match.group(2)

        return revision, down_revision, content

    def _update_migration_file(
        self,
        file_path: Path,
        old_revision: str,
        new_revision: str,
        new_down_revision: str | None,
    ) -> None:
        """Update migration file with new revision IDs."""
        content = file_path.read_text()

        # Update revision
        content = re.sub(
            r"^revision\s*=\s*['\"]([^'\"]+)['\"]",
            f"revision = '{new_revision}'",
            content,
            flags=re.MULTILINE,
        )

        # Update down_revision
        if new_down_revision:
            content = re.sub(
                r"^down_revision\s*=\s*(['\"]([^'\"]*)['\"]|None)",
                f"down_revision = '{new_down_revision}'",
                content,
                flags=re.MULTILINE,
            )
        else:
            content = re.sub(
                r"^down_revision\s*=\s*(['\"]([^'\"]*)['\"]|None)",
                "down_revision = None",
                content,
                flags=re.MULTILINE,
            )

        # Update filename to reflect new revision
        new_filename = file_path.name.replace(old_revision, new_revision)
        new_path = file_path.parent / new_filename

        # Write updated content to new file
        new_path.write_text(content)

        # Remove old file if different
        if new_path != file_path:
            file_path.unlink()

        logger.info(f"Updated migration file: {file_path} -> {new_path}")

    def _rewrite_migration_files(
        self, migrations_to_rebase: list[str], target_head: str
    ) -> None:
        """Rewrite migration files with new revision IDs to reflect rebase."""
        logger.info("Rewriting migration files for rebase...")

        # Create new revision IDs for migrations to rebase
        for migration in migrations_to_rebase:
            new_revision = self._generate_new_revision_id()
            self.revision_mapping[migration] = new_revision
            logger.info(f"Mapping {migration} -> {new_revision}")

        # Update migration files
        for i, old_revision in enumerate(migrations_to_rebase):
            file_path = self._find_migration_file(old_revision)
            if not file_path:
                raise AlembicRebaseError(
                    f"Could not find migration file for revision {old_revision}"
                )

            new_revision = self.revision_mapping[old_revision]

            # Determine new down_revision
            if i == 0:
                # First migration in rebase should point to target_head
                new_down_revision = target_head
            else:
                # Subsequent migrations point to previous rebased migration
                prev_old_revision = migrations_to_rebase[i - 1]
                new_down_revision = self.revision_mapping[prev_old_revision]

            self._update_migration_file(
                file_path, old_revision, new_revision, new_down_revision
            )

    def _validate_migration_file_integrity(self, revision: str) -> bool:
        """Validate that a migration file has proper structure and syntax."""
        file_path = self._find_migration_file(revision)
        if not file_path:
            return False

        try:
            content = file_path.read_text()

            # Check for required elements
            required_patterns = [
                r"^revision\s*=\s*['\"][^'\"]+['\"]",  # revision = 'xxx'
                r"^down_revision\s*=\s*(['\"][^'\"]*['\"]|None)",  # down_revision = 'xxx' or None
                r"def upgrade\(\)",  # upgrade function
                r"def downgrade\(\)",  # downgrade function
            ]

            for pattern in required_patterns:
                if not re.search(pattern, content, re.MULTILINE):
                    logger.error(
                        f"Migration file {file_path} missing required pattern: {pattern}"
                    )
                    return False

            # Try to compile the Python code
            compile(content, str(file_path), "exec")

            return True

        except Exception as e:
            logger.error(f"Migration file {file_path} validation failed: {e}")
            return False

    def _validate_migration_chain_integrity(self, migrations: list[str]) -> bool:
        """Validate that the migration chain has proper linkage."""
        for i, revision in enumerate(migrations):
            file_path = self._find_migration_file(revision)
            if not file_path:
                logger.error(f"Migration file not found for revision: {revision}")
                return False

            _, down_revision, _ = self._parse_migration_file(file_path)

            if i == 0:
                # First migration can have any down_revision
                continue
            # Subsequent migrations should point to previous migration
            expected_down_revision = migrations[i - 1]
            if down_revision != expected_down_revision:
                logger.error(
                    f"Migration chain broken: {revision} points to {down_revision}, expected {expected_down_revision}"
                )
                return False

        return True

    async def _downgrade_to_revision(self, revision: str) -> None:
        """Downgrade database to a specific revision."""
        logger.info(f"Downgrading to revision: {revision}")

        # Use sync engine for alembic commands
        sync_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.config.set_main_option("sqlalchemy.url", sync_url)

        command.downgrade(self.config, revision)

    async def _upgrade_to_head(self, head: str) -> None:
        """Upgrade database to a specific head."""
        logger.info(f"Upgrading to head: {head}")

        # Use sync engine for alembic commands
        sync_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.config.set_main_option("sqlalchemy.url", sync_url)

        command.upgrade(self.config, head)

    async def rebase(self, target_head: str, base_head: str) -> None:
        """Rebase migrations by putting base_head below target_head in history.

        Args:
            target_head: The revision that will remain at the top
            base_head: The revision that will be moved below target_head

        """
        logger.info(
            f"Starting rebase: target_head={target_head}, base_head={base_head}"
        )

        # Load configuration
        self._load_alembic_config()

        # Validate revisions
        await self._validate_revisions(target_head, base_head)

        # Find common ancestor
        common_ancestor = self._find_common_ancestor(target_head, base_head)
        if not common_ancestor:
            raise AlembicRebaseError("No common ancestor found between the two heads")

        logger.info(f"Common ancestor: {common_ancestor}")

        # Get the migrations to rebase (from base_head back to common ancestor)
        base_chain = self._get_migration_chain(base_head)
        self._get_migration_chain(target_head)

        # Find where the base chain diverged from target
        common_index = None
        for i, rev in enumerate(base_chain):
            if rev == common_ancestor:
                common_index = i
                break

        if common_index is None:
            raise AlembicRebaseError("Could not find common ancestor in base chain")

        migrations_to_rebase = base_chain[common_index + 1 :]
        logger.info(f"Migrations to rebase: {migrations_to_rebase}")

        # Step 1: Rewrite migration files with new revision IDs
        self._rewrite_migration_files(migrations_to_rebase, target_head)

        # Step 1.5: Validate migration file integrity after rewrite
        logger.info("Validating migration file integrity after rebase...")
        for old_revision in migrations_to_rebase:
            new_revision = self.revision_mapping[old_revision]
            if not self._validate_migration_file_integrity(new_revision):
                raise AlembicRebaseError(
                    f"Migration file integrity validation failed for {new_revision}"
                )

        # Validate migration chain integrity
        rebased_revisions = [self.revision_mapping[rev] for rev in migrations_to_rebase]
        if not self._validate_migration_chain_integrity(rebased_revisions):
            raise AlembicRebaseError("Migration chain integrity validation failed")

        logger.info("Migration file integrity validation passed")

        # Step 2: Downgrade to common ancestor
        await self._downgrade_to_revision(common_ancestor)

        # Step 3: Upgrade to target head
        await self._upgrade_to_head(target_head)

        # Step 4: Apply rebased migrations using new revision IDs
        for old_revision in migrations_to_rebase:
            new_revision = self.revision_mapping[old_revision]
            await self._upgrade_to_head(new_revision)

        logger.info("Rebase completed successfully!")


async def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Rebase alembic migrations when heads are diverged",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s abc123 def456
  %(prog)s --alembic-ini ./configs/alembic.ini abc123 def456
        """,
    )

    parser.add_argument(
        "target_head", help="The revision ID that will remain at the top of the history"
    )

    parser.add_argument(
        "base_head", help="The revision ID that will be moved below the target head"
    )

    parser.add_argument(
        "--alembic-ini",
        default="alembic.ini",
        help="Path to alembic.ini file (default: alembic.ini)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        rebase = AlembicRebase(args.alembic_ini)
        await rebase.rebase(args.target_head, args.base_head)
    except AlembicRebaseError as e:
        logger.error(f"Rebase failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
