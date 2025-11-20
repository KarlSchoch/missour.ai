from openai import OpenAI
from transcription.models import Transcript, Chunk, Topic, Tag
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages.base import BaseMessage
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

class TaggingManager:
    """
    For an individual transcript, manages chunking and tagging

    Allows for defining multiple elements of chunking and tagging approaches
    """
    def __init__(
            self, 
            api_key:str, 
            transcript:Transcript = None,
            topics:list[Topic] = [],
            chunk_size:int = 500,
            chunk_overlap:int = 50,
            tagging_model:str = 'gpt-4.1.-mini',
            model_provider:str = 'openai'
        ):
        self.client = OpenAI(api_key=api_key)
        self.model_provider = model_provider
        self.tagging_model = tagging_model
        self.transcript = transcript
        self.chunker = RecursiveCharacterTextSplitter(
            chunk_size = chunk_size,
            chunk_overlap = chunk_overlap
        )
        self.chunks:list[Chunk] = []
        self.topics:list[Topic] = topics
        self.tags:list[Tag] = []

    def chunk(self) -> List[Chunk]:
        # Use chunker to create langchain "docs"
        self.docs = self.chunker.create_documents([self.transcript.transcript_text])

        # Save the chunks to the db and the TaggingManager class
        for doc in self.docs:
            chunk_obj = Chunk(
                transcript = self.transcript,
                chunk_text = doc.page_content,
            )
            chunk_obj.save()
            self.chunks.append(chunk_obj)

        return self.chunks
    
    def tag_chunk(self, chunk:Chunk, topics:List[Topic] = None) -> List[Tag]:
        # Validate data inputs
        ## If there is no chunk, provide user an error message
        ## If there are no topics, fall back onto self.topics
        if not topics:
            topics = self.topics

        # Set up LLM to enable tagging
        class Classification(BaseModel):
            tag:bool = Field(description="whether the topic is covered in the passage")
            relevant_section:str = Field(
                description="if you tagged the passage as containing the topic, extract the portion of the passage that led you to this conclusion"
            )
        # llm is langchain_core.language_models.chat_models.BaseChatModel
        llm = init_chat_model(
            self.tagging_model,
            model_provider=self.model_provider
        )
        # llm is now langchain_core.runnables.base.Runnable
        llm = llm.with_structured_output(Classification)

        # iterate through each tag and topic
        for topic in topics:
            print(f"* topic: {topic}")

            # tagging_prompt is ChatPromptTemplate class
            tagging_prompt = ChatPromptTemplate.from_template(
                """
                Determine whether the following passage contains a reference to the provided topic.
                
                If you are unsure, assume the passage covers the topic as false negatives are more impactful than false positives

                Provide the properties mentioned in the 'Classification' function.

                Topic:
                {topic}
                
                Passage:
                {passage}
                """
            )
            # prompt is langchain_core.prompt_values.PromptValue
            prompt = tagging_prompt.invoke({
                "passage": chunk,
                "topic": topic
            })

            # result is langchain_core.messages.base.BaseMessage
            result = llm.invoke(prompt)
            assert isinstance(result, BaseMessage)
            assert hasattr(result, "tag")
            assert hasattr(result, "relevant_section")

            # Create the Tag object
            tag_obj = Tag(
                topic = self.transcript,
                chunk = chunk,
                topic_present = result.tag,
                relevant_section = result.relevant_section
            )
            tag_obj.save()
            self.tags.append(tag_obj)

        return self.tags
    
    def tag_transcript(self):
        """
        Wraps the other functions to chunk then tag a full transcript
        """
        return ""
    