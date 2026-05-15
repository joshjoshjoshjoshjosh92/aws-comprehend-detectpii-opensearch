"""Unit tests for PII detection and redaction logic."""
import os
import sys
import time
from unittest.mock import patch, MagicMock

# Set required env var before importing config
os.environ.setdefault("OPENSEARCH_ENDPOINT", "test-endpoint.us-east-1.es.amazonaws.com")

import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pii_processor import redact_text, contains_pii, detect_pii, process_document


class TestRedactText:
    def test_single_entity(self):
        text = "My name is John Smith and I live here."
        entities = [{"BeginOffset": 11, "EndOffset": 21, "Type": "NAME", "Score": 0.99}]
        result = redact_text(text, entities)
        assert result == "My name is [NAME] and I live here."

    def test_multiple_entities(self):
        text = "John Smith SSN 123-45-6789"
        entities = [
            {"BeginOffset": 0, "EndOffset": 10, "Type": "NAME", "Score": 0.99},
            {"BeginOffset": 15, "EndOffset": 26, "Type": "SSN", "Score": 0.99},
        ]
        result = redact_text(text, entities)
        assert result == "[NAME] SSN [SSN]"

    def test_no_entities(self):
        text = "This is clean text."
        result = redact_text(text, [])
        assert result == "This is clean text."

    def test_adjacent_entities(self):
        text = "JohnSmith"
        entities = [
            {"BeginOffset": 0, "EndOffset": 4, "Type": "NAME", "Score": 0.99},
            {"BeginOffset": 4, "EndOffset": 9, "Type": "NAME", "Score": 0.99},
        ]
        result = redact_text(text, entities)
        assert result == "[NAME][NAME]"

    def test_entity_at_end(self):
        text = "Contact: john@example.com"
        entities = [{"BeginOffset": 9, "EndOffset": 25, "Type": "EMAIL", "Score": 0.99}]
        result = redact_text(text, entities)
        assert result == "Contact: [EMAIL]"


class TestContainsPii:
    @patch("pii_processor._get_comprehend")
    def test_returns_true_when_pii_found(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.contains_pii_entities.return_value = {
            "Labels": [{"Name": "NAME", "Score": 0.95}]
        }
        mock_comprehend.return_value = mock_client

        assert contains_pii("John Smith lives here") is True

    @patch("pii_processor._get_comprehend")
    def test_returns_false_when_clean(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.contains_pii_entities.return_value = {"Labels": []}
        mock_comprehend.return_value = mock_client

        assert contains_pii("Q4 planning meeting moved to Thursday") is False

    @patch("pii_processor._get_comprehend")
    def test_respects_confidence_threshold(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.contains_pii_entities.return_value = {
            "Labels": [{"Name": "NAME", "Score": 0.3}]  # Below 0.7 threshold
        }
        mock_comprehend.return_value = mock_client

        assert contains_pii("Maybe a name maybe not") is False

    @patch("pii_processor._get_comprehend")
    def test_filters_by_entity_type(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.contains_pii_entities.return_value = {
            "Labels": [{"Name": "IP_ADDRESS", "Score": 0.99}]  # Not in default types
        }
        mock_comprehend.return_value = mock_client

        assert contains_pii("Server at 192.168.1.1") is False

    @patch("pii_processor._get_comprehend")
    def test_truncates_long_text(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.contains_pii_entities.return_value = {"Labels": []}
        mock_comprehend.return_value = mock_client

        long_text = "x" * 200_000
        contains_pii(long_text)

        # Verify the text passed to Comprehend was truncated
        call_args = mock_client.contains_pii_entities.call_args
        assert len(call_args[1]["Text"]) == 99_000


class TestDetectPii:
    @patch("pii_processor._get_comprehend")
    def test_returns_filtered_entities(self, mock_comprehend):
        mock_client = MagicMock()
        mock_client.detect_pii_entities.return_value = {
            "Entities": [
                {"Type": "NAME", "Score": 0.99, "BeginOffset": 0, "EndOffset": 10},
                {"Type": "NAME", "Score": 0.3, "BeginOffset": 15, "EndOffset": 20},  # Low confidence
                {"Type": "IP_ADDRESS", "Score": 0.99, "BeginOffset": 25, "EndOffset": 35},  # Not in types
            ]
        }
        mock_comprehend.return_value = mock_client

        result = detect_pii("John Smith and more text here")
        assert len(result) == 1
        assert result[0]["Type"] == "NAME"
        assert result[0]["Score"] == 0.99


class TestProcessDocument:
    @patch("pii_processor.contains_pii")
    def test_clean_document(self, mock_contains):
        mock_contains.return_value = False

        doc = {"title": "Clean Memo", "body": "Q4 planning meeting moved to Thursday. No action items."}
        result = process_document(doc, mode="REDACT")

        assert result["pii_flag"] is False
        assert result["pii_count"] == 0
        assert result["pii_types"] == []
        assert "pii_scanned_at" in result

    @patch("pii_processor.detect_pii")
    @patch("pii_processor.contains_pii")
    def test_pii_document_redact_mode(self, mock_contains, mock_detect):
        mock_contains.return_value = True
        mock_detect.return_value = [
            {"Type": "NAME", "Score": 0.99, "BeginOffset": 12, "EndOffset": 22}
        ]

        doc = {"title": "Short title", "body": "Contact is John Smith for details on the account."}
        result = process_document(doc, mode="REDACT")

        assert result["pii_flag"] is True
        assert result["pii_count"] == 1
        assert "NAME" in result["pii_types"]
        assert "[NAME]" in result["body"]

    @patch("pii_processor.detect_pii")
    @patch("pii_processor.contains_pii")
    def test_pii_document_flag_mode(self, mock_contains, mock_detect):
        mock_contains.return_value = True
        mock_detect.return_value = [
            {"Type": "SSN", "Score": 0.99, "BeginOffset": 4, "EndOffset": 15}
        ]

        doc = {"title": "Short title", "body": "SSN 123-45-6789 is on file for this customer."}
        result = process_document(doc, mode="FLAG")

        assert result["pii_flag"] is True
        assert "SSN" in result["pii_types"]
        # In FLAG mode, text should NOT be redacted
        assert "123-45-6789" in result["body"]

    @patch("pii_processor.contains_pii")
    def test_skips_short_fields(self, mock_contains):
        mock_contains.return_value = False

        doc = {"id": "12345", "short": "hi", "body": "This is a longer field that gets checked for PII content."}
        result = process_document(doc)

        # "id" and "short" are < 20 chars, should not be included in text_fields
        assert result["pii_flag"] is False

    @patch("pii_processor.contains_pii")
    def test_scanned_at_timestamp_format(self, mock_contains):
        mock_contains.return_value = False

        doc = {"body": "Some text that is long enough to be checked by the processor."}
        result = process_document(doc)

        # Verify ISO 8601 format
        ts = result["pii_scanned_at"]
        assert ts.endswith("Z")
        assert "T" in ts
        time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
