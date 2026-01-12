import cv2

class ORMMatcher:
    def __init__(self, logo_path):
        self.load_logo(logo_path)
        self.top_left = None
        self.bottom_right = None
        self.best_val = None
        self.sample = None
    
    def load_logo(self, logo_path):
        """
        Load a logo image and convert it to grayscale for better matching.
        Do this once when the class is initialized; it will be used for all subsequent matches.
        The numpy array representing the logo is stored as self.logo.
        """
        logo = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
        # Convert to grayscale for better matching
        # Handle different image formats (grayscale, BGR, BGRA, etc.)
        if len(logo.shape) == 2:
            self.logo = logo
        elif len(logo.shape) == 3 and logo.shape[2] == 3:
            self.logo = cv2.cvtColor(logo, cv2.COLOR_BGR2GRAY)
        elif len(logo.shape) == 3 and logo.shape[2] == 4:
            self.logo = cv2.cvtColor(logo, cv2.COLOR_BGRA2GRAY)
        else:
            self.logo = logo

    def locate_from_image_path(self, image_path):
        """
        Detect a logo in an image file using template matching
        Args:
            image_path: Path to the image file
        """
        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        self.locate_from_cv2_image(image)


    def locate_from_cv2_image(self,  image):
        """
        Detect a logo in a numpy array representing an image using template matching
        It stores the results in self.top_left, self.bottom_right, self.best_val, and self.sample.
        Args:
            image: Numpy array representing an image
        """
        # Convert to grayscale for better matching
        # Handle different image formats (grayscale, BGR, BGRA, etc.)
        
        if len(image.shape) == 2:
            sample_gray = image
        elif len(image.shape) == 3 and image.shape[2] == 3:
            sample_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 3 and image.shape[2] == 4:
            sample_gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            sample_gray = image
        
        # Get template dimensions. Shape is the shape of the numpy array defining the image.
        h, w = self.logo.shape
        
        # Perform template matching using multiple methods for better results
        methods = [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]
        best_match = None
        best_val = -1
        
        for method in methods:
            result = cv2.matchTemplate(sample_gray, self.logo, method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            # For these methods, higher values are better matches
            if max_val > best_val:
                best_val = max_val
                best_match = max_loc
        
        # Draw rectangle around the detected logo
        self.top_left = best_match
        self.bottom_right = (self.top_left[0] + w, self.top_left[1] + h)
        self.best_val = best_val
        self.sample = image
        

