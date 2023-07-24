import unittest
import time

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32ui

from video import getImageObject, getWindowsSize


class VideoTest(unittest.TestCase):
    def test_video_capture_efficiency(self):
        hdesktop = win32gui.GetDesktopWindow()  # create handle to desktop window
        desktop_dc = win32gui.GetWindowDC(hdesktop)  # create device context

        # get the size of the screen
        left_x = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top_y = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width, height = getWindowsSize()

        time_start = time.time()
        img = getImageObject(desktop_dc, left_x, top_y, width, height)
        print(f"{str(1 / (time.time() - time_start))} fps")


if __name__ == '__main__':
    unittest.main()
