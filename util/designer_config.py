import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class DesignerConfig:
 
    def __init__(self, config_folder: Path):
        
        self.config_folder = config_folder
        self.template_path = config_folder / 'template.tif'
        self.json_folder = config_folder / 'json'
        self.fiducials_folder = config_folder / 'fiducials'

        self.json_folder.mkdir(parents=True, exist_ok=True)
        self.fiducials_folder.mkdir(parents=True, exist_ok=True)

        if not self.template_path.exists():
            logger.error(f"Template file not found: {self.template_path}")
            raise FileNotFoundError(f"Template file not found: {self.template_path}")

        logger.info(f"Initialized DesignerConfig with config folder: {config_folder}")

    