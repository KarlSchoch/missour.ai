"""Provider-response helpers shared by billable model-call integrations."""

import os


class ProviderResponseValidationError(ValueError):
    """Raised when a provider response cannot be billed safely."""


def is_simulated_model_environment():
    return os.getenv("MODEL_ENV", "").lower() == "dev"


def is_test_model_environment():
    return os.getenv("MODEL_ENV", "").lower() == "test"


def parsed_response(response):
    if isinstance(response, dict) and "parsed" in response:
        parsing_error = response.get("parsing_error")
        if parsing_error:
            raise parsing_error
        return response["parsed"]
    return response


def raw_response(response):
    if isinstance(response, dict) and "raw" in response:
        return response["raw"]
    return response


def response_text(response):
    value = parsed_response(response)
    if isinstance(value, str):
        return value
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                pieces.append(item["text"])
            else:
                raise ProviderResponseValidationError(
                    "Provider response contained an unknown content item shape."
                )
        return "".join(pieces)
    return content


def provider_request_id(response):
    raw = raw_response(response)
    response_metadata = getattr(raw, "response_metadata", {}) or {}
    return (
        getattr(raw, "id", "")
        or response_metadata.get("request_id", "")
        or response_metadata.get("id", "")
    )


def token_usage(response):
    """Normalize LangChain/OpenAI usage into total input, cached input, output."""
    raw = raw_response(response)
    usage = getattr(raw, "usage_metadata", None) or {}
    response_metadata = getattr(raw, "response_metadata", {}) or {}
    provider_usage = response_metadata.get("token_usage", {}) or {}

    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        input_tokens = provider_usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens")
    if output_tokens is None:
        output_tokens = provider_usage.get("completion_tokens")

    input_details = usage.get("input_token_details", {}) or {}
    prompt_details = provider_usage.get("prompt_tokens_details", {}) or {}
    cached_tokens = input_details.get("cache_read")
    if cached_tokens is None:
        cached_tokens = input_details.get("cached_tokens")
    if cached_tokens is None:
        cached_tokens = prompt_details.get("cached_tokens")

    return input_tokens, cached_tokens, output_tokens


def _validated_token_count(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderResponseValidationError(
            f"Provider response did not contain a valid {field_name}."
        )
    if value < 0:
        raise ProviderResponseValidationError(
            f"Provider response contained a negative {field_name}."
        )
    return value


def validate_token_usage(
    input_tokens,
    cached_input_tokens,
    output_tokens,
    *,
    allow_all_missing=False,
):
    values = (input_tokens, cached_input_tokens, output_tokens)
    if allow_all_missing and all(value is None for value in values):
        return 0, 0, 0

    input_tokens = _validated_token_count(input_tokens, "input token count")
    cached_input_tokens = _validated_token_count(
        cached_input_tokens, "cached-input token count"
    )
    output_tokens = _validated_token_count(output_tokens, "output token count")
    if cached_input_tokens > input_tokens:
        raise ProviderResponseValidationError(
            "Provider cached-input tokens exceed total input tokens."
        )
    return input_tokens, cached_input_tokens, output_tokens


def validate_response_text(text, *, allow_empty=False):
    if not isinstance(text, str):
        raise ProviderResponseValidationError(
            "Provider response did not contain text in the expected shape."
        )
    if not allow_empty and not text.strip():
        raise ProviderResponseValidationError(
            "Provider response contained empty generated text."
        )
    return text


def validate_provider_request_id(request_id, *, required=False):
    if not isinstance(request_id, str):
        raise ProviderResponseValidationError(
            "Provider request identifier was not a string."
        )
    if required and not request_id:
        raise ProviderResponseValidationError(
            "Provider response did not contain a request identifier."
        )
    if len(request_id) > 255:
        raise ProviderResponseValidationError(
            "Provider request identifier exceeds the ledger field length."
        )
    return request_id
