# src/transcription_manager.py
import os
import logging
import openai
from openai import OpenAI
import io
import math
import subprocess
import json

class TranscriptionManager:
    def __init__(self, api_key:str, file_path:str, max_file_size:int=20):
        self.client = OpenAI(api_key=api_key)
        self.max_file_size = max_file_size
        self.file_path = file_path
        # Calculate file duration
        command = [
                "ffprobe", "-i", self.file_path,
                "-show_entries", "format=duration",
                "-v", "quiet", "-of", "json"
        ]
        res = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        try:
              self.file_duration = float(json.loads(res.stdout)["format"]["duration"])
        except (KeyError, json.JSONDecodeError, TypeError) as e:
              raise e
        # Calculate chunk settings
        self.chunk_path=f"{os.getcwd()}/chunk.wav"
        self.chunk_settings = {
            'channels': 1,
            'sample_rate': 16000,
            'bit_depth': 2
        }
        self.chunk_length_sec = math.floor(
            ( self.max_file_size * 1024 * 1024 ) / ( self.chunk_settings['sample_rate'] * self.chunk_settings['bit_depth'] * self.chunk_settings['channels'] )
        )

    def read_audio_chunk(self, start_time:float=0):

        command = [
            "ffmpeg",
            "-n", # will cause read to fail if chunk file already exists
            "-ss", str(start_time),
            "-t", str(self.chunk_length_sec),
            "-i", self.file_path,
            "-f", "wav",
            "-ac", str(self.chunk_settings['channels']),
            "-ar", str(self.chunk_settings['sample_rate']),
            f"{self.chunk_path}"
        ]


        subprocess.run(command, stderr=subprocess.DEVNULL)
        
        return

    def create_transcript(self) -> str:
        transcript=""
        start_time=0
        i = 1
        tgt_chunks = math.floor(self.file_duration / self.chunk_length_sec) + 1

        while start_time < self.file_duration:
            print(f"Processing chunk {i} of {tgt_chunks}")
            self.read_audio_chunk(start_time)
            print("* Successfully read in audio chunk")
            transcript += self._transcribe_chunk()
            print("* Successfully transcribed chunk")

            start_time += self.chunk_length_sec
            i += 1
   
        return transcript
    

    def _transcribe_chunk(self) -> str:
        # Check for the model_env
        if os.getenv("MODEL_ENV") == "dev":
            print("MODEL_ENV is DEV.  Bypassing external API calls")
            return "Short transcript text resembling actual API output."
            
        with open(f"{self.chunk_path}", "rb") as audio_file:
            try:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            except openai.BadRequestError as e:
                # Handle error code is "audio_too_short" by returning empty transcript
                if e.code == 'audio_too_short':
                    print("Warning: Skipping chunk due to short audio")
                    return ""
                
                raise e
            finally:
                try:
                    os.remove(self.chunk_path)
                    print(f"Chunk at {self.chunk_path} successfully deleted")
                except:
                    print(f"Chunk does not exist at {self.chunk_path}")
                
        return transcript.text
