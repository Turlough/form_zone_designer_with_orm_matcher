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


class TestSumShouldEqualTotal(unittest.TestCase):
    def test_matching_sum_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "10", "a": "4", "b": "6"},
            field_names=["total", "a", "b"],
            params={},
            field_to_page={"total": 1, "a": 1, "b": 1},
        )
        self.assertEqual(fn(ctx), [])

    def test_blank_total_and_blank_parts_no_failure(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "", "a": "", "b": None},
            field_names=["total", "a", "b"],
            params={},
            field_to_page={"total": 1, "a": 1, "b": 2},
        )
        self.assertEqual(fn(ctx), [])

    def test_blank_total_with_valued_parts_fails_on_total_page(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "  ", "a": "3", "b": "2"},
            field_names=["total", "a", "b"],
            params={},
            field_to_page={"total": 1, "a": 2, "b": 3},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[0][1], "total")
        self.assertIn("5.0", result[0][2])
        self.assertIn("0.0", result[0][2])

    def test_mismatch_fails_on_total(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "10", "a": "4", "b": "5"},
            field_names=["total", "a", "b"],
            params={},
            field_to_page={"total": 2, "a": 1, "b": 1},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 2)
        self.assertEqual(result[0][1], "total")

    def test_non_numeric_part_is_fault_and_does_not_hide_blank_total(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "", "a": "abc", "b": "4"},
            field_names=["total", "a", "b"],
            params={},
            field_to_page={"total": 1, "a": 2, "b": 2},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][1], "a")
        self.assertIn("not a valid number", result[0][2])
        self.assertEqual(result[1][1], "total")
        self.assertIn("4.0", result[1][2])

    def test_invalid_total_returns_only_total_fault(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["sum_should_equal_total"]
        ctx = _ctx(
            field_values={"total": "n/a", "a": "1"},
            field_names=["total", "a"],
            params={},
            field_to_page={"total": 1, "a": 1},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "total")
        self.assertIn("not a valid number", result[0][2])


class TestTotalPerUnitInRange(unittest.TestCase):
    def test_milk_example_passes(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"cow_count": "100", "total_litres": "500000"},
            field_names=["cow_count", "total_litres"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
        )
        self.assertEqual(fn(ctx), [])

    def test_at_bounds_passes(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"count": "100", "total": "400000"},
            field_names=["count", "total"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
        )
        self.assertEqual(fn(ctx), [])

    def test_non_integer_per_unit_still_passes(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"count": "100", "total": "450123"},
            field_names=["count", "total"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
        )
        self.assertEqual(fn(ctx), [])

    def test_total_out_of_range_fails_total_field(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"count": "100", "total": "300000"},
            field_names=["count", "total"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
            field_to_page={"total": 2},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 2)
        self.assertEqual(result[0][1], "total")
        self.assertIn("per unit", result[0][2])
        self.assertIn("400000", result[0][2])

    def test_blank_fields_skip(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"count": "", "total": "500000"},
            field_names=["count", "total"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
        )
        self.assertEqual(fn(ctx), [])

    def test_zero_count_fails_count_field(self) -> None:
        fn = PROJECT_VALIDATION_REGISTRY["total_per_unit_in_range"]
        ctx = _ctx(
            field_values={"count": "0", "total": "500000"},
            field_names=["count", "total"],
            params={"min_per_unit": 4000, "max_per_unit": 8000},
            field_to_page={"count": 3},
        )
        result = fn(ctx)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "count")
        self.assertIn("zero", result[0][2].lower())


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
