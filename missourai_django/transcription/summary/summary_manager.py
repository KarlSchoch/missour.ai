from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os
from ..tests.test_utils import FakeLLM
from ..models import Summary, Transcript, Topic

class SummaryManager:
    """
    For a piece of text, generates summaries
    """
    def __init__(
            self,
            api_key:str,
            summary_model:str = 'gpt-4.1-mini',
            model_provider:str = 'openai'
        ):
        self.model_provider = model_provider
        fake_summary_responses = [
            'Concise summary of a deep and engaging hearing.',
        ] * 5
        if os.getenv("MODEL_ENV") == "dev":
            print("MODEL_ENV is DEV.  Instantiating FakeLLM")
            self.llm = FakeLLM(fake_summary_responses)
        elif os.getenv("MODEL_ENV") in ['test', 'prod']:
            self.llm = init_chat_model(
                summary_model,
                model_provider=self.model_provider,
                api_key=api_key
            )
        self.topic_summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You summarize text.  Be concise"),
            (
                "user", 
                "Summarize the following piece of text in 350 words or less, focusing on the specified topic of interest.\n\n Topic of Interest: {tgt_topic}\n\n Text: {transcript_content}"
            ),
        ])
        self.general_summary_prompt = ChatPromptTemplate.from_messages([
            ("system", "You summarize text.  Be concise"),
            ("user", "Summarize the following piece of text in 500 words or less\n\n Text: {transcript_content}"),
        ])
        self.chains = {
            "topic": self.topic_summary_prompt | self.llm | StrOutputParser(),
            "general": self.general_summary_prompt | self.llm | StrOutputParser(),
        }

    def summarize(
            self, 
            transcript_content:str,
            tgt_transcript:Transcript,
            tgt_topic:Topic = None,
        ):

        if not tgt_topic:
            summary_type = 'general'
            summary_text = self.chains.get('general').invoke({
                "transcript_content": transcript_content,
            })
        else:
            summary_type = 'topic'
            summary_text = self.chains.get('topic').invoke({
                "transcript_content": transcript_content,
                "tgt_topic": tgt_topic.topic,
            })
        summary_obj = Summary(
            transcript = tgt_transcript,
            summary_type = summary_type,
            topic = tgt_topic,
            text = summary_text
        )
        summary_obj.save()

        return summary_obj
