import os
import time
from multiprocessing import Queue

import cv2
import numpy as np
import win32api
import win32con
import win32gui
import win32ui
from loguru import logger


def getWindowsSize():
    hdesktop = win32gui.GetDesktopWindow()

    rect = win32gui.GetWindowRect(hdesktop)
    x = rect[0]
    y = rect[1]
    width = rect[2] - x
    height = rect[3] - y

    return width, height


def getImageObject(desktop_dc, left_x, top_y, width, height):
    img_dc = win32ui.CreateDCFromHandle(desktop_dc)
    mem_dc = img_dc.CreateCompatibleDC()

    # create bitmap
    screenshot_bitmap = win32ui.CreateBitmap()
    screenshot_bitmap.CreateCompatibleBitmap(img_dc, width, height)
    mem_dc.SelectObject(screenshot_bitmap)

    # copy the screen into our memory device context
    mem_dc.BitBlt((0, 0), (width, height), img_dc, (left_x, top_y), win32con.SRCCOPY)

    # convert to numpy array
    signed_ints_array = screenshot_bitmap.GetBitmapBits(True)

    # delete the handles to prevent memory leaks
    mem_dc.DeleteDC()
    win32gui.DeleteObject(screenshot_bitmap.GetHandle())

    img = np.frombuffer(signed_ints_array, dtype=np.uint8).reshape(height, width, 4)
    img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)  # remove the alpha channel and convert the image to BGR color format
    opencv_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # create the OpenCV image object

    return opencv_img


def getScreen(output: Queue):
    hdesktop = win32gui.GetDesktopWindow()  # create handle to desktop window
    desktop_dc = win32gui.GetWindowDC(hdesktop)  # create device context

    # get the size of the screen
    left_x = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    top_y = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    width, height = getWindowsSize()

    # start time of the current second
    current_sec_start_time = time.time()
    current_fps = 0
    while True:
        # if there is passed more than 1 second - send information into queue
        if time.time() - current_sec_start_time >= 1:
            output.put(current_fps)
            current_sec_start_time = time.time()
            current_fps = 0

        img = getImageObject(desktop_dc, left_x, top_y, width, height)
        output.put(img)
        current_fps += 1


class VideoWriter:
    __writer = None

    def __init__(self, img_size: tuple[int, int], filename: str, base_path: str, fps: float):
        logger.info("created video writer")
        file_path = os.path.join(base_path, filename)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)

        __fourcc = cv2.VideoWriter_fourcc(*'DIVX')
        self.__writer = cv2.VideoWriter(file_path, __fourcc, fps, img_size)

    def addFrame(self, frame):
        self.__writer.write(frame)

    def closeWriter(self):
        self.__writer.release()
