import os
from pathlib import Path
import logging

from util.path_utils import find_project_template, PROJECT_TEMPLATE_FILENAMES

logger = logging.getLogger(__name__)

class DesignerConfig:
 
    def __init__(self, config_folder: Path):
        
        self.config_folder = config_folder
        self.json_folder = config_folder / 'json'
        self.fiducials_folder = config_folder / 'fiducials'
        self.qc_comments = config_folder / 'qc_comments.txt'

        self.json_folder.mkdir(parents=True, exist_ok=True)
        self.fiducials_folder.mkdir(parents=True, exist_ok=True)

        template_found = find_project_template(config_folder)
        if template_found is None:
            expected = ", ".join(PROJECT_TEMPLATE_FILENAMES)
            self.template_path = config_folder / "template.tif"
            logger.error("Template file not found in %s (expected one of: %s)", config_folder, expected)
            raise FileNotFoundError(
                f"Template file not found in {config_folder}. Expected one of: {expected}"
            )
        self.template_path = template_found

        logger.info(f"Initialized DesignerConfig with config folder: {config_folder}")

    