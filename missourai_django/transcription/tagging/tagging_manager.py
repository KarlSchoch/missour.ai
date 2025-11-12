from openai import OpenAI
from transcription.models import Transcript

class TaggingManager:
    def __init__(self, api_key:str):
        self.client = OpenAI(api_key=api_key)

    def chunk(self, transcript: Transcript):
        return ""
    
    def tag_chunk(self):
        return ""
    
    def tag_transcript(self):
        """
        Wraps the other functions to chunk then tag a full transcript
        """
        return ""
    