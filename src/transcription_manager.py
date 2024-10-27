# src/transcription_manager.py
import os
import logging
from openai import OpenAI
from chunk_manager import ChunkManager
from audio_file import AudioFile

class TranscriptionManager:
    def __init__(self, api_key, audio_dir='../audio-files', transcript_dir='../transcripts'):
        self.client = OpenAI(api_key=api_key)
        self.audio_dir = audio_dir
        self.transcript_dir = transcript_dir

    def get_files_to_transcribe(self):
        audio_files = {f.split(".")[0] for f in os.listdir(self.audio_dir)}
        transcript_files = {f.split(".")[0] for f in os.listdir(self.transcript_dir)}
        return [f"{self.audio_dir}/{file}.mp3" for file in audio_files - transcript_files]

    def create_transcript(self, file_path):
        with open(file_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text

    def process_audio_file(self, audio_file):
        transcript_path = f"{self.transcript_dir}/{audio_file.file_base}.txt"
        
        # Check if the transcript already exists
        if os.path.exists(transcript_path):
            logging.info(f"Transcript already exists for {audio_file.file_base}")
            return

        try:
            if audio_file.needs_chunking():
                logging.info(f"File {audio_file.file_base} is too large, chunking...")
                chunk_manager = ChunkManager(audio_file)
                chunk_paths = chunk_manager.chunk_audio()
                transcript = ''.join([self.create_transcript(chunk) for chunk in chunk_paths])
                chunk_manager.clean_up_chunks(chunk_paths)
            else:
                logging.info(f"Processing {audio_file.file_base} directly.")
                transcript = self.create_transcript(audio_file.file_path)

            # Write the final transcript to the output file
            with open(transcript_path, 'w') as f:
                f.write(transcript)
            logging.info(f"Transcript written to {transcript_path}")

        except Exception as e:
            logging.error(f"Error processing {audio_file.file_base}: {str(e)}")

    def transcribe_all_files(self):
        files_to_transcribe = self.get_files_to_transcribe()
        if not files_to_transcribe:
            logging.info("No new files to transcribe.")
            return
        
        for file_path in files_to_transcribe:
            audio_file = AudioFile(file_path)
            self.process_audio_file(audio_file)
