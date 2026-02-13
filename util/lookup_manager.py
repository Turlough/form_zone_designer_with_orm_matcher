from pathlib import Path
import csv
from typing import Self

class LookupManager:

    def __init__(self, lookup_list: Path, output_csv_file: Path, prime_index: int=0):
        self.lookup_list = lookup_list
        self.output_csv_file = output_csv_file
        self.prime_index = prime_index
        self.field_names = []
        self.indexed_rows = []
        self.lookup_dict = dict()
        self.current_row = 0
        self._load_lookup_list()
        self.load_output_csv()

    def _load_lookup_list(self):
        with open(self.lookup_list, 'r') as f:
            reader = csv.reader(f)
            next(reader) # Skip header
            for row in reader:
                self.lookup_dict[row[self.prime_index]] = row
    
    def load_output_csv(self) -> None:
        """Load (or reload) the output CSV from disk."""
        self.field_names = []
        self.indexed_rows = []
        with open(self.output_csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            self.field_names = next(reader)  # Skip header
            for row in reader:
                self.indexed_rows.append(row)

    def set_current_row(self, row: int) -> Self:
        '''Return prebuilt LookupManager object with the current row set.'''
        self.current_row = row
        return self

    def get_indexed_value(self, field_name: str) -> str | None:
        '''Get the value of a field in the current row of the output CSV file.
        Set the current row first!'''
        return self.indexed_rows[self.current_row][self.field_names.index(field_name)]
    
    def lookup_value(self, value: str | int, lookup_column: int) -> str | None:
        '''Lookup the value of a field in the lookup list, in the given column.
        value: the value to lookup
        lookup_column: the column in the lookup list to lookup
        Returns: None if not found, or the looked up value that was found (will be the same as the value passed in, of course)'''
        if value not in self.lookup_dict:
            return None
        return self.lookup_dict[value][lookup_column]

    def match_value(self, value: str | int, lookup_column: int, field_name: str) -> str | None:
        '''Match the value of a field in the lookup list, in the given column, with the value in the indexed field, field_name.
        value: the value to match
        lookup_column: the column in the lookup list to match
        field_name: the name of the field in the indexed field to match'''
        lookup_value = self.lookup_value(value, lookup_column).upper()
        indexed_value = self.get_indexed_value(field_name).upper()
        if lookup_value is None:
            return None
        if lookup_value != indexed_value:
            return f"Indexed value '{indexed_value}' does not match the value in the lookup list '{lookup_value}'"
        return None
