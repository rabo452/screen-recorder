import os
import time
from multiprocessing import Process, Queue, Pipe
from threading import Thread

from loguru import logger
from moviepy.video import VideoClip
from pynput import keyboard
from pynput.keyboard import Key
import moviepy.editor as mpe

from video import getScreen, VideoWriter, getWindowsSize
from audio import getAudio, AudioWriter


class ProgramConfig:
    # write values
    video_process_terminated = False
    audio_process_terminated = False
    audio = True
    video = True

    # read only values
    _VIDEO_FPS = 30
    _STOP_PROGRAM_KEY = Key.f8
    _BASE_PATH = os.getcwd()
    _VIDEO_FILENAME = "video.avi"
    _AUDIO_FILENAME = "audio.wav"
    _RESULT_FILENAME = "out.mp4"
    _LOG_LEVEL = "INFO"

# combine .wav and .avi files into one mp4 file
def combine_audio_video(audio_file: str, video_file: str, result_filename: str, fps: int):
    my_clip = mpe.VideoFileClip(video_file)
    audio_background = mpe.AudioFileClip(audio_file)
    final_clip: VideoClip = my_clip.set_audio(audio_background)
    final_clip.write_videofile(result_filename, fps=fps)
    final_clip.close()

# keyboard event handler
def keyboard_on_press(key, config: ProgramConfig, start_program_time: int):
    if key == config._STOP_PROGRAM_KEY and time.time() - start_program_time > 2:
        config.video = config.audio = False
        logger.info("record is stopped")
        print("record is stopped")

        # active wait until both audio and video processes are terminated
        while not config.video_process_terminated or not config.audio_process_terminated:
            time.sleep(.1)

        audio_file = os.path.join(config._BASE_PATH, config._AUDIO_FILENAME)
        video_file = os.path.join(config._BASE_PATH, config._VIDEO_FILENAME)
        logger.info("start combining audio and video")
        combine_audio_video(audio_file, video_file, config._RESULT_FILENAME, config._VIDEO_FPS)

        os.remove(audio_file)
        os.remove(video_file)

        print(f"result of record in the file: {config._RESULT_FILENAME}")
        return False

# thread that works with video
@logger.catch
def video_thread(config: ProgramConfig):
    video_queue = Queue()
    video_filename = config._VIDEO_FILENAME
    size = getWindowsSize()
    writer = VideoWriter(size, video_filename, config._BASE_PATH, config._VIDEO_FPS)

    video_process = Process(target=getScreen, args=(video_queue,))
    video_process.start()

    while True:
        if not config.video:
            logger.info("stop video process!")
            video_process.terminate()
            writer.closeWriter()
            video_queue.close()
            config.video_process_terminated = True
            break

        frame = video_queue.get()
        writer.addFrame(frame)

# thread that works with audio
@logger.catch
def audio_thread(config: ProgramConfig):
    con_thread, con_process = Pipe(duplex=True)
    audio_queue = Queue()
    audio_filename = config._AUDIO_FILENAME
    sample_rate = 40000
    writer = AudioWriter(sample_rate, audio_filename, config._BASE_PATH)

    audio_process = Process(target=getAudio, args=(audio_queue, sample_rate, con_process))
    audio_process.start()

    while True:
        if not config.audio:
            con_thread.send("terminate!")
            logger.info("stop audio process!")
            con_thread.recv()
            audio_process.terminate()
            writer.close()
            audio_queue.close()
            logger.info("audio process terminated!")
            config.audio_process_terminated = True
            break

        chunk = audio_queue.get()
        writer.addChunk(chunk)


def main():
    config = ProgramConfig()
    th1 = Thread(target=video_thread, args=(config,))
    th2 = Thread(target=audio_thread, args=(config,))

    th1.start()
    th2.start()

    key = str(config._STOP_PROGRAM_KEY).replace("Key.", "")
    print(f"press {key} to stop the recording")
    start_program_time = time.time()
    with keyboard.Listener(on_press=lambda key: keyboard_on_press(key, config, start_program_time)) as listener:
        listener.join()


if __name__ == "__main__":
    logger.remove()
    logger.add("log/info.log", level=ProgramConfig._LOG_LEVEL)
    main()
