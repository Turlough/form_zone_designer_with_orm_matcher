import csv
import os
import logging
from fields import Field, RadioGroup
import json

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
        
        # Check if headers exist
        if len(self.rows) == 0:
            # Empty file, add headers
            self.headers = ['tiff_path'] + self.field_names
            self.rows = [self.headers]
        else:
            # Check if first row looks like headers
            first_row = self.rows[0]
            if first_row and first_row[0].lower() in ['tiff_path', 'path', 'file']:
                # Has headers
                self.headers = first_row
                # Update headers if field names changed
                if self.headers != ['tiff_path'] + self.field_names:
                    self.headers = ['tiff_path'] + self.field_names
                    self.rows[0] = self.headers
            else:
                # No headers, insert them
                self.headers = ['tiff_path'] + self.field_names
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
    
    def _get_field_names_from_json(self, json_folder):
        """Extract field names from all JSON files in order."""
        field_names = []
        page_num = 1
        
        while True:
            json_path = os.path.join(json_folder, f"{page_num}.json")
            if not os.path.exists(json_path):
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
                logger.warning(f"Error reading {json_path}: {e}")
            
            page_num += 1
        
        return field_names
    
    def get_tiff_paths(self):
        """Return list of TIFF paths from CSV (excluding header)."""
        if len(self.rows) <= 1:
            return []
        return [row[0] for row in self.rows[1:] if row[0]]
    
    def get_row_index_for_tiff(self, tiff_path):
        """Get the row index (0-based, excluding header) for a given TIFF path."""
        for i, row in enumerate(self.rows[1:]):
            if row[0] == tiff_path:
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
        """Convert relative TIFF path to absolute path."""
        if os.path.isabs(relative_path):
            return relative_path
        return os.path.join(self.csv_dir, relative_path)
