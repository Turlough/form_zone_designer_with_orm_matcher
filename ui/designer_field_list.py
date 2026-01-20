from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDropEvent
import json
import copy
import logging

logger = logging.getLogger(__name__)


class DesignerFieldList(QTableWidget):
    """
    A draggable table widget for displaying and reordering form fields.
    Shows field name and type, with special handling for RadioGroups.
    """
    
    # Emitted whenever the JSON text changes due to row reordering.
    # Payload is the raw JSON string.
    page_json_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Name", "Type"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAlternatingRowColors(True)
        
        # Store the full field data for each row (to reconstruct JSON)
        self._field_data_list = []
        
        # Flag to prevent JSON updates during programmatic table changes
        self._updating_table = False
        
        # Track the source row index when dragging starts
        self._drag_source_row = None
    
    def startDrag(self, supportedActions):
        """Override to capture the source row index before dragging begins."""
        # Get the currently selected row(s) - for drag, typically one row is selected
        selected_rows = self.selectedIndexes()
        if selected_rows:
            # Get the row index from the first selected item
            self._drag_source_row = selected_rows[0].row()
        else:
            self._drag_source_row = None
        
        # Call parent to handle the actual drag operation
        super().startDrag(supportedActions)
    
    def set_page_json(self, json_text: str):
        """Set the fields table from JSON text without emitting change signals."""
        logger.debug(f"set_page_json called with JSON length: {len(json_text) if json_text else 0}")
        # Set flag to prevent JSON updates during programmatic table population
        self._updating_table = True
        try:
            self._update_table_from_json(json_text)
        finally:
            self._updating_table = False
    
    def get_page_json(self) -> str:
        """Return the raw JSON text reconstructed from the table order."""
        return self._reconstruct_json_from_table()
    
    def _update_table_from_json(self, json_text: str):
        """Parse JSON and populate the table, filtering out RadioButtons."""
        self.setRowCount(0)
        self._field_data_list = []
        
        if not json_text or not json_text.strip():
            logger.debug("Empty JSON text provided to _update_table_from_json")
            return
        
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"JSON text was: {json_text[:200]}...")
            return
        
        if not isinstance(data, list):
            logger.warning(f"JSON data is not a list, got {type(data)}")
            return
        
        logger.debug(f"Parsed {len(data)} items from JSON")
        
        # Populate table (skip RadioButtons, show RadioGroups with count)
        rows_added = 0
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                logger.warning(f"Item at index {idx} is not a dict, got {type(item)}")
                continue
                
            field_type = item.get('_type', '')
            
            if not field_type:
                logger.warning(f"Item at index {idx} has no '_type' field. Keys: {list(item.keys())}")
                continue
            
            # Skip RadioButtons (they're shown as part of RadioGroup)
            if field_type == 'RadioButton':
                logger.debug(f"Skipping RadioButton at index {idx}")
                continue
            
            # Handle RadioGroup - show with button count
            if field_type == 'RadioGroup':
                radio_buttons = item.get('radio_buttons', [])
                button_count = len(radio_buttons)
                field_name = item.get('name', '')
                display_name = f"{field_name} ({button_count})" if button_count > 0 else field_name
            else:
                display_name = item.get('name', '')
            
            # Add row to table
            row = self.rowCount()
            self.insertRow(row)
            
            name_item = QTableWidgetItem(display_name or '')
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store the index into _field_data_list in the item's UserRole
            # This allows us to track which field data belongs to which row after drag/drop
            name_item.setData(Qt.ItemDataRole.UserRole, len(self._field_data_list))
            
            type_item = QTableWidgetItem(field_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            
            self.setItem(row, 0, name_item)
            self.setItem(row, 1, type_item)
            
            # Store the full field data for this row (deep copy to avoid reference issues)
            self._field_data_list.append(copy.deepcopy(item))
            rows_added += 1
        
        logger.debug(f"Added {rows_added} rows to table")
        
        # Resize columns to content and ensure table is updated
        self.resizeColumnsToContents()
        self.update()
        self.repaint()
    
    def _reconstruct_json_from_table(self) -> str:
        """Reconstruct JSON from the current table order."""
        if not self._field_data_list:
            return "[]"
        
        # _field_data_list is already in the correct order after drag/drop
        # Each item in _field_data_list contains the complete field data
        # (RadioGroups include their nested radio_buttons array)
        try:
            return json.dumps(self._field_data_list, indent=2, default=str)
        except TypeError:
            return "[]"
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop event to manually reorder rows with proper insertion behavior."""
        # Ignore if we're programmatically updating the table
        if self._updating_table:
            super().dropEvent(event)
            return
        
        # Get source and destination rows
        source_row = self._drag_source_row
        if source_row is None:
            # Fallback to default behavior if source wasn't tracked
            super().dropEvent(event)
            self._sync_field_data_from_table()
            json_text = self._reconstruct_json_from_table()
            self.page_json_changed.emit(json_text)
            return
        
        # Get the destination row from the drop position
        drop_position = event.position().toPoint()
        destination_row = self.indexAt(drop_position).row()
        
        # Handle drop at end of table (when destination_row is -1)
        if destination_row < 0:
            destination_row = self.rowCount()
        
        # Validate indices
        if not (0 <= source_row < self.rowCount()):
            logger.warning(f"Invalid source row {source_row}, ignoring drop")
            event.ignore()
            return
        
        if not (0 <= destination_row <= self.rowCount()):
            logger.warning(f"Invalid destination row {destination_row}, ignoring drop")
            event.ignore()
            return
        
        # If source == destination, no change needed
        if source_row == destination_row:
            event.accept()
            return
        
        # Accept the drop event but prevent default behavior
        event.accept()
        
        # Set flag to prevent recursive updates during manual reordering
        self._updating_table = True
        try:
            # Remove the source row from table and get its items
            source_name_item = self.takeItem(source_row, 0)
            source_type_item = self.takeItem(source_row, 1)
            self.removeRow(source_row)
            
            # Get the field data index from the source row's UserRole
            field_data_index = source_name_item.data(Qt.ItemDataRole.UserRole)
            if field_data_index is None or not (0 <= field_data_index < len(self._field_data_list)):
                logger.error(f"Invalid field_data_index {field_data_index} for source row {source_row}")
                self._updating_table = False
                return
            
            # Remove the field data from the list
            moved_field_data = self._field_data_list.pop(field_data_index)
            
            # Adjust destination if source was before it (after removal, indices shift)
            if source_row < destination_row:
                insert_position = destination_row - 1
            else:
                insert_position = destination_row
            
            # Insert the row at the new position
            self.insertRow(insert_position)
            self.setItem(insert_position, 0, source_name_item)
            self.setItem(insert_position, 1, source_type_item)
            
            # Insert the field data at the corresponding position
            self._field_data_list.insert(insert_position, moved_field_data)
            
            # Update all UserRole indices to match new positions
            for row in range(self.rowCount()):
                name_item = self.item(row, 0)
                if name_item:
                    name_item.setData(Qt.ItemDataRole.UserRole, row)
        
        finally:
            self._updating_table = False
        
        # Emit the updated JSON
        json_text = self._reconstruct_json_from_table()
        self.page_json_changed.emit(json_text)
    
    def _sync_field_data_from_table(self):
        """Synchronize _field_data_list with the current table row order."""
        # Reconstruct _field_data_list by reading the field data indices
        # stored in each row's name item UserRole, in the order they appear in the table
        new_field_data_list = []
        skipped_rows = []
        
        for row in range(self.rowCount()):
            name_item = self.item(row, 0)
            if name_item is None:
                logger.warning(f"Row {row} has no name item, skipping")
                skipped_rows.append(row)
                continue
                
            field_data_index = name_item.data(Qt.ItemDataRole.UserRole)
            if field_data_index is None:
                logger.warning(f"Row {row} name item has no UserRole data, skipping")
                skipped_rows.append(row)
                continue
                
            if not (0 <= field_data_index < len(self._field_data_list)):
                logger.warning(f"Row {row} has invalid field_data_index {field_data_index} (list length: {len(self._field_data_list)}), skipping")
                skipped_rows.append(row)
                continue
            
            # Copy the field data to the new list in the new order
            new_field_data_list.append(copy.deepcopy(self._field_data_list[field_data_index]))
            # Update the UserRole to reflect the new index in the new list
            name_item.setData(Qt.ItemDataRole.UserRole, len(new_field_data_list) - 1)
        
        if skipped_rows:
            logger.warning(f"Skipped {len(skipped_rows)} rows during field data sync: {skipped_rows}")
        
        # Replace the old list with the reordered one
        if len(new_field_data_list) != len(self._field_data_list):
            logger.warning(f"Field data list length changed: {len(self._field_data_list)} -> {len(new_field_data_list)}")
        
        self._field_data_list = new_field_data_list
    
