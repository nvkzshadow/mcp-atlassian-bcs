"""Content masking/verification via external mask service.

When CONTENT_MASK_SERVICE_URL is set, text content from Jira and Confluence
is sent to the service before being returned to the client. The service
returns masked/sanitized text which is substituted in the response.
"""

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Timeout for mask service HTTP request (seconds)
MASK_REQUEST_TIMEOUT = 30

# Expected response key for masked text (API contract); try in order.
# mai-ms-masking-it-proxy returns {"masked_data": {"masked_text": "...", "text": "...", "masks_dict": ..., "timing_steps": ...}}
MASK_RESPONSE_TEXT_KEYS = ("text", "masked_text", "maskedText", "result", "data", "content", "output")
MASKED_DATA_NESTED_KEY = "masked_data"  # nested object with masked_text

# Max length of text values in log
_LOG_TEXT_MAX = 500
# Max length of full request/response log (to avoid huge log files)
_LOG_FULL_MAX = 20_000
# Max length of response string in the single "full response" log line (avoid handler/encoding issues)
_LOG_RESPONSE_INLINE_MAX = 3000

# Placeholder when mask service is not used for a user (e.g. Unassigned)
MASKED_USER_PLACEHOLDER = "[masked]"


def _mask_user_dict_via_service(
    user: dict[str, Any],
    *,
    author: dict[str, Any] | None,
    assignee: dict[str, Any] | None,
    api_payload: dict[str, Any],
) -> dict[str, Any]:
    """Mask user (reporter/assignee/comment author) via the mask service; return updated user dict."""
    text = (
        (user.get("display_name") or user.get("name") or user.get("email")) or ""
    )
    text = str(text).strip()
    if not text:
        out = dict(user)
        for key in ("display_name", "name", "email", "key", "username", "account_id", "avatar_url"):
            if key in out and out[key] is not None and str(out[key]).strip():
                out[key] = MASKED_USER_PLACEHOLDER
        return out
    masked = mask_text(
        text,
        author=author,
        assignee=assignee,
        api_payload=api_payload,
    )
    out = dict(user)
    out["display_name"] = masked
    out["name"] = masked
    if "email" in out and out["email"]:
        out["email"] = masked
    for key in ("key", "username", "account_id", "avatar_url"):
        if key in out and out[key] is not None and str(out[key]).strip():
            out[key] = MASKED_USER_PLACEHOLDER
    return out


def _flush_log_handlers() -> None:
    """Flush root logger handlers so request/response logs appear in file immediately."""
    for h in logging.getLogger().handlers:
        if hasattr(h, "flush"):
            h.flush()


def _build_log_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Build a copy of the response safe for logging (truncate long text, trim timing)."""
    log_payload = dict(data)
    nested = log_payload.get(MASKED_DATA_NESTED_KEY)
    if isinstance(nested, dict):
        nested_copy = dict(nested)
        for key in ("masked_text", "text"):
            if key in nested_copy and isinstance(nested_copy[key], str):
                s = nested_copy[key]
                nested_copy[key] = s[:_LOG_TEXT_MAX] + "..." if len(s) > _LOG_TEXT_MAX else s
        if "timing_steps" in nested_copy:
            nested_copy["timing_steps"] = "<...>"
        if "masks_dict" in nested_copy:
            nested_copy["masks_dict"] = dict(list(nested_copy["masks_dict"].items())[:5]) if isinstance(nested_copy["masks_dict"], dict) else "<...>"
        log_payload[MASKED_DATA_NESTED_KEY] = nested_copy
    else:
        for key in MASK_RESPONSE_TEXT_KEYS:
            if key in log_payload and isinstance(log_payload[key], str):
                s = log_payload[key]
                log_payload[key] = s[:_LOG_TEXT_MAX] + "..." if len(s) > _LOG_TEXT_MAX else s
                break
    return log_payload


def get_content_mask_service_url() -> str | None:
    """Return the content mask service URL from environment.

    Returns:
        URL string if CONTENT_MASK_SERVICE_URL is set and non-empty, None otherwise.
    """
    url = os.getenv("CONTENT_MASK_SERVICE_URL")
    if not url or not str(url).strip():
        return None
    return str(url).strip()


def mask_text(
    text: str,
    *,
    author: dict[str, Any] | None = None,
    assignee: dict[str, Any] | None = None,
    api_payload: dict[str, Any] | None = None,
) -> str:
    """Send text to the mask service and return the response (or original on failure).

    If CONTENT_MASK_SERVICE_URL is not set, or text is empty, returns the original text.
    On HTTP/network error or invalid response, logs a warning and returns the original text.

    Args:
        text: Raw text content to send for masking.
        author: Optional author (reporter) dict for context, e.g. from Jira issue reporter.
        assignee: Optional assignee dict for context, e.g. from Jira issue assignee.
        api_payload: Optional full JSON from Jira/Confluence API (issue, page, comment, etc.)
                     sent to the mask service as "payload" for full context.

    Returns:
        Masked text from the service, or the original text if masking is disabled or fails.
    """
    url = get_content_mask_service_url()
    if not url:
        return text
    if not text or not text.strip():
        return text

    try:
        request_body: dict[str, Any] = {"text": text}
        if author is not None:
            request_body["author"] = author
        if assignee is not None:
            request_body["assignee"] = assignee
        if api_payload is not None:
            request_body["payload"] = api_payload
        request_preview = (
            text[:_LOG_TEXT_MAX] + "..." if len(text) > _LOG_TEXT_MAX else text
        )
        try:
            logger.warning(
                "Content mask service request url=\"%s\" body.text (len=%d): \"%s\"",
                url,
                len(text),
                request_preview.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r"),
            )
        except Exception as e:
            logger.warning(
                "Content mask service request log failed: %s (url=%s, body_len=%d)",
                e,
                url,
                len(text),
            )
        _flush_log_handlers()
        response = requests.post(
            url,
            json=request_body,
            headers={"Content-Type": "application/json"},
            timeout=MASK_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        response_str = str(data)
        response_len = len(response_str)
        if response_len > _LOG_RESPONSE_INLINE_MAX:
            response_str = (
                response_str[:_LOG_RESPONSE_INLINE_MAX] + "... [truncated]"
            )
        try:
            logger.warning(
                "Content mask service full response (len=%d): \"%s\"",
                response_len,
                response_str.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r"),
            )
        except Exception as e:
            logger.warning(
                "Content mask service response log failed: %s (response_len=%d)",
                e,
                response_len,
            )
        _flush_log_handlers()
        if isinstance(data, dict):
            log_payload = _build_log_payload(data)
            logger.info("Content mask service response: %s", log_payload)
        else:
            logger.info(
                "Content mask service response (raw): %s", str(data)[:500]
            )
        if isinstance(data, dict):
            # Nested format: {"masked_data": {"masked_text": "...", "text": "..."}} (mai-ms-masking-it-proxy)
            # MCP result must be the masking service result: return masked_text as the canonical response.
            masked_data = data.get(MASKED_DATA_NESTED_KEY)
            if isinstance(masked_data, dict):
                masks_dict = masked_data.get("masks_dict")
                if masks_dict is not None:
                    logger.warning(
                        "Content mask service response masks_dict: \"%s\"",
                        str(masks_dict)
                        .replace("\\", "\\\\")
                        .replace('"', '\\"')
                        .replace("\n", "\\n")
                        .replace("\r", "\\r"),
                    )
                    if isinstance(masks_dict, dict) and len(masks_dict) > 0:
                        logger.error(
                            "Content mask service masks_dict is non-empty (masked fragments): %s",
                            masks_dict,
                        )
                # Prefer masked_text — this is the masking result returned to the MCP client
                masked_text_val = masked_data.get("masked_text")
                if isinstance(masked_text_val, str):
                    return masked_text_val
                text_val = masked_data.get("text")
                if isinstance(text_val, str):
                    return text_val
            # Flat format: {"text": "..."} or similar
            for key in MASK_RESPONSE_TEXT_KEYS:
                val = data.get(key)
                if isinstance(val, str):
                    return val
                if val is not None and not isinstance(val, (dict, list)):
                    return str(val)
        # Fallback: some APIs return the masked string at top level
        if isinstance(data, str):
            return data
        logger.warning(
            "Content mask service response missing expected keys (got top-level keys: %s)",
            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return text
    except requests.RequestException as e:
        logger.warning("Content mask service request failed: %s", e)
        return text
    except (ValueError, TypeError) as e:
        logger.warning("Content mask service invalid JSON response: %s", e)
        return text


def mask_issue_content(result: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to a Jira issue simplified dict.

    Masks 'description' and each comment's 'body' in place. Returns the same dict
    (mutated) for convenience.

    Args:
        result: Simplified issue dict from JiraIssue.to_simplified_dict().

    Returns:
        The same dict with description and comment bodies replaced by masked text.
    """
    if get_content_mask_service_url() is None:
        return result

    author = result.get("reporter") if isinstance(result.get("reporter"), dict) else None
    assignee = result.get("assignee") if isinstance(result.get("assignee"), dict) else None

    if result.get("description") and isinstance(result["description"], str):
        result["description"] = mask_text(
            result["description"],
            author=author,
            assignee=assignee,
            api_payload=result,
        )

    comments = result.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, dict):
                if comment.get("body") is not None:
                    comment["body"] = mask_text(
                        str(comment["body"]),
                        author=author,
                        assignee=assignee,
                        api_payload=result,
                    )
                # Mask comment author via the mask service
                if isinstance(comment.get("author"), dict):
                    comment["author"] = _mask_user_dict_via_service(
                        comment["author"],
                        author=author,
                        assignee=assignee,
                        api_payload=result,
                    )

    # Mask reporter and assignee via the mask service (same as https://apis.tusvc.bcs.ru/mai-ms-masking-it-proxy/mask/chat)
    if isinstance(result.get("reporter"), dict):
        result["reporter"] = _mask_user_dict_via_service(
            result["reporter"],
            author=author,
            assignee=assignee,
            api_payload=result,
        )
    assignee_val = result.get("assignee")
    if isinstance(assignee_val, dict) and assignee_val.get("display_name") != "Unassigned":
        result["assignee"] = _mask_user_dict_via_service(
            assignee_val,
            author=author,
            assignee=assignee,
            api_payload=result,
        )

    return result


def mask_page_content(content: str) -> str:
    """Mask a single page or fragment content string.

    Args:
        content: Raw page/comment content.

    Returns:
        Masked content if service URL is set, else original content.
    """
    return mask_text(content)


def mask_confluence_page_dict(result: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to a Confluence page simplified dict.

    Masks result['content']['value'] if present. Modifies in place.

    Args:
        result: Simplified page dict from ConfluencePage.to_simplified_dict().

    Returns:
        The same dict with content value masked.
    """
    if get_content_mask_service_url() is None:
        return result

    content_obj = result.get("content")
    if isinstance(content_obj, dict) and "value" in content_obj:
        content_obj["value"] = mask_text(
            str(content_obj["value"]), api_payload=result
        )
    return result


def mask_confluence_comment_dict(comment: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to a single Confluence comment dict (body field)."""
    if get_content_mask_service_url() is None:
        return comment
    if comment.get("body") is not None:
        comment["body"] = mask_text(
            str(comment["body"]), api_payload=comment
        )
    return comment


def mask_confluence_diff_result(result: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to get_page_version_diff result (diff field)."""
    if get_content_mask_service_url() is None:
        return result
    if result.get("diff") is not None:
        result["diff"] = mask_text(
            str(result["diff"]), api_payload=result
        )
    return result
