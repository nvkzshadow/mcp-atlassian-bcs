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

# Expected response key for masked text (API contract)
MASK_RESPONSE_TEXT_KEY = "text"


def get_content_mask_service_url() -> str | None:
    """Return the content mask service URL from environment.

    Returns:
        URL string if CONTENT_MASK_SERVICE_URL is set and non-empty, None otherwise.
    """
    url = os.getenv("CONTENT_MASK_SERVICE_URL")
    if not url or not str(url).strip():
        return None
    return str(url).strip()


def mask_text(text: str) -> str:
    """Send text to the mask service and return the response (or original on failure).

    If CONTENT_MASK_SERVICE_URL is not set, or text is empty, returns the original text.
    On HTTP/network error or invalid response, logs a warning and returns the original text.

    Args:
        text: Raw text content to send for masking.

    Returns:
        Masked text from the service, or the original text if masking is disabled or fails.
    """
    url = get_content_mask_service_url()
    if not url:
        return text
    if not text or not text.strip():
        return text

    try:
        response = requests.post(
            url,
            json={"text": text},
            headers={"Content-Type": "application/json"},
            timeout=MASK_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and MASK_RESPONSE_TEXT_KEY in data:
            return str(data[MASK_RESPONSE_TEXT_KEY])
        # Fallback: some APIs return the masked string at top level
        if isinstance(data, str):
            return data
        logger.warning(
            "Content mask service response missing expected key %r: %s",
            MASK_RESPONSE_TEXT_KEY,
            type(data).__name__,
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

    if result.get("description") and isinstance(result["description"], str):
        result["description"] = mask_text(result["description"])

    comments = result.get("comments")
    if isinstance(comments, list):
        for comment in comments:
            if isinstance(comment, dict) and comment.get("body") is not None:
                comment["body"] = mask_text(str(comment["body"]))

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
        content_obj["value"] = mask_text(str(content_obj["value"]))
    return result


def mask_confluence_comment_dict(comment: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to a single Confluence comment dict (body field)."""
    if get_content_mask_service_url() is None:
        return comment
    if comment.get("body") is not None:
        comment["body"] = mask_text(str(comment["body"]))
    return comment


def mask_confluence_diff_result(result: dict[str, Any]) -> dict[str, Any]:
    """Apply content masking to get_page_version_diff result (diff field)."""
    if get_content_mask_service_url() is None:
        return result
    if result.get("diff") is not None:
        result["diff"] = mask_text(str(result["diff"]))
    return result
