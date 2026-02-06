import os
from pathlib import Path
import logging

from util.path_utils import find_file_case_insensitive

logger = logging.getLogger(__name__)

class DesignerConfig:
 
    def __init__(self, config_folder: Path):
        
        self.config_folder = config_folder
        self.json_folder = config_folder / 'json'
        self.fiducials_folder = config_folder / 'fiducials'
        self.qc_comments = config_folder / 'qc_comments.txt'

        self.json_folder.mkdir(parents=True, exist_ok=True)
        self.fiducials_folder.mkdir(parents=True, exist_ok=True)

        # Resolve template case-insensitively (e.g. template.tif vs Template.TIF)
        template_found = find_file_case_insensitive(config_folder, 'template.tif')
        if template_found is None:
            self.template_path = config_folder / 'template.tif'
            logger.error(f"Template file not found: {self.template_path}")
            raise FileNotFoundError(f"Template file not found: {self.template_path}")
        self.template_path = template_found

        logger.info(f"Initialized DesignerConfig with config folder: {config_folder}")

    