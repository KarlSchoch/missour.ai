"""Provider-response helpers shared by billable model-call integrations."""

import os


def is_simulated_model_environment():
    return os.getenv("MODEL_ENV", "").lower() == "dev"


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
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def provider_request_id(response):
    raw = raw_response(response)
    response_metadata = getattr(raw, "response_metadata", {}) or {}
    return str(
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
        input_tokens = provider_usage.get("prompt_tokens", 0)
    output_tokens = usage.get("output_tokens")
    if output_tokens is None:
        output_tokens = provider_usage.get("completion_tokens", 0)

    input_details = usage.get("input_token_details", {}) or {}
    prompt_details = provider_usage.get("prompt_tokens_details", {}) or {}
    cached_tokens = input_details.get("cache_read")
    if cached_tokens is None:
        cached_tokens = input_details.get("cached_tokens")
    if cached_tokens is None:
        cached_tokens = prompt_details.get("cached_tokens", 0)

    return int(input_tokens or 0), int(cached_tokens or 0), int(output_tokens or 0)
