import cv2
import numpy as np

def preprocess_plate(plate):
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)

    # Upscale 
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Sharpen
    kernel = np.array([[0,-1,0], [-1,5,-1], [0,-1,0]])
    gray = cv2.filter2D(gray, -1, kernel)

    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )

    return thresh
