"""Project-level validations: config-driven business rules per project."""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from util.lookup_manager import LookupManager
from util.path_utils import resolve_path_or_original

logger = logging.getLogger(__name__)


@dataclass
class ValidationContext:
    """Everything a validation strategy might need. Built per row."""

    field_values: dict[str, Any]
    # This is used when multiple fields form a validation group, e.g. max_tickboxes or mutually_exclusive.
    # If only one field is provided, it is used as the prime field for lookup_value or match_value.
    field_names: list[str] | None
    params: dict
    field_to_page: dict[str, int] | None
    lookup_manager: LookupManager | None
    row_index: int

def __str__(self):
    return f"ValidationContext(field_values={self.field_values}, field_names={self.field_names}, params={self.params}, field_to_page={self.field_to_page}, lookup_manager={self.lookup_manager}, row_index={self.row_index})"
def __repr__(self):
    return self.__str__()


def _is_ticked(value: Any) -> bool:
    """Normalize tickbox semantics: non-empty string or 'Ticked'."""
    if value is None:
        return False
    s = str(value).strip()
    return s != "" and s.lower() != "false"


def _strategy_max_tickboxes(ctx: ValidationContext) -> list[tuple[int, str, str]]:
    """Count ticked fields; if > params['max'], invalidate last ticked field."""
    max_val = ctx.params.get("max", 1)
    ticked: list[tuple[str, int]] = []  # (field_name, page)

    for name in ctx.field_names:
        val = ctx.field_values.get(name)
        if _is_ticked(val):
            page = (ctx.field_to_page or {}).get(name, 1)
            ticked.append((name, page))

    if len(ticked) <= max_val:
        return []

    # Invalidate the last ticked field
    last_name, last_page = ticked[-1]
    return [
        (
            last_page,
            last_name,
            f"At most {max_val} of these may be ticked; {len(ticked)} are ticked.",
        )
    ]



def _strategy_mutually_exclusive(ctx: ValidationContext) -> list[tuple[int, str, str]]:
    """If exclusive_field is ticked and any other is ticked, invalidate exclusive_field."""
    exclusive = ctx.params.get("exclusive_field")
    if not exclusive:
        return []

    others = [n for n in ctx.field_names if n != exclusive]
    exclusive_ticked = _is_ticked(ctx.field_values.get(exclusive))
    any_other_ticked = any(_is_ticked(ctx.field_values.get(n)) for n in others)

    if not exclusive_ticked or not any_other_ticked:
        return []

    page = (ctx.field_to_page or {}).get(exclusive, 1)
    return [
        (
            page,
            exclusive,
            "This option is mutually exclusive with the others; do not tick both.",
        )
    ]


def _strategy_value_exists_in_lookup(ctx: ValidationContext) -> list[tuple[int, str, str]]:
    """Check that the value exists in the lookup list."""
    if ctx.lookup_manager is None:
        return []
    lookup_col = ctx.params.get("lookup_column", 0)

    # field_names[0] is the field whose value we look up
    if not ctx.field_names:
        return []

    field_name = ctx.field_names[0]
    value = ctx.field_values.get(field_name)
    if value is None or str(value).strip() == "":
        return []

    # LookupManager uses prime_index in __init__; we assume it matches
    lookup_val = ctx.lookup_manager.lookup_value(value, lookup_col)
    if lookup_val is None:
        page = (ctx.field_to_page or {}).get(field_name, 1)
        return [
            (
                page,
                field_name,
                f"Value {value!r} not found in lookup list.",
            )
        ]
    return []


def _strategy_match_value_in_lookup(ctx: ValidationContext) -> list[tuple[int, str, str]]:
    """Check that the looked-up value matches the indexed field value."""
    if ctx.lookup_manager is None:
        return []
    lookup_column = ctx.params.get("lookup_column", 0)

     # field_names[0] is the field whose value we look up
     # field_names[1] is the field whose value we match
    if not ctx.field_names or len(ctx.field_names) < 2:
        return []

    field_name = ctx.field_names[0]
    field_to_match = ctx.field_names[1]
    value = ctx.field_values.get(field_name)
    if value is None or str(value).strip() == "":
        return []

    lookup_value = ctx.field_values.get(field_to_match)
    if lookup_value is None or str(lookup_value).strip() == "":
        return []

    msg = ctx.lookup_manager.match_value(value, lookup_column, field_to_match)
    if msg is None:
        return []

    page = (ctx.field_to_page or {}).get(field_to_match, 1)
    return [(page, field_to_match, msg)]



def _strategy_numbers_nearly_equal(ctx: ValidationContext) -> list[tuple[int, str, str]]:
    """Check that the looked-up value matches the indexed field value."""
    if ctx.lookup_manager is None:
        return []

     # field_names[0] is the field whose value we look up
     # field_names[1] is the field whose value we match
    if not ctx.field_names or len(ctx.field_names) != 2:
        return []

    field1 = ctx.field_names[0]
    value1 = ctx.field_values.get(field1)
    field2 = ctx.field_names[1]
    value2 = ctx.field_values.get(field2)
    tolerance = ctx.params.get("tolerance", 0.01)

    try:
        value1 = float(value1)
        value2 = float(value2)
    except ValueError:
        return []
    upper_bound = value1 * (1 + tolerance)
    lower_bound = value1 * (1 - tolerance)
    if value2 >= lower_bound and value2 <= upper_bound:
        return []
    page1 = (ctx.field_to_page or {}).get(field1, 1) 
    page2 = (ctx.field_to_page or {}).get(field2, 1)
    msg = f"This number ({value1}) is not within {tolerance*100}% of '{field2.upper()}'s value ({value2})."
    if page1 != page2:
        msg += f" On page {page2}, '{field2.upper()}'s value is {value2}."
    fault1 = (page1, field1, msg)
    msg = f"This number ({value2}) is not within {tolerance*100}% of '{field1.upper()}'s value ({value1})."
    if page1 != page2:
        msg += f" On page {page1}, '{field1.upper()}'s value is {value1}."
    fault2 = (page2, field2, msg)
    return [fault1, fault2]


PROJECT_VALIDATION_REGISTRY: dict[str, Callable[[ValidationContext], list[tuple[int, str, str]]]] = {
    "max_tickboxes": _strategy_max_tickboxes,
    "mutually_exclusive": _strategy_mutually_exclusive,
    "value_exists_in_lookup": _strategy_value_exists_in_lookup,
    "match_value_in_lookup": _strategy_match_value_in_lookup,
    "numbers_nearly_equal": _strategy_numbers_nearly_equal,
}


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
