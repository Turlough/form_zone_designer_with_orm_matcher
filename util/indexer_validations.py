
def is_empty(value: str) -> bool:
    return value is None or value.strip() == ""

def is_not_integer(value: str) -> bool:
    return value is not None and value.strip() != "" and not value.isdigit()

def is_not_decimal(value: str) -> bool:
    return value is not None and value.strip() != "" and not value.replace(".", "", 1).isdigit()


class Validator:
    tests: list[callable]
    def __init__(self, field_type: type):
        self.field_type = field_type

    def is_valid(self, field_name: str, value: any) -> bool:
        for test in self.tests:
            if test(value):
                return False
        return True

class TextValidator(Validator):
    def __init__(self):
        super().__init__(str)
        self.tests = [is_empty]

class IntegerValidator(Validator):
    def __init__(self):
        super().__init__(int)
        self.tests = [is_empty, is_not_integer]

class DecimalValidator(Validator):
    def __init__(self):
        super().__init__(float)
        self.tests = [is_empty, is_not_decimal]

