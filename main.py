
import os
import time
from multiprocessing import Process, Queue, Pipe
from threading import Thread

import cv2
from loguru import logger
from moviepy.video import VideoClip
from pynput import keyboard
import moviepy.editor as mpe

from config import ProgramConfig, ProgramState
from video import getScreen, VideoWriter, getWindowsSize
from audio import getAudio, AudioWriter


# change .avi fps to needed one fps
def change_video_fps(video_file_path: str, config: ProgramConfig, fps: float):
    size = getWindowsSize()
    temp_file_name = f"temp_{time.time()}.avi"
    writer = VideoWriter(size, temp_file_name, config.BASE_PATH, fps)

    vidcap = cv2.VideoCapture(video_file_path)
    success = True
    while success:
        success, frame = vidcap.read()
        writer.addFrame(frame)

    writer.closeWriter()
    vidcap.release()

    os.remove(video_file_path)
    os.rename(temp_file_name, video_file_path)


# combine .wav and .avi files into one mp4 file
def combine_audio_video(audio_file_path: str, video_file_path: str, result_filename: str, fps: float):
    my_clip = mpe.VideoFileClip(video_file_path)
    try:
        audio_background = mpe.AudioFileClip(audio_file_path)
        final_clip: VideoClip = my_clip.set_audio(audio_background)
        final_clip.write_videofile(result_filename, fps=fps)
        final_clip.close()
    except:
        # it means that no audio captured, only video
        my_clip.close()
        os.remove(result_filename)
        os.rename(video_file_path, result_filename)


# keyboard event handler
def keyboard_on_press(key, config: ProgramConfig, state_dict: ProgramState, start_program_time: float):
    # user can't stop program until processes are started
    if key == config.STOP_PROGRAM_KEY and time.time() - start_program_time > 1:
        state_dict.video = state_dict.audio = False
        logger.info("record is stopped")
        print("record is stopped")

        # active wait until both audio and video processes are terminated
        while not state_dict.video_process_terminated or not state_dict.audio_process_terminated:
            time.sleep(.1)

        audio_file_path = os.path.join(config.BASE_PATH, config.AUDIO_FILENAME)
        video_file_path = os.path.join(config.BASE_PATH, config.VIDEO_FILENAME)
        logger.info("start combining audio and video")

        all_fps = 0
        for fps in state_dict.video_fps_collection:
            all_fps += fps
        average_fps = all_fps / len(state_dict.video_fps_collection)

        change_video_fps(config.VIDEO_FILENAME, config, average_fps)
        combine_audio_video(audio_file_path, video_file_path, config.RESULT_FILENAME, average_fps)

        try:
            os.remove(audio_file_path)
            os.remove(video_file_path)
        except FileNotFoundError:
            pass
        except OSError:
            pass

        print(f"result of record in the file: {config.RESULT_FILENAME}")

        return False


# thread that works with video
@logger.catch
def video_thread(config: ProgramConfig, state_dict: ProgramState):
    def addFrame(frame, writer):
        # if process returned int - it means that this is fps for last second
        if type(frame) == int:
            fps = frame
            state_dict.video_fps_collection.append(fps)
            return
        writer.addFrame(frame)

    video_queue = Queue()
    video_filename = config.VIDEO_FILENAME
    size = getWindowsSize()
    writer = VideoWriter(size, video_filename, config.BASE_PATH, 29)

    video_process = Process(target=getScreen, args=(video_queue,))
    video_process.start()

    while True:
        if not state_dict.video:
            logger.info("stop video process!")
            video_process.terminate()
            writer.closeWriter()

            # add the remaining frames into video
            while not video_queue.empty():
                frame = video_queue.get()  # return cv2 frame or intenger as fps for fps collection
                addFrame(frame, writer)

            video_queue.close()
            state_dict.video_process_terminated = True
            break

        frame = video_queue.get()  # return cv2 frame or intenger as fps for fps collection
        addFrame(frame, writer)


# thread that works with audio
@logger.catch
def audio_thread(config: ProgramConfig, state_dict: ProgramState):
    con_thread, con_process = Pipe(duplex=True)
    audio_queue = Queue()
    audio_filename = config.AUDIO_FILENAME
    sample_rate = config.SAMPLE_RATE
    writer = AudioWriter(sample_rate, audio_filename, config.BASE_PATH)

    audio_process = Process(target=getAudio, args=(audio_queue, sample_rate, con_process))
    audio_process.start()

    while True:
        if not state_dict.audio:
            con_thread.send("terminate!")
            logger.info("stop audio process!")
            con_thread.recv()
            audio_process.terminate()

            # add remaining sounds into the audio file
            while not audio_queue.empty():
                chunk = audio_queue.get()
                writer.addChunk(chunk)

            writer.close()
            audio_queue.close()
            logger.info("audio process terminated!")
            state_dict.audio_process_terminated = True
            break

        chunk = audio_queue.get()
        writer.addChunk(chunk)


def main():
    config = ProgramConfig()
    state = ProgramState()
    th1 = Thread(target=video_thread, args=(config, state))
    th2 = Thread(target=audio_thread, args=(config, state))

    th1.start()
    th2.start()

    key = str(config.STOP_PROGRAM_KEY).replace("Key.", "")
    print(f"press {key} to stop the recording")
    start_program_time = time.time()
    with keyboard.Listener(on_press=lambda key: keyboard_on_press(key, config, state, start_program_time)) as listener:
        listener.join()


if __name__ == "__main__":
    logger.remove()
    logger.add("log/info.log", level=ProgramConfig.LOG_LEVEL)
    main()

