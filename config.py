import os

from pynput.keyboard import Key


class ProgramConfig:
    # read only values
    SAMPLE_RATE = 48000
    STOP_PROGRAM_KEY = Key.f8
    BASE_PATH = os.getcwd()
    VIDEO_FILENAME = "video.avi"
    AUDIO_FILENAME = "audio.wav"
    RESULT_FILENAME = "out.mp4"
    LOG_LEVEL = "INFO"


class ProgramState:
    video_process_terminated = False
    audio_process_terminated = False
    audio = True
    video = True
    video_fps_collection: list  # this collection is needed for calculating average fps for video.

    def __init__(self):
        self.video_fps_collection = []
