from typing import Any
import datetime

def contains_text(value: str) -> bool:
    return value is not None and value.strip() != ""

def is_integer(value: str) -> bool:
    if value is None or value.strip() == "":
        return False # is empty has already been tested
    else:
        return value.isdigit()

def is_decimal(value: str) -> bool:
    if value is  None or value.strip() == "":
        return False # is empty has already been tested
    else:
        return value.replace(".", "", 1).isdigit()

def is_date(value: str) -> bool:
    if value is None or value.strip() == "":
        return False # is empty has already been tested
    else:
        try:
            datetime.datetime.strptime(value, "d%/m%/yyyy")
            return True
        except ValueError:
            return False

class Validator:
    tests: list[callable]
    def __init__(self, field_type: type):
        self.field_type = field_type

    def is_valid(self, value: any) -> bool:
        responses = []
        for test in self.tests:
            if not test(value):
                return False
        return True

class TextValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [contains_text]

class IntegerValidator(Validator):
    def __init__(self):
        super().__init__(int)
        self.tests = [contains_text, is_integer]

class DecimalValidator(Validator):
    def __init__(self):
        super().__init__(float)
        self.tests = [contains_text, is_decimal]

class DateValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [contains_text, is_date]
