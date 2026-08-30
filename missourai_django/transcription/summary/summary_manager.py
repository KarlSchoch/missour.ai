import logging
from uuid import uuid4

from django.conf import settings
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from transcription.models import Summary, TaskPricing, Transcript, Topic
from transcription.services.model_calls import (
    is_simulated_model_environment,
    is_test_model_environment,
    provider_request_id,
    response_text,
    token_usage,
    validate_provider_request_id,
    validate_response_text,
    validate_token_usage,
)
from transcription.services.pricing import (
    create_pending_usage_event,
    create_simulated_usage_event,
    complete_token_event,
    mark_failed,
    mark_reconciliation_required,
    PricingResolutionError,
    resolve_pricing,
)
from transcription.tests.test_utils import FakeLLM

logger = logging.getLogger(__name__)


class SummaryManager:
    """Generate summaries while recording one immutable usage event per call."""

    def __init__(
        self,
        api_key: str,
        summary_model: str = None,
        model_provider: str = "openai",
    ):
        self.model_provider = model_provider
        self.summary_model = summary_model or settings.SUMMARY_MODEL
        if is_simulated_model_environment():
            logger.info("MODEL_ENV=dev; using simulated summary responses")
            self.llm = FakeLLM(
                ["Concise summary of a deep and engaging hearing."] * 5
            )
        else:
            self.llm = init_chat_model(
                self.summary_model,
                model_provider=self.model_provider,
                api_key=api_key,
            )

        self.topic_summary_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You summarize text. Be concise"),
                (
                    "user",
                    "Summarize the following piece of text, focusing on the "
                    "specified topic of interest.\n\nTopic of Interest: "
                    "{tgt_topic}\n\nText: {transcript_content}",
                ),
            ]
        )
        self.general_summary_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You summarize text. Be concise"),
                ("user", "Summarize the following piece of text\n\nText: {transcript_content}"),
            ]
        )

    def summarize(
        self,
        transcript_content: str,
        tgt_transcript: Transcript,
        tgt_topic: Topic = None,
        operation_id: str = None,
    ):
        if (
            tgt_topic is not None
            and tgt_topic.created_by_id != tgt_transcript.created_by_id
        ):
            raise ValueError("Topic must be owned by the same user as the transcript.")

        summary_type = "topic" if tgt_topic else "general"
        prompt_template = (
            self.topic_summary_prompt if tgt_topic else self.general_summary_prompt
        )
        prompt_values = {"transcript_content": transcript_content}
        if tgt_topic:
            prompt_values["tgt_topic"] = tgt_topic.topic
        prompt = prompt_template.invoke(prompt_values)
        operation_id = operation_id or str(uuid4())
        idempotency_key = (
            f"summary:{tgt_transcript.pk}:{summary_type}:"
            f"{tgt_topic.pk if tgt_topic else 'general'}:{operation_id}"
        )
        simulated = is_simulated_model_environment()
        usage_event = None

        try:
            if simulated:
                # Fail before a simulated invocation when configuration is absent.
                resolve_pricing(
                    TaskPricing.TaskType.SUMMARY,
                    self.model_provider,
                    self.summary_model,
                )
            else:
                usage_event = create_pending_usage_event(
                    user=tgt_transcript.created_by,
                    task_type=TaskPricing.TaskType.SUMMARY,
                    provider=self.model_provider,
                    model_name=self.summary_model,
                    idempotency_key=idempotency_key,
                    transcript=tgt_transcript,
                )
        except PricingResolutionError:
            logger.exception(
                "pricing_resolution_failed user_id=%s task=summary model=%s "
                "transcript_id=%s",
                tgt_transcript.created_by_id,
                self.summary_model,
                tgt_transcript.pk,
            )
            raise
        if usage_event is not None:
            logger.info(
                "usage_event_created usage_event_id=%s user_id=%s task=summary "
                "model=%s transcript_id=%s status=pending",
                usage_event.pk,
                tgt_transcript.created_by_id,
                self.summary_model,
                tgt_transcript.pk,
            )

        try:
            raw_result = self.llm.invoke(prompt)
        except Exception as exc:
            if usage_event is not None:
                mark_failed(usage_event, reason=exc)
                logger.warning(
                    "usage_event_transition usage_event_id=%s status=failed",
                    usage_event.pk,
                )
            raise

        try:
            summary_text = validate_response_text(response_text(raw_result))
        except Exception as exc:
            if usage_event is not None and not simulated:
                mark_reconciliation_required(
                    usage_event,
                    reason=exc,
                    calculation_details={"provider_response_received": True},
                )
            raise

        summary_obj = Summary.objects.create(
            transcript=tgt_transcript,
            summary_type=summary_type,
            topic=tgt_topic,
            text=summary_text,
        )

        request_id = ""
        try:
            request_id = validate_provider_request_id(
                provider_request_id(raw_result)
            )
            usage_values = token_usage(raw_result)
            input_tokens, cached_tokens, output_tokens = validate_token_usage(
                *usage_values,
                allow_all_missing=(
                    simulated or is_test_model_environment()
                ),
            )
            if simulated:
                usage_event = create_simulated_usage_event(
                    user=tgt_transcript.created_by,
                    task_type=TaskPricing.TaskType.SUMMARY,
                    provider=self.model_provider,
                    model_name=self.summary_model,
                    idempotency_key=idempotency_key,
                    provider_request_id=request_id,
                    transcript=tgt_transcript,
                    summary=summary_obj,
                    calculation_details={
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
                    summary=summary_obj,
                    calculation_details={
                        "provider_request_id_present": bool(request_id),
                    },
                )
        except Exception as exc:
            if usage_event is not None and not simulated:
                try:
                    usage_event = mark_reconciliation_required(
                        usage_event,
                        reason=exc,
                        provider_request_id=request_id,
                        summary=summary_obj,
                        calculation_details={
                            "provider_response_received": True,
                            "provider_request_id_present": bool(request_id),
                            "summary_id": summary_obj.pk,
                        },
                    )
                except Exception:
                    logger.exception(
                        "usage_reconciliation_marking_failed usage_event_id=%s",
                        usage_event.pk,
                    )
            logger.exception(
                "usage_reconciliation_required usage_event_id=%s "
                "provider_request_id=%s transcript_id=%s",
                usage_event.pk if usage_event else None,
                request_id,
                tgt_transcript.pk,
            )

        logger.info(
            "usage_event_transition usage_event_id=%s user_id=%s task=summary "
            "model=%s provider_request_id=%s artifact_id=%s status=%s",
            usage_event.pk if usage_event else None,
            tgt_transcript.created_by_id,
            self.summary_model,
            request_id,
            summary_obj.pk,
            usage_event.status if usage_event else "reconciliation_required",
        )
        return summary_obj
