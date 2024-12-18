# src/chunk_manager.py
import os
import logging

class ChunkManager:
    def __init__(self, audio_file):
        self.audio_file = audio_file
    
    def chunk_audio(self):
        chunk_count = self.audio_file.file_size // self.audio_file.max_file_size + 1
        chunk_length_ms = len(self.audio_file.audio) // chunk_count
        
        chunk_paths = []
        for i in range(0, len(self.audio_file.audio), chunk_length_ms):
            chunk = self.audio_file.audio[i:i + chunk_length_ms]
            chunk_path = f"../audio-files/tmp_chunk_{i}_{self.audio_file.file_base}.mp3"
            chunk.export(chunk_path, format="mp3")
            chunk_paths.append(chunk_path)
        
        return chunk_paths
    
    def clean_up_chunks(self, chunk_paths):
        for chunk_path in chunk_paths:
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
                logging.info(f"Removed temporary chunk file: {chunk_path}")
