import os
import time
from multiprocessing import Process, Queue, Pipe
from multiprocessing.connection import Connection

import soundcard as sc
import soundfile as sf
import numpy as np
from loguru import logger
from numpy import ndarray

from exceptions import NoMicrophoneException


def slice_audio(speaker_audio: ndarray, microphone_audio: ndarray, speaker_tmp: ndarray, microphone_tmp: ndarray):
    full_audio = None
    # that's mean that we have unused chunks from previous iteration and we need to get chunks
    if len(speaker_tmp) != 0 and speaker_audio is None:
        max_index = min(len(microphone_audio), len(speaker_tmp))
        full_audio = microphone_audio[:max_index] + speaker_tmp[:max_index]

        if len(microphone_audio) > len(speaker_tmp):
            microphone_tmp = microphone_audio[max_index:]
            speaker_tmp = np.array([])
        else:
            speaker_tmp = speaker_tmp[max_index:]

    if len(microphone_tmp) != 0 and microphone_audio is None:
        max_index = min(len(microphone_tmp), len(speaker_audio))
        full_audio = microphone_tmp[:max_index] + speaker_audio[:max_index]

        if len(speaker_audio) > len(microphone_tmp):
            speaker_tmp = speaker_audio[max_index:]
            microphone_tmp = np.array([])
        else:
            microphone_tmp = microphone_tmp[max_index:]

    if speaker_audio is not None and microphone_audio is not None and len(speaker_audio) != len(microphone_audio):
        max_index = min(len(speaker_audio), len(microphone_audio))
        full_audio = microphone_audio[:max_index] + speaker_audio[:max_index]

        if len(speaker_audio) > len(microphone_audio):
            speaker_tmp = speaker_audio[max_index:]
        else:
            microphone_tmp = microphone_audio[max_index:]

    if full_audio is None:
        logger.error("full audio is unspecified")
        raise RuntimeError("full audio is unspecified")

    return full_audio, speaker_tmp, microphone_tmp


def record_speaker(output: Queue, SAMPLE_RATE: int):
    with sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True).recorder(
            samplerate=SAMPLE_RATE) as mic:
        null_audio_timestamp = None  # variable store information about when started program receive the empty sounds
        while True:
            audio: ndarray = mic.record(numframes=None)
            if len(audio) == 0 and not null_audio_timestamp:
                null_audio_timestamp = time.time()  # there is no audio, save timestamp and continue to listen
                continue

            # if previous times there were empty sounds,
            # then it should add empty sounds directly into file by calculating them
            if len(audio) != 0 and null_audio_timestamp is not None:
                digital_audio_count = int(SAMPLE_RATE * (time.time() - null_audio_timestamp))
                digital_audio = np.array([[0, 0] for _ in range(digital_audio_count)])
                output.put(digital_audio)
                null_audio_timestamp = None

            output.put(audio)


def record_microphone(output: Queue, SAMPLE_RATE):
    try:
        with sc.get_microphone(id=str(sc.default_microphone().name), include_loopback=True).recorder(
                samplerate=SAMPLE_RATE) as mic:
            while True:
                audio = mic.record(numframes=None)
                output.put(audio)
    except RuntimeError:
        logger.info("microphone error")
        output.put(NoMicrophoneException("microphone turned off"))


@logger.catch
def getAudio(output: Queue, SAMPLE_RATE: int, conn: Connection):
    # sometimes audio of the speaker and microphone have difference in their sample rate
    # that's why we need to get only same part of audio that has in both audios
    speaker_queue = Queue()
    microphone_queue = Queue()

    process_speaker = Process(target=record_speaker, args=(speaker_queue, SAMPLE_RATE))
    process_microphone = Process(target=record_microphone, args=(microphone_queue, SAMPLE_RATE))

    process_speaker.start()
    process_microphone.start()
    logger.info("audio processes started!")

    # parts of no used audio in previous runs are stored here
    spare_audio_speaker_data = np.array([])
    spare_audio_microphone_data = np.array([])
    while True:
        # if there is message to terminate this audio process - terminate child processes
        if conn.poll():
            logger.info("stop audio processes!")
            conn.recv()
            if not microphone_queue._closed:
                process_microphone.terminate()
            process_speaker.terminate()
            conn.send("terminated")
            break

        microphone_audio = None
        speaker_audio = None

        # get speaker and microphone audio
        if not speaker_queue._closed and len(spare_audio_speaker_data) == 0:
            speaker_audio = speaker_queue.get()
        if not microphone_queue._closed and len(spare_audio_microphone_data) == 0:
            microphone_audio = microphone_queue.get()

        # if there is no microphone - shut down the process with queue object
        if isinstance(microphone_audio, NoMicrophoneException):
            process_microphone.terminate()
            microphone_queue.close()

            if speaker_audio is None:
                pass
            else:
                output.put(speaker_audio)
            continue

        # this can't be
        if speaker_audio is None and microphone_audio is None:
            logger.warning("speaker and microphone audio don't return values!")
            continue

        if not microphone_queue._closed:
            # that's mean that from previous iteration we have chunks from microphone or speaker that weren't used
            if len(spare_audio_microphone_data) != 0 or len(spare_audio_speaker_data) != 0 or len(microphone_audio) != len(speaker_audio):
                full_audio, spare_audio_speaker_data, spare_audio_microphone_data = slice_audio(speaker_audio, microphone_audio, spare_audio_speaker_data,
                                                                      spare_audio_microphone_data)
            else:
                full_audio = microphone_audio + speaker_audio
        else:
            full_audio = speaker_audio

        # this can't be
        if full_audio is None:
            logger.error("full audio doesn't exist!")
            raise RuntimeError("full audio doesn't exist!")
        output.put(full_audio)


class AudioWriter:
    __writer = None

    def __init__(self, sample_rate: int, filename: str, base_path: str):
        file_path = os.path.join(base_path, filename)
        logger.info("created audio writer")
        self.__writer = sf.SoundFile(file_path, "w", sample_rate, 2, format="WAV")

    def addChunk(self, chunk_data):
        self.__writer.write(chunk_data)

    def close(self):
        logger.info("closed audio writer")
        self.__writer.close()


if __name__ == '__main__':
    con1, con2 = Pipe()
    q = Queue()
    SAMPLE_RATE = 48000  # [Hz]. sampling rate.

    p = Process(target=getAudio, args=(q, SAMPLE_RATE, con2))
    p.start()

    writer = AudioWriter(SAMPLE_RATE, "out.wav", "./")
    for i in range(10):
        data = q.get()
        writer.addChunk(data)
    writer.close()
    p.terminate()
