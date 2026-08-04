from .rectangle_detector import (
    detect_rectangles_multi_method as detect_rectangles,
    remove_inner_rectangles,
)
from .rectangle_detection_settings import (
    DEFAULT_RECTANGLE_DETECTION_SETTINGS,
    PARAM_TOOLTIPS,
    RectangleDetectionSettings,
)
from .designer_persistence import (
    load_page_fields,
    save_page_fields,
    load_rectangle_detection_settings,
    save_rectangle_detection_settings,
)
from .orm_matcher import ORMMatcher
from .designer_config import DesignerConfig
from .csv_manager import CSVManager
from .lookup_manager import LookupManager
from .validation import ProjectValidations
from .fiducial_paths import (
    DEFAULT_LOGO_CANDIDATES,
    find_default_logo,
    find_fiducial_for_page,
    per_page_logo_filename,
)