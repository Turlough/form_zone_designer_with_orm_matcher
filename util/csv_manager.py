import csv
import os
import logging
from fields import Field, RadioGroup
import json

from util.path_utils import (
    resolve_path_or_original,
    paths_equal_case_insensitive,
    find_file_case_insensitive,
)

logger = logging.getLogger(__name__)

class CSVManager:
    """Manages CSV file loading, header generation, and saving."""
    
    def __init__(self):
        self.csv_path = None
        self.csv_dir = None
        self.rows = []
        self.headers = []
        self.field_names = []  # Ordered list of field names from JSON files
    
    def load_csv(self, csv_path, json_folder):
        """Load CSV file and ensure it has proper structure."""
        self.csv_path = csv_path
        self.csv_dir = os.path.dirname(os.path.abspath(csv_path))
        
        # Read existing CSV
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            self.rows = list(reader)
        
        # Get field names from JSON files
        self.field_names = self._get_field_names_from_json(json_folder)

        # Build the expected header row from JSON field names
        # Always ensure a trailing "Comments" column exists for QC flags.
        expected_headers = ['tiff_path'] + self.field_names + ['Comments']

        # Check if headers exist
        if len(self.rows) == 0:
            # Empty file, add headers
            self.headers = expected_headers
            self.rows = [self.headers]
        else:
            # Check if first row looks like headers
            first_row = self.rows[0]
            if self._first_row_is_header(first_row, expected_headers):
                # First row is (or looks like) a header row.
                # Always normalise it to the expected headers generated from JSON.
                self.headers = expected_headers
                self.rows[0] = self.headers
            else:
                # No headers detected, insert them
                self.headers = expected_headers
                self.rows.insert(0, self.headers)
        
        # Ensure all rows have correct number of columns
        expected_cols = len(self.headers)
        for i, row in enumerate(self.rows):
            if len(row) < expected_cols:
                # Pad with empty strings
                self.rows[i] = row + [''] * (expected_cols - len(row))
            elif len(row) > expected_cols:
                # Truncate
                self.rows[i] = row[:expected_cols]
        
        logger.info(f"Loaded CSV with {len(self.rows)-1} data rows and {len(self.headers)} columns")
        return True

    def _first_row_is_header(self, first_row, expected_headers):
        """
        Determine whether the first row of the CSV is a header row.

        Primary test (per requirement):
        - Compare the first three items in the first row with the expected
          field names (including 'tiff_path' as the first column).

        Fallback for backward compatibility:
        - If the first cell is one of 'tiff_path', 'path', or 'file',
          treat it as a header row as well.
        """
        if not first_row:
            return False

        # Compare up to the first three cells against the expected header cells
        items_to_check = min(3, len(first_row), len(expected_headers))
        if items_to_check == 0:
            return False

        all_match_expected = all(
            first_row[i].strip().lower() == expected_headers[i].strip().lower()
            for i in range(items_to_check)
        )
        if all_match_expected:
            return True

        # Backward-compatibility: accept legacy header names in the first column
        first_cell = first_row[0].strip().lower()
        if first_cell in ('tiff_path', 'path', 'file'):
            return True

        return False
    
    def _get_field_names_from_json(self, json_folder):
        """Extract field names from all JSON files in order.
        Uses case-insensitive path resolution for JSON files."""
        field_names = []
        page_num = 1
        
        while True:
            json_path = find_file_case_insensitive(json_folder, f"{page_num}.json")
            if json_path is None:
                break
            
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                # Iterate through top-level elements
                for item in data:
                    field = Field.from_dict(item)
                    if isinstance(field, RadioGroup):
                        # RadioGroup gets one column
                        if field.name not in field_names:
                            field_names.append(field.name)
                    else:
                        # Regular field
                        if field.name not in field_names:
                            field_names.append(field.name)
                
            except Exception as e:
                logger.warning(f"Error reading {json_path!s}: {e}")
            
            page_num += 1
        
        return field_names
    
    def get_tiff_paths(self):
        """Return list of TIFF paths from CSV (excluding header)."""
        if len(self.rows) <= 1:
            return []
        return [row[0] for row in self.rows[1:] if row[0]]
    
    def get_row_index_for_tiff(self, tiff_path):
        """Get the row index (0-based, excluding header) for a given TIFF path.
        Uses case-insensitive path comparison."""
        for i, row in enumerate(self.rows[1:]):
            if paths_equal_case_insensitive(row[0], tiff_path):
                return i
        return -1
    
    def get_field_value(self, row_index, field_name):
        """Get value for a field in a specific row."""
        if field_name not in self.headers:
            return None
        
        col_index = self.headers.index(field_name)
        actual_row = row_index + 1  # Skip header
        
        if actual_row >= len(self.rows):
            return None
        
        return self.rows[actual_row][col_index]
    
    def set_field_value(self, row_index, field_name, value):
        """Set value for a field in a specific row."""
        if field_name not in self.headers:
            logger.warning(f"Field {field_name} not in headers")
            return False
        
        col_index = self.headers.index(field_name)
        actual_row = row_index + 1  # Skip header
        
        if actual_row >= len(self.rows):
            return False
        
        self.rows[actual_row][col_index] = str(value)
        return True
    
    def save_csv(self):
        """Save CSV file back to disk."""
        if not self.csv_path:
            return False
        
        try:
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(self.rows)
            logger.info(f"Saved CSV to {self.csv_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving CSV: {e}")
            return False
    
    def get_absolute_tiff_path(self, relative_path):
        """Convert relative TIFF path to absolute path.
        Resolves case-insensitively so paths work across different filesystems.
        Normalizes path separators so CSV paths from Windows (\\) work on Linux (/) and vice versa."""
        # Normalize separators: CSV may contain Windows (\) or Unix (/) paths
        normalized = relative_path.replace("\\", os.sep).replace("/", os.sep)
        if os.path.isabs(normalized):
            full_path = normalized
        else:
            full_path = os.path.join(self.csv_dir, normalized)
        resolved = resolve_path_or_original(full_path)
        return str(resolved)
