from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os
from ..tests.test_utils import FakeLLM

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
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You summarize text.  Be concise"),
            ("user", "Summarize the following: \n\n{input}"),
        ])
        self.chain = self.prompt | self.llm | StrOutputParser()

    def summarize(self, transcript_content:str):
        summary = self.chain.invoke(
            {"input": transcript_content}
        )
        return summary
