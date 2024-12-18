# src/transcription_manager.py
import os
import logging
from openai import OpenAI
from pydub import AudioSegment
import io

class TranscriptionManager:
    def __init__(self, api_key:str, max_file_size=25 * 1024 * 1024):
        self.client = OpenAI(api_key=api_key)
        self.max_file_size = max_file_size

    def create_transcript(self, file_path:str) -> str:
        # Ingest audio file into memory and get file size
        audio = AudioSegment.from_file(file_path)
        file_size = os.path.getsize(file_path)

        # Determine whether to chunk the audio file
        if file_size > self.max_file_size:
            # Determine chunk count and length
            logging.info(f"File {file_path} is too large, chunking...")
            chunk_count = file_size // self.max_file_size + 1
            chunk_length_ms = len(audio) // chunk_count
            # Inintialize transcript
            transcript = ""
            # Transcribe each chunk
            for i in range(0, len(audio), chunk_length_ms):
                chunk = audio[i:i + chunk_length_ms]
                transcript += self._transcribe_chunk(chunk)
        else:
            logging.info(f"Processing {file_path} directly.")
            transcript = self._transcribe_chunk(audio)
        
        return transcript
    
    def _transcribe_chunk(self, chunk:AudioSegment) -> str:

        # TO DO: Add logic for removing chunks
        chunk.export('./chunk.mp3', format="mp3")
        print(os.listdir())
        with open("./chunk.mp3", "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text