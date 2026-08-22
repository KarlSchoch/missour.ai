import logging
from typing import List
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from transcription.models import Chunk, Tag, TaskPricing, Topic, Transcript
from transcription.services.model_calls import (
    is_simulated_model_environment,
    is_test_model_environment,
    parsed_response,
    provider_request_id,
    token_usage,
    validate_provider_request_id,
    validate_token_usage,
)
from transcription.services.pricing import (
    complete_token_event,
    create_pending_usage_event,
    create_simulated_usage_event,
    mark_failed,
    mark_reconciliation_required,
    PricingResolutionError,
    resolve_pricing,
)
from transcription.tests.test_utils import FakeLLM

logger = logging.getLogger(__name__)


class Classification(BaseModel):
    tag: bool = Field(description="whether the topic is covered in the passage")
    relevant_section: str = Field(
        description=(
            "if the passage contains the topic, extract the portion that led to "
            "this conclusion"
        )
    )


class TaggingManager:
    """Chunk and tag a transcript while recording each model invocation."""

    def __init__(
        self,
        api_key: str,
        transcript: Transcript,
        topics: list[Topic] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        tagging_model: str = None,
        model_provider: str = "openai",
        run_id: str = None,
    ):
        self.api_key = api_key
        self.model_provider = model_provider
        self.tagging_model = tagging_model or settings.TAGGING_MODEL
        self.transcript = transcript
        self.chunker = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.chunks: list[Chunk] = []
        self.topics: list[Topic] = topics or []
        self.tags: list[Tag] = []
        self.failed_pairs = []
        self.run_id = run_id or str(uuid4())
        self.llm = None

    def _validate_topic_ownership(self, topics: List[Topic]) -> None:
        mismatched_topics = [
            topic.pk
            for topic in topics
            if topic.created_by_id != self.transcript.created_by_id
        ]
        if mismatched_topics:
            raise ValueError("Topics must be owned by the same user as the transcript.")

    def _initialize_llm(self):
        if self.llm is not None:
            return self.llm
        fake_responses = [
            Classification(tag=index % 2 == 0, relevant_section="Some random text")
            for index in range(100)
        ]
        if is_simulated_model_environment():
            logger.info("MODEL_ENV=dev; using simulated tagging responses")
            self.llm = FakeLLM(fake_responses)
            return self.llm

        llm = init_chat_model(
            self.tagging_model,
            model_provider=self.model_provider,
            api_key=self.api_key,
        )
        try:
            self.llm = llm.with_structured_output(
                Classification,
                include_raw=True,
            )
        except TypeError:
            # Test doubles and older compatible providers may not expose
            # include_raw. Their parsed result remains supported with zero usage.
            self.llm = llm.with_structured_output(Classification)
        return self.llm

    def chunk(self) -> List[Chunk]:
        self.docs = self.chunker.create_documents([self.transcript.transcript_text])
        for doc in self.docs:
            self.chunks.append(
                Chunk.objects.create(
                    transcript=self.transcript,
                    chunk_text=doc.page_content,
                )
            )
        return self.chunks

    def _idempotency_key(self, chunk, topic, run_id):
        return (
            f"tagging:{self.transcript.pk}:{chunk.pk}:{topic.pk}:"
            f"{run_id}:invocation"
        )

    def _prompt(self, chunk, topic):
        template = ChatPromptTemplate.from_template(
            """
            Determine whether the following passage contains a reference to the
            provided topic. If unsure, assume the passage covers the topic because
            false negatives are more impactful than false positives.

            Provide the properties mentioned in the Classification function.

            Topic:
            {topic}

            Passage:
            {passage}
            """
        )
        return template.invoke(
            {"passage": chunk.chunk_text, "topic": topic.topic}
        )

    def tag_chunk(
        self,
        chunk: Chunk,
        topics: List[Topic] = None,
        *,
        run_id: str = None,
        regenerate: bool = False,
    ) -> List[Tag]:
        topics = topics or self.topics
        self._validate_topic_ownership(topics)
        run_id = run_id or self.run_id

        for topic in topics:
            existing_tag = Tag.objects.filter(chunk=chunk, topic=topic).first()
            if existing_tag is not None and not regenerate:
                continue

            simulated = is_simulated_model_environment()
            idempotency_key = self._idempotency_key(chunk, topic, run_id)
            usage_event = None
            try:
                if simulated:
                    resolve_pricing(
                        TaskPricing.TaskType.TAGGING,
                        self.model_provider,
                        self.tagging_model,
                    )
                else:
                    usage_event = create_pending_usage_event(
                        user=self.transcript.created_by,
                        task_type=TaskPricing.TaskType.TAGGING,
                        provider=self.model_provider,
                        model_name=self.tagging_model,
                        idempotency_key=idempotency_key,
                        transcript=self.transcript,
                    )
            except PricingResolutionError:
                logger.exception(
                    "pricing_resolution_failed user_id=%s task=tagging model=%s "
                    "transcript_id=%s chunk_id=%s topic_id=%s",
                    self.transcript.created_by_id,
                    self.tagging_model,
                    self.transcript.pk,
                    chunk.pk,
                    topic.pk,
                )
                raise
            if usage_event is not None:
                logger.info(
                    "usage_event_created usage_event_id=%s user_id=%s task=tagging "
                    "model=%s transcript_id=%s status=pending",
                    usage_event.pk,
                    self.transcript.created_by_id,
                    self.tagging_model,
                    self.transcript.pk,
                )

            try:
                raw_result = self._initialize_llm().invoke(
                    self._prompt(chunk, topic)
                )
            except Exception as exc:
                if usage_event is not None:
                    mark_failed(usage_event, reason=exc)
                self.failed_pairs.append((chunk.pk, topic.pk, exc))
                logger.exception(
                    "tagging_call_failed usage_event_id=%s transcript_id=%s "
                    "chunk_id=%s topic_id=%s",
                    usage_event.pk if usage_event else None,
                    self.transcript.pk,
                    chunk.pk,
                    topic.pk,
                )
                continue

            request_id = ""
            try:
                request_id = validate_provider_request_id(
                    provider_request_id(raw_result)
                )
                result = parsed_response(raw_result)
                if not isinstance(result, Classification):
                    result = Classification.model_validate(result)
                usage_values = token_usage(raw_result)
                input_tokens, cached_tokens, output_tokens = validate_token_usage(
                    *usage_values,
                    allow_all_missing=(
                        simulated or is_test_model_environment()
                    ),
                )
                with transaction.atomic():
                    if existing_tag is None:
                        tag_obj = Tag.objects.create(
                            topic=topic,
                            chunk=chunk,
                            topic_present=result.tag,
                            relevant_section=result.relevant_section,
                        )
                    else:
                        existing_tag.topic_present = result.tag
                        existing_tag.relevant_section = result.relevant_section
                        existing_tag.save(
                            update_fields=["topic_present", "relevant_section"]
                        )
                        tag_obj = existing_tag

                    if simulated:
                        usage_event = create_simulated_usage_event(
                            user=self.transcript.created_by,
                            task_type=TaskPricing.TaskType.TAGGING,
                            provider=self.model_provider,
                            model_name=self.tagging_model,
                            idempotency_key=idempotency_key,
                            provider_request_id=request_id,
                            transcript=self.transcript,
                            tag=tag_obj,
                            calculation_details={
                                "tagging_run_id": run_id,
                                "chunk_id": chunk.pk,
                                "topic_id": topic.pk,
                                "provider_request_id_present": bool(request_id),
                            },
                        )
                    else:
                        usage_event = complete_token_event(
                            usage_event,
                            input_tokens=input_tokens,
                            cached_input_tokens=cached_tokens,
                            output_tokens=output_tokens,
                            provider_request_id=request_id,
                            tag=tag_obj,
                            calculation_details={
                                "tagging_run_id": run_id,
                                "chunk_id": chunk.pk,
                                "topic_id": topic.pk,
                                "provider_request_id_present": bool(request_id),
                            },
                        )
            except Exception as exc:
                if usage_event is not None and not simulated:
                    mark_reconciliation_required(
                        usage_event,
                        reason=exc,
                        calculation_details={"provider_response_received": True},
                    )
                self.failed_pairs.append((chunk.pk, topic.pk, exc))
                logger.exception(
                    "usage_reconciliation_required usage_event_id=%s "
                    "provider_request_id=%s transcript_id=%s chunk_id=%s topic_id=%s",
                    usage_event.pk if usage_event else None,
                    request_id,
                    self.transcript.pk,
                    chunk.pk,
                    topic.pk,
                )
                continue

            self.tags.append(tag_obj)
            logger.info(
                "usage_event_transition usage_event_id=%s user_id=%s task=tagging "
                "model=%s provider_request_id=%s artifact_id=%s status=%s",
                usage_event.pk,
                self.transcript.created_by_id,
                self.tagging_model,
                request_id,
                tag_obj.pk,
                usage_event.status,
            )

        return self.tags

    def tag_transcript(
        self,
        topics: List[Topic] = None,
        *,
        run_id: str = None,
        regenerate: bool = False,
    ) -> List[Tag]:
        topics = topics or self.topics
        self._validate_topic_ownership(topics)
        run_id = run_id or self.run_id
        self.chunks = list(Chunk.objects.filter(transcript=self.transcript))
        has_single_partial_legacy_chunk = (
            len(self.chunks) == 1
            and self.chunks[0].chunk_text != self.transcript.transcript_text
        )
        if not self.chunks or has_single_partial_legacy_chunk:
            self.chunks = []
            self.chunk()
        for chunk in self.chunks:
            self.tag_chunk(
                chunk,
                topics,
                run_id=run_id,
                regenerate=regenerate,
            )
        return self.tags
