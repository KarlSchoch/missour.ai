from openai import OpenAI
from transcription.models import Transcript, Chunk
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List

class TaggingManager:
    """
    For an individual transcript, manages chunking and tagging

    Allows for defining LLM clients and chunking methods
    """
    def __init__(
            self, 
            api_key:str, 
            transcript:Transcript = None,
            chunk_size:int = 500,
            chunk_overlap:int = 50,
        ):
        self.client = OpenAI(api_key=api_key)
        self.transcript = transcript
        self.chunker = RecursiveCharacterTextSplitter(
            chunk_size = chunk_size,
            chunk_overlap = chunk_overlap
        )

    def chunk(self) -> List[Chunk]:
        self.docs = self.chunker.create_documents([self.transcript.transcript_text])

        chunks = []

        for doc in self.docs:
            chunk_obj = Chunk(
                transcript = self.transcript,
                chunk_text = doc.page_content,
            )
            chunk_obj.save()
            chunks.append(chunk_obj)

        return chunks
    
    def tag_chunk(self):
        return ""
    
    def tag_transcript(self):
        """
        Wraps the other functions to chunk then tag a full transcript
        """
        return ""
    