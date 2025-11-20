"""
Run with:  OPENAI_API_KEY=... python scripts/inspect_tagging_llm.py
"""

import os
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import OpenAI

TOPIC = "Workforce Development"
PASSAGE = "Our curriculum focuses on apprenticeships and mentorship to upskill workers."

class Classification(BaseModel):
    tag: bool = Field(description="whether the topic is covered in the passage")
    relevant_section: str = Field(description="excerpt supporting the classification")

def main() -> None:
    load_dotenv()
    api_key = os.environ["OPENAI_API_KEY"]

    # Optional argument to ensure the key is visible to child libs
    # os.environ.setdefault("OPENAI_API_KEY", api_key)

    llm = init_chat_model(
        "gpt-4.1-mini",
        model_provider="openai",
    ).with_structured_output(Classification)

    prompt = ChatPromptTemplate.from_template(
        """
        Determine whether the following passage contains a reference to the provided topic.
        If unsure, answer False.

        Topic:
        {topic}

        Passage:
        {passage}
        """
    ).invoke({"topic": TOPIC, "passage": PASSAGE})

    result = llm.invoke(prompt)

    print(f"type: {type(result)}")
    print(f"tag: {result.tag}")
    print(f"relevant_section: {result.relevant_section}")
    print(f"as dict: {result.dict()}")

if __name__ == "__main__":
    main()
