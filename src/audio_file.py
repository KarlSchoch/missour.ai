# src/audio_file.py
from pydub import AudioSegment
import os

class AudioFile:
    def __init__(self, file_path, max_file_size=20 * 1024 * 1024):
        self.file_path = file_path
        self.file_base = os.path.basename(file_path).split(".")[0]
        self.audio = AudioSegment.from_file(file_path)
        self.file_size = os.path.getsize(file_path)
        self.max_file_size = max_file_size

    def needs_chunking(self):
        return self.file_size > self.max_file_size