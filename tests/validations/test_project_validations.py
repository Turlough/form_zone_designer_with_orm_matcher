"""Unit tests for project-level validation strategies."""
import unittest
from pathlib import Path

from util.validation import (
    ValidationContext,
    ProjectValidations,
    PROJECT_VALIDATION_REGISTRY,
)


def _ctx(
    field_values: dict,
    field_names: list[str],
    params: dict,
    field_to_page: dict | None = None,
    lookup_manager=None,
    row_index: int = 0,
) -> ValidationContext:
    return ValidationContext(
        field_values=field_values,
        field_names=field_names,
        params=params,
        field_to_page=field_to_page or {},
        lookup_manager=lookup_manager,
        row_index=row_index,
    )


class TestMaxTickboxes(unittest.TestCase):
    def test_under_max_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["max_tickboxes"]
        ctx = _ctx(
            field_values={"a": "Ticked", "b": "", "c": "Ticked"},
            field_names=["a", "b", "c"],
            params={"max": 3},
        )
        self.assertEqual(fn(ctx), [])

    def test_at_max_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["max_tickboxes"]
        ctx = _ctx(
            field_values={"a": "Ticked", "b": "Ticked", "c": "Ticked"},
            field_names=["a", "b", "c"],
            params={"max": 3},
        )
        self.assertEqual(fn(ctx), [])

    def test_over_max_fails_last_ticked(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["max_tickboxes"]
        ctx = _ctx(
            field_values={"a": "Ticked", "b": "Ticked", "c": "Ticked", "d": "Ticked"},
            field_names=["a", "b", "c", "d"],
            params={"max": 2},
            field_to_page={"a": 1, "b": 1, "c": 1, "d": 1},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "d")
        self.assertIn("At most 2", result[0][2])


class TestMutuallyExclusive(unittest.TestCase):
    def test_exclusive_only_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["mutually_exclusive"]
        ctx = _ctx(
            field_values={"none": "Ticked", "a": "", "b": ""},
            field_names=["none", "a", "b"],
            params={"exclusive_field": "none"},
        )
        self.assertEqual(fn(ctx), [])

    def test_others_only_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["mutually_exclusive"]
        ctx = _ctx(
            field_values={"none": "", "a": "Ticked", "b": ""},
            field_names=["none", "a", "b"],
            params={"exclusive_field": "none"},
        )
        self.assertEqual(fn(ctx), [])

    def test_both_ticked_fails(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["mutually_exclusive"]
        ctx = _ctx(
            field_values={"none": "Ticked", "a": "Ticked", "b": ""},
            field_names=["none", "a", "b"],
            params={"exclusive_field": "none"},
            field_to_page={"none": 1},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "none")
        self.assertIn("mutually exclusive", result[0][2].lower())


class MockLookupManager:
    """Minimal mock for lookup_value tests."""

    def __init__(self, known_values: set[str]):
        self._known = known_values

    def lookup_value(self, value: str | int, lookup_column: int) -> str | None:
        return "ok" if str(value) in self._known else None


class TestValueExistsInLookup(unittest.TestCase):
    def test_no_lookup_manager_returns_empty(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["value_exists_in_lookup"]
        ctx = _ctx(
            field_values={"herd": "123"},
            field_names=["herd"],
            params={"lookup_column": 0},
            lookup_manager=None,
        )
        self.assertEqual(fn(ctx), [])

    def test_empty_value_returns_empty(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["value_exists_in_lookup"]
        ctx = _ctx(
            field_values={"herd": ""},
            field_names=["herd"],
            params={"lookup_column": 0},
            lookup_manager=None,
        )
        self.assertEqual(fn(ctx), [])

    def test_value_found_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["value_exists_in_lookup"]
        lm = MockLookupManager({"123"})
        ctx = _ctx(
            field_values={"herd": "123"},
            field_names=["herd"],
            params={"lookup_column": 0},
            lookup_manager=lm,
            field_to_page={"herd": 1},
        )
        self.assertEqual(fn(ctx), [])

    def test_value_not_found_returns_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["value_exists_in_lookup"]
        lm = MockLookupManager({"999"})
        ctx = _ctx(
            field_values={"herd": "123"},
            field_names=["herd"],
            params={"lookup_column": 0},
            lookup_manager=lm,
            field_to_page={"herd": 1},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "herd")
        self.assertIn("not found", result[0][2])


class TestProjectValidationsRunner(unittest.TestCase):
    """Test ProjectValidations.run_validations logic."""

    def test_run_validations_max_tickboxes_failure(self) -> None:
        config = {
            "validations": [
                {
                    "strategy": "max_tickboxes",
                    "field_names": ["a", "b", "c"],
                    "params": {"max": 1},
                },
            ],
        }
        pv = ProjectValidations(config, Path("/nonexistent/csv.csv"))
        field_values = {"a": "Ticked", "b": "Ticked", "c": ""}
        failures = pv.run_validations(0, field_values, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][1], "b")

    def test_run_validations_no_rules_empty(self) -> None:
        config = {"validations": []}
        pv = ProjectValidations(config, Path("/nonexistent/csv.csv"))
        failures = pv.run_validations(0, {}, None)
        self.assertEqual(failures, [])

    def test_run_validations_unknown_strategy_skipped(self) -> None:
        config = {
            "validations": [
                {"strategy": "nonexistent", "field_names": [], "params": {}},
            ],
        }
        pv = ProjectValidations(config, Path("/nonexistent/csv.csv"))
        failures = pv.run_validations(0, {}, None)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
