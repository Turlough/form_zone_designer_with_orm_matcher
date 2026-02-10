import unittest

from util.indexer_validations import TextValidator, IntegerValidator, DecimalValidator


class TestTextValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = TextValidator()

    def test_non_empty_string_is_valid(self) -> None:
        self.assertTrue(self.validator.is_valid("hello"))

    def test_empty_string_is_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid(""))

    def test_whitespace_only_string_is_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid("   "))

    def test_none_is_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid(None))


class TestIntegerValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = IntegerValidator()

    def test_valid_integer_string_is_valid(self) -> None:
        self.assertTrue(self.validator.is_valid("123"))
        self.assertTrue(self.validator.is_valid("0"))

    def test_invalid_integer_string_is_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid("123a"))
        self.assertFalse(self.validator.is_valid("12.3"))
        self.assertFalse(self.validator.is_valid("12,300"))
        self.assertFalse(self.validator.is_valid("abc"))

    def test_empty_or_none_are_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid(""))
        self.assertFalse(self.validator.is_valid(None))


class TestDecimalValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = DecimalValidator()

    def test_valid_decimal_strings_are_valid(self) -> None:
        # Integers should be accepted as decimals as well.
        self.assertTrue(self.validator.is_valid("123"))
        self.assertTrue(self.validator.is_valid("0"))
        self.assertTrue(self.validator.is_valid("12.3"))

    def test_invalid_decimal_strings_are_invalid(self) -> None:
        # Multiple decimal points or non-digit characters should fail.
        self.assertFalse(self.validator.is_valid("12.3.4"))
        self.assertFalse(self.validator.is_valid("abc"))
        self.assertFalse(self.validator.is_valid("12a3"))
        self.assertFalse(self.validator.is_valid("12,300"))

    def test_empty_or_none_are_invalid(self) -> None:
        self.assertFalse(self.validator.is_valid(""))
        self.assertFalse(self.validator.is_valid(None))


if __name__ == "__main__":
    unittest.main()

