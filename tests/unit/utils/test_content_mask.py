"""Tests for content masking/verification utility (mask service)."""

from unittest.mock import MagicMock, patch

import requests

from mcp_atlassian.utils.content_mask import (
    get_content_mask_service_url,
    mask_confluence_comment_dict,
    mask_confluence_diff_result,
    mask_confluence_page_dict,
    mask_issue_content,
    mask_page_content,
    mask_text,
)


class TestGetContentMaskServiceUrl:
    """Test get_content_mask_service_url."""

    def test_returns_none_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert get_content_mask_service_url() is None

    def test_returns_none_when_empty(self):
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": ""}):
            assert get_content_mask_service_url() is None

    def test_returns_url_when_set(self):
        url = "https://apis.example.com/mask/chat"
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": url}):
            assert get_content_mask_service_url() == url

    def test_strips_whitespace(self):
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "  https://mask.example.com  "}):
            assert get_content_mask_service_url() == "https://mask.example.com"


class TestMaskText:
    """Test mask_text with mocked HTTP."""

    def test_returns_original_when_url_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert mask_text("secret data") == "secret data"

    def test_returns_original_when_text_empty(self):
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            assert mask_text("") == ""
            assert mask_text("   ") == "   "

    @patch("mcp_atlassian.utils.content_mask.requests.post")
    def test_returns_masked_from_response(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"text": "MASKED"},
            raise_for_status=MagicMock(),
        )
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = mask_text("original")
        assert result == "MASKED"
        mock_post.assert_called_once()
        call_kw = mock_post.call_args[1]
        assert call_kw["json"] == {"text": "original"}
        assert "application/json" in str(call_kw["headers"].get("Content-Type", ""))

    @patch("mcp_atlassian.utils.content_mask.requests.post")
    def test_returns_original_on_http_error(self, mock_post):
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status.side_effect = requests.HTTPError("500")
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = mask_text("original")
        assert result == "original"

    @patch("mcp_atlassian.utils.content_mask.requests.post")
    def test_returns_original_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.RequestException("Connection failed")
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = mask_text("original")
        assert result == "original"

    @patch("mcp_atlassian.utils.content_mask.requests.post")
    def test_returns_masked_from_nested_mask_response(self, mock_post):
        """Service returns {'masked_data': {'masked_text': '...'}} (mai-ms-masking-it-proxy)."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "masked_data": {
                    "text": "original",
                    "masked_text": "{PERSON_1} родился {DATE_1}",
                    "masks_dict": {"{PERSON_1}": "Иван", "{DATE_1}": "01.01.1990"},
                    "timing_steps": {"step1": 0.1},
                }
            },
            raise_for_status=MagicMock(),
        )
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = mask_text("original")
        assert result == "{PERSON_1} родился {DATE_1}"

    @patch("mcp_atlassian.utils.content_mask.requests.post")
    def test_returns_original_when_response_missing_text_key(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"other": "value"},
            raise_for_status=MagicMock(),
        )
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = mask_text("original")
        assert result == "original"


class TestMaskIssueContent:
    """Test mask_issue_content."""

    def test_no_op_when_url_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            result = {"description": "desc", "comments": [{"body": "c1"}]}
            out = mask_issue_content(result)
            assert out["description"] == "desc"
            assert out["comments"][0]["body"] == "c1"

    @patch("mcp_atlassian.utils.content_mask.mask_text")
    def test_masks_description_and_comments_when_url_set(self, mock_mask_text):
        def side_effect(t):
            return f"MASKED({t})"

        mock_mask_text.side_effect = side_effect
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://mask.example.com"}):
            result = {
                "description": "issue desc",
                "comments": [{"body": "comment one"}, {"body": "comment two"}],
            }
            mask_issue_content(result)
        assert result["description"] == "MASKED(issue desc)"
        assert result["comments"][0]["body"] == "MASKED(comment one)"
        assert result["comments"][1]["body"] == "MASKED(comment two)"


class TestMaskPageContent:
    """Test mask_page_content (alias for mask_text)."""

    @patch("mcp_atlassian.utils.content_mask.mask_text")
    def test_delegates_to_mask_text(self, mock_mask_text):
        mock_mask_text.return_value = "masked"
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://x.com"}):
            assert mask_page_content("page body") == "masked"
        mock_mask_text.assert_called_once_with("page body")


class TestMaskConfluencePageDict:
    """Test mask_confluence_page_dict."""

    def test_no_op_when_url_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            result = {"content": {"value": "page text", "format": "markdown"}}
            mask_confluence_page_dict(result)
            assert result["content"]["value"] == "page text"

    @patch("mcp_atlassian.utils.content_mask.mask_text")
    def test_masks_content_value_when_url_set(self, mock_mask_text):
        mock_mask_text.return_value = "MASKED"
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://x.com"}):
            result = {"content": {"value": "raw", "format": "markdown"}}
            mask_confluence_page_dict(result)
        assert result["content"]["value"] == "MASKED"


class TestMaskConfluenceCommentDict:
    """Test mask_confluence_comment_dict."""

    @patch("mcp_atlassian.utils.content_mask.mask_text")
    def test_masks_body_when_url_set(self, mock_mask_text):
        mock_mask_text.return_value = "MASKED_BODY"
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://x.com"}):
            comment = {"body": "comment text"}
            mask_confluence_comment_dict(comment)
        assert comment["body"] == "MASKED_BODY"


class TestMaskConfluenceDiffResult:
    """Test mask_confluence_diff_result."""

    @patch("mcp_atlassian.utils.content_mask.mask_text")
    def test_masks_diff_field_when_url_set(self, mock_mask_text):
        mock_mask_text.return_value = "MASKED_DIFF"
        with patch.dict("os.environ", {"CONTENT_MASK_SERVICE_URL": "https://x.com"}):
            result = {"diff": "line1\nline2", "page_id": "123"}
            mask_confluence_diff_result(result)
        assert result["diff"] == "MASKED_DIFF"
