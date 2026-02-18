"""Project-level validations: config-driven business rules per project."""
import logging
from pathlib import Path
from typing import Any

from util.lookup_manager import LookupManager
from util.path_utils import resolve_path_or_original

from .strategies import PROJECT_VALIDATION_REGISTRY, ValidationContext

logger = logging.getLogger(__name__)


class ProjectValidations:
    """Validation service for a single batch. Created once when batch loads."""

    def __init__(self, project_config: dict, csv_path: Path, config_folder: str | None = None):
        self.project_config = project_config
        self.csv_path = csv_path
        self.validations = list(project_config.get("validations", []))

        lookup_path_str = project_config.get("lookup_list")
        if lookup_path_str:
            lookup_path = Path(str(lookup_path_str))
            if not lookup_path.is_absolute() and config_folder:
                lookup_path = Path(config_folder) / lookup_path
            resolved = resolve_path_or_original(str(lookup_path))
            if resolved and Path(resolved).exists():
                prime_index = project_config.get("lookup_prime_index", 0)
                try:
                    self.lookup_manager = LookupManager(
                        Path(resolved), csv_path, prime_index=prime_index
                    )
                except Exception as e:
                    logger.warning("Could not create LookupManager: %s", e)
                    self.lookup_manager = None
            else:
                self.lookup_manager = None
        else:
            self.lookup_manager = None

    def run_validations(
        self,
        row_index: int,
        field_values: dict[str, Any],
        field_to_page: dict[str, int] | None,
    ) -> list[tuple[int, str, str]]:
        """Run all project validations for one row."""
        if self.lookup_manager:
            self.lookup_manager.set_current_row(row_index)

        seen: set[tuple[int, str]] = set()
        all_failures: list[tuple[int, str, str]] = []

        for rule in self.validations:
            strategy_name = rule.get("strategy")
            if not strategy_name:
                continue

            fn = PROJECT_VALIDATION_REGISTRY.get(strategy_name)
            if fn is None:
                logger.warning("Unknown validation strategy: %s", strategy_name)
                continue

            ctx = ValidationContext(
                field_values=field_values,
                field_names=rule.get("field_names", []),
                params=rule.get("params", {}),
                field_to_page=field_to_page,
                lookup_manager=self.lookup_manager,
                row_index=row_index,
            )

            try:
                failures = fn(ctx)
                for page, field_name, message in failures:
                    key = (page, field_name)
                    if key not in seen:
                        seen.add(key)
                        all_failures.append((page, field_name, message))
            except Exception as e:
                logger.warning("Validation strategy %s failed: %s", strategy_name, e)

        return all_failures
