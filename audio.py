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


def record_speaker(output: Queue, SAMPLE_RATE):
    with sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True).recorder(
            samplerate=SAMPLE_RATE) as mic:
        while True:
            t1 = time.time()
            audio: ndarray = mic.record(numframes=SAMPLE_RATE)
            t2 = time.time() - t1

            # audio is recording for 1 second
            # sometimes it takes less than 1 second (when it records empty sound) to record
            # and that's why we need to slice the array in the percent
            difference = 1 - t2
            if difference > 0.05:
                last_index = int(SAMPLE_RATE * t2)
                audio = audio[:last_index]

            output.put(audio)


def record_microphone(output: Queue, SAMPLE_RATE):
    try:
        with sc.get_microphone(id=str(sc.default_microphone().name), include_loopback=True).recorder(
                samplerate=SAMPLE_RATE) as mic:
            while True:
                audio = mic.record(numframes=SAMPLE_RATE)
                output.put(audio)
    except RuntimeError:
        logger.info("microphone error")
        output.put(NoMicrophoneException("microphone turned off"))

@logger.catch
def getAudio(output: Queue, SAMPLE_RATE: int, conn: Connection):
    # sometimes audio of the speaker and microphone have difference in their sample rate
    # that's why we need to get only same part of audio that has in both audios
    def slice_audio(speaker_audio, microphone_audio, speaker_tmp: ndarray, microphone_tmp: ndarray):
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

    speaker_queue = Queue()
    microphone_queue = Queue()

    process_speaker = Process(target=record_speaker, args=(speaker_queue, SAMPLE_RATE))
    process_microphone = Process(target=record_microphone, args=(microphone_queue, SAMPLE_RATE))

    process_speaker.start()
    process_microphone.start()
    logger.info("audio processes started!")

    # parts of no used audio are stored here
    tmp_speaker = np.array([])
    tmp_microphone = np.array([])
    while True:
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

        if not speaker_queue._closed and len(tmp_speaker) == 0:
            speaker_audio = speaker_queue.get()
        if not microphone_queue._closed and len(tmp_microphone) == 0:
            microphone_audio = microphone_queue.get()

        if isinstance(microphone_audio, NoMicrophoneException):
            process_microphone.terminate()
            microphone_queue.close()

            if speaker_audio is None:
                pass
            else:
                output.put(speaker_audio)
            continue

        if speaker_audio is None and microphone_audio is None:
            logger.warning("speaker and microphone audio don't return values!")
            continue

        if not microphone_queue._closed:
            # that's mean that from previous iteration we have chunks from microphone or speaker that weren't used
            if len(tmp_microphone) != 0 or len(tmp_speaker) != 0 or len(microphone_audio) != len(speaker_audio):
                full_audio, tmp_speaker, tmp_microphone = slice_audio(speaker_audio, microphone_audio, tmp_speaker, tmp_microphone)
            else:
                full_audio = microphone_audio + speaker_audio
        else:
            full_audio = speaker_audio

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