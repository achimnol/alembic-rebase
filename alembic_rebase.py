#!/usr/bin/env python3
"""Standalone script to rebase alembic migrations when heads are diverged.

This script allows you to rebase one migration branch onto another when
working with diverged alembic heads in a git repository.

The rebasing process follows the 4-phase approach described in SPEC.md:
1. Analysis and Validation
2. Downgrade to Common Ancestor
3. History Rewriting
4. Apply Linearized History
"""

import argparse
import asyncio
import configparser
import logging
import re
import sys
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
    """Main class for handling alembic migration rebasing.

    This class implements the 4-phase rebasing algorithm described in SPEC.md:
    - Phase 1: Analysis and Validation (configuration, revision validation, chain analysis)
    - Phase 2: Downgrade to Common Ancestor
    - Phase 3: History Rewriting (file modification with integrity validation)
    - Phase 4: Apply Linearized History
    """

    def __init__(self, alembic_ini_path: str | None = None) -> None:
        self.alembic_ini_path = alembic_ini_path or "alembic.ini"
        self.config: Config | None = None
        self.script_dir: ScriptDirectory | None = None
        self.db_url: str | None = None
        self.script_location: str | None = None

    def _load_alembic_config(self) -> None:
        """Load alembic configuration from alembic.ini file.

        Part of Phase 1: Analysis and Validation.
        Parses alembic.ini to extract script_location and sqlalchemy.url,
        converts database URL to async format, and initializes alembic objects.
        """
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

    async def _validate_revisions(self, top_head: str, base_head: str) -> None:
        """Validate that the provided revision IDs exist and are actually heads.

        Part of Phase 1: Analysis and Validation.
        Ensures both top_head and base_head are solely current database heads
        and that they are different revisions.
        """
        current_heads = await self._get_current_heads()

        if top_head not in current_heads:
            raise AlembicRebaseError(
                f"Top head '{top_head}' is not a current head. Current heads: {current_heads}"
            )

        if base_head not in current_heads:
            raise AlembicRebaseError(
                f"Base head '{base_head}' is not a current head. Current heads: {current_heads}"
            )

        if top_head == base_head:
            raise AlembicRebaseError("Top head and base head cannot be the same")

    def _get_migration_chain(self, revision: str) -> list[str]:
        """Get the chain of migrations leading to a specific revision.

        Part of Phase 1: Analysis and Validation.
        Builds migration chains by following down_revision links from the given
        revision back to the root, then returns the chain in chronological order.
        """
        assert self.script_dir is not None, "Script directory not initialized"
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

    def _find_common_ancestor(self, top_head: str, base_head: str) -> str | None:
        """Find the common ancestor of two migration heads.

        Part of Phase 1: Analysis and Validation.
        Identifies the last migration that both branches share by comparing
        their migration chains.
        """
        top_chain = set(self._get_migration_chain(top_head))
        base_chain = self._get_migration_chain(base_head)

        for revision in base_chain:
            if revision in top_chain:
                return revision

        return None

    def _find_migration_file(self, revision: str) -> Path | None:
        """Find the migration file for a given revision."""
        # Resolve script location relative to alembic.ini directory
        assert self.script_location is not None, "Script location not initialized"
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

        # Write updated content back to the same file (revision ID unchanged)
        file_path.write_text(content)

        logger.info(f"Updated migration file linkage: {file_path.name}")

    def _rewrite_migration_files(
        self, migrations_to_rebase: list[str], last_top_migration: str
    ) -> None:
        """Update migration files to reflect new parent relationships after rebase.

        Part of Phase 3: History Rewriting.
        Modifies migration files to reflect the new linearized revision history
        by updating down_revision fields while preserving all other content.
        """
        logger.info("Updating migration file linkage for rebase...")

        # Update migration files (keeping original revision IDs)
        for i, revision in enumerate(migrations_to_rebase):
            file_path = self._find_migration_file(revision)
            if not file_path:
                raise AlembicRebaseError(
                    f"Could not find migration file for revision {revision}"
                )

            # Determine new down_revision
            if i == 0:
                # First migration in rebase should point to last_top_migration
                new_down_revision = last_top_migration
            else:
                # Subsequent migrations point to previous migration in the rebased chain
                new_down_revision = migrations_to_rebase[i - 1]

            # Update only the down_revision, keep original revision ID
            self._update_migration_file(
                file_path, revision, revision, new_down_revision
            )

    def _validate_migration_file_integrity(self, revision: str) -> bool:
        """Validate that a migration file has proper structure and syntax.

        Part of Phase 3: History Rewriting - Integrity Validation.
        Validates Python syntax and ensures all required alembic elements are present.
        """
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
        """Validate that the migration chain has proper linkage.

        Part of Phase 3: History Rewriting - Integrity Validation.
        Verifies migration chain linkage is correct and there is only a single
        head revision in the history.
        """
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
        """Downgrade database to a specific revision.

        Part of Phase 2: Downgrade to Common Ancestor.
        Uses alembic to downgrade database to the common ancestor revision,
        removing all migrations from both diverged branches.
        """
        logger.info(f"Downgrading to revision: {revision}")

        # Use sync engine for alembic commands
        assert self.db_url is not None, "Database URL not initialized"
        assert self.config is not None, "Config not initialized"
        sync_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.config.set_main_option("sqlalchemy.url", sync_url)

        command.downgrade(self.config, revision)

    async def _upgrade_to_head(self, head: str) -> None:
        """Upgrade database to a specific head.

        Part of Phase 4: Apply Linearized History.
        Runs the regular alembic upgrade procedure using the new history chain.
        """
        logger.info(f"Upgrading to head: {head}")

        # Use sync engine for alembic commands
        assert self.db_url is not None, "Database URL not initialized"
        assert self.config is not None, "Config not initialized"
        sync_url = self.db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        self.config.set_main_option("sqlalchemy.url", sync_url)

        command.upgrade(self.config, head)

    async def rebase(self, base_head: str, top_head: str) -> None:
        """Rebase migrations by putting base_head below top_head in history.

        The rebasing process consists of four main phases:
        1. Analysis and Validation
        2. Downgrade to Common Ancestor
        3. History Rewriting
        4. Apply Linearized History

        Args:
            base_head: The revision that will be moved below top_head
            top_head: The revision that will remain at the top

        """
        logger.info(f"Starting rebase: base_head={base_head}, top_head={top_head}")

        # === Phase 1: Analysis and Validation ===
        logger.info("Phase 1: Analysis and Validation")

        # Configuration Loading
        self._load_alembic_config()

        # Revision Validation
        await self._validate_revisions(top_head, base_head)

        # Chain Analysis
        common_ancestor = self._find_common_ancestor(top_head, base_head)
        if not common_ancestor:
            raise AlembicRebaseError("No common ancestor found between the two heads")

        logger.info(f"Common ancestor: {common_ancestor}")

        # Get the migrations to rebase (from base_head back to common ancestor)
        base_chain = self._get_migration_chain(base_head)
        top_chain = self._get_migration_chain(top_head)

        # Find where the base chain diverged from top
        common_index = None
        for i, rev in enumerate(base_chain):
            if rev == common_ancestor:
                common_index = i
                break

        if common_index is None:
            raise AlembicRebaseError("Could not find common ancestor in base chain")

        migrations_to_rebase = base_chain[common_index + 1 :]
        logger.info(f"Migrations to rebase: {migrations_to_rebase}")

        # === Phase 2: Downgrade to Common Ancestor ===
        logger.info("Phase 2: Downgrade to Common Ancestor")
        await self._downgrade_to_revision(common_ancestor)

        # === Phase 3: History Rewriting ===
        logger.info("Phase 3: History Rewriting")

        # Find the rebasing point
        # Get the revision ID of the last migration in the top_head chain after the common ancestor
        top_chain_after_ancestor = [rev for rev in top_chain if rev != common_ancestor]
        if not top_chain_after_ancestor:
            raise AlembicRebaseError(
                "No migrations found in top chain after common ancestor"
            )

        # Get the last migration in the top chain after the common ancestor
        last_top_migration = top_chain_after_ancestor[-1]

        # File Rewriting - update migration file linkage for rebase
        self._rewrite_migration_files(migrations_to_rebase, last_top_migration)

        # Integrity Validation
        logger.info("Validating migration file integrity after rebase...")
        for revision in migrations_to_rebase:
            if not self._validate_migration_file_integrity(revision):
                raise AlembicRebaseError(
                    f"Migration file integrity validation failed for {revision}"
                )

        # Validate migration chain integrity (with updated linkage)
        if not self._validate_migration_chain_integrity(migrations_to_rebase):
            raise AlembicRebaseError("Migration chain integrity validation failed")

        logger.info("Migration file integrity validation passed")

        # === Phase 4: Apply Linearized History ===
        logger.info("Phase 4: Apply Linearized History")

        # Apply rebased migrations - first upgrade to top_head, then apply rebased migrations
        await self._upgrade_to_head(top_head)

        # Apply rebased migrations using original revision IDs
        for revision in migrations_to_rebase:
            await self._upgrade_to_head(revision)

        logger.info("Rebase completed successfully!")


async def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Rebase alembic migrations when heads are diverged",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 1000a1b2c3d4e5 2000f6e7d8c9ba
  %(prog)s -f ./configs/alembic.ini 1000a1b2c3d4e5 2000f6e7d8c9ba
  %(prog)s --config ./configs/alembic.ini 1000a1b2c3d4e5 2000f6e7d8c9ba
        """,
    )

    parser.add_argument(
        "base_head", help="The revision ID that will be moved below the top head"
    )

    parser.add_argument(
        "top_head", help="The revision ID that will remain at the top of the history"
    )

    parser.add_argument(
        "-f",
        "--config",
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
        rebase = AlembicRebase(args.config)
        await rebase.rebase(args.base_head, args.top_head)
    except AlembicRebaseError as e:
        logger.error(f"Rebase failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
