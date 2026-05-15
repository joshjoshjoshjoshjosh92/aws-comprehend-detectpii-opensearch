"""Unit tests for Lambda handler event routing."""
import os
import sys
from unittest.mock import patch, MagicMock

os.environ.setdefault("OPENSEARCH_ENDPOINT", "test-endpoint.us-east-1.es.amazonaws.com")
os.environ.setdefault("OPENSEARCH_INDEX", "pii-test")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda"))

import pytest
from handler import handler


class TestHandlerRouting:
    @patch("handler.handle_s3_event")
    def test_routes_s3_event(self, mock_s3):
        mock_s3.return_value = {"processed": 1}
        event = {
            "Records": [{"eventSource": "aws:s3", "s3": {"bucket": {"name": "b"}, "object": {"key": "k"}}}]
        }
        result = handler(event, None)
        mock_s3.assert_called_once_with(event)

    @patch("handler.handle_scheduled_scan")
    def test_routes_eventbridge_schedule(self, mock_scan):
        mock_scan.return_value = {"scanned": 0, "flagged": 0}
        event = {"detail-type": "Scheduled Event", "source": "aws.events"}
        result = handler(event, None)
        mock_scan.assert_called_once_with(event)

    @patch("handler.handle_direct_invoke")
    def test_routes_direct_invoke(self, mock_direct):
        mock_direct.return_value = {"pii_flag": True, "pii_types": ["NAME"], "pii_count": 1}
        event = {"document": {"title": "Test", "body": "John Smith is here with details."}}
        result = handler(event, None)
        mock_direct.assert_called_once_with(event)

    @patch("handler.handle_direct_invoke")
    def test_routes_unknown_event_to_direct(self, mock_direct):
        mock_direct.return_value = {"pii_flag": False, "pii_types": [], "pii_count": 0}
        event = {"some": "random payload that is long enough"}
        result = handler(event, None)
        mock_direct.assert_called_once_with(event)
