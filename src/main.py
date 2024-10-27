# src/main.py
import os
import logging
from transcription_manager import TranscriptionManager

if __name__ == "__main__":
    # Set the logging level
    logging.basicConfig(level=logging.INFO)

    # Get OpenAI API key from environment variable
    api_key = os.getenv('OPENAI_API_KEY')

    if not api_key:
        logging.error("OpenAI API key not found. Set the OPENAI_API_KEY environment variable.")
        exit(1)

    # Create a TranscriptionManager and transcribe all files
    manager = TranscriptionManager(api_key)
    manager.transcribe_all_files()
