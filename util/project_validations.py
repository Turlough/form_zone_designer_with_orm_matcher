import re
from pathlib import Path
import csv

################################################################################
# Single field validations
################################################################################
def is_valid_email(value: str) -> str | None:
    return "Invalid email address" if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", value) is not None else None


def is_valid_phone_number(value: str) -> str | None:
    return "Invalid phone number" if re.match(r"^\d{10}$", value) is not None else None

def is_valid_date(value: str) -> str | None:
    # Match dd/MM/yyyy
    return "Invalid date" if re.match(r"^\d{2}/\d{2}/\d{4}$", value) is None else None

################################################################################
# Lookup-list validations
################################################################################
# A CSV file contains a structured, comma-separated list of values.
# For example, "Herd number", "Owner name""
# We would validate that 1) The herd number exists. 2) The owner name exists, and corresponds to the herd number.

#TODO: Create a LookupManager class that can maintain both the current export CSV file and the lookup list CSV file,
# and provide helper functions

def value_exists_in_lookup_list(value: str, lookup_list: Path, column_index: int) -> str | None:
    """
    Check if the value exists in the lookup list.
    """
    with open(lookup_list, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[column_index] == value:
                return None
    return f"Value {value} not found in lookup list"
    
# Helper function to get the value of a field in the current export CSV file
def get_field_value(field_name: str, current_row: int, output_csv_file: Path) -> str | None:
    with open(output_csv_file, 'r') as f:
        reader = csv.reader(f)
        field_names = next(reader)
        column_index = field_names.index(field_name)
        actual_row = current_row + 1  # Skip header
        if actual_row >= len(reader):
            return None
        return reader[actual_row][column_index] 

def lookup_value(
value: str, # value of the current field
lookup_list: Path, # path to the lookup list CSV file
name_of_field_to_lookup: str, # The field name of the field whose value we are looking up
prime_column: int=1, # The column number in the lookup list that contains the current field's value
lookup_column=2, # The column number in the lookup list that contains the name
) -> str | None:
    """
    Look up the value of the current field in the lookup list.
    Find the row in the lookup list that contains the value of the current field.
    Check that the value of the field in the lookup column matches the value of the "name_of_field_to_lookup" field.
    """
    lookup_value = get_field_value(value, current_row, output_csv_file)# TODO: Fix this.  
    with open(lookup_list, 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[prime_column] == value:
                if row[lookup_column] != value:
                    return f"Looked up value does not match the Form's value of {name_of_field_to_lookup}"
                else:
                    return None
    return f"Value {value} not  found in lookup list"

