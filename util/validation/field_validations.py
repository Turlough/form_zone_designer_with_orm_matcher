from typing import Any
import datetime
import re
from util.validation.strategies import EIRCODE_REGEX

def contains_text(value: str) -> bool:
    return value is not None

def is_integer(value: str) -> bool:
    if value is None:
        return False # is empty has already been tested
    else:
        return value.isdigit()

def is_decimal(value: str) -> bool:
    if value is  None:
        return False # is empty has already been tested
    else:
        return value.replace(".", "", 1).isdigit()

def is_date(value: str) -> bool:
    if value is None:
        return False # is empty has already been tested
    else:
        try:
            datetime.datetime.strptime(value, "%d/%m/%Y")
            return True
        except ValueError:
            return False

def is_email(value: str) -> bool:
    if value is None:
        return False # is empty has already been tested
    else:
        return re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", value)

def is_irish_mobile(value: str) -> bool:
    if value is None:
        return False # is empty has already been tested
    else:
        return re.match(r"^08[356789]\d{7}$", value)

def is_eircode(value: str) -> bool:
    if value is None:
        return False # is empty has already been tested
    else:
        return re.match(EIRCODE_REGEX, str(value), re.IGNORECASE)

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

class EmailValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [contains_text, is_email]

class IrishMobileValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [contains_text, is_irish_mobile]

class EircodeValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [contains_text, is_eircode]