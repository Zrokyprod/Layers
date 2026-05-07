"""Tests for AI integration services."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.embedding_service import EmbeddingService
from app.services.nl_analytics import NLAnalyticsService
from app.services.predictive_cost import PredictiveCostService


class TestEmbeddingService:
    """Tests for embedding service."""

    def test_prepare_embedding_text(self):
        """Test preparing text for embedding."""
        service = EmbeddingService(api_key="test-key")
        
        text = service.prepare_embedding_text(
            diagnosis_type="TOKEN_OVERFLOW",
            error_message="Context length exceeded",
            code_snippet="messages = [...]",
            fix_diff="--- BEFORE ---\ncode\n--- AFTER ---\nfixed",
        )
        
        assert "Diagnosis: TOKEN_OVERFLOW" in text
        assert "Error: Context length exceeded" in text
        assert "Code:" in text
        assert "Fix:" in text

    def test_prepare_embedding_text_minimal(self):
        """Test preparing text with minimal data."""
        service = EmbeddingService(api_key="test-key")
        
        text = service.prepare_embedding_text(
            diagnosis_type="RATE_LIMIT",
            error_message=None,
            code_snippet=None,
            fix_diff=None,
        )
        
        assert text == "Diagnosis: RATE_LIMIT"

    @patch("app.services.embedding_service.OpenAI")
    def test_generate_embedding_success(self, mock_openai):
        """Test successful embedding generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        service = EmbeddingService(api_key="test-key")
        embedding = service.generate_embedding("test text")
        
        assert embedding == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once()

    @patch("app.services.embedding_service.OpenAI")
    def test_generate_embedding_failure(self, mock_openai):
        """Test embedding generation failure."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        service = EmbeddingService(api_key="test-key")
        embedding = service.generate_embedding("test text")
        
        assert embedding is None


class TestPredictiveCostService:
    """Tests for predictive cost service."""

    def test_calculate_ewma(self):
        """Test EWMA calculation."""
        service = PredictiveCostService()
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        ewma = service.calculate_ewma(data, span=3)
        
        assert len(ewma) == len(data)
        assert ewma[0] == 1.0  # First value unchanged
        assert ewma[-1] > 3.0  # Last value should be smoothed upward

    def test_detect_trend_increasing(self):
        """Test trend detection for increasing data."""
        service = PredictiveCostService()
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        
        trend = service.detect_trend(data)
        
        assert trend["trend"] == "increasing"
        assert trend["slope"] > 0

    def test_detect_trend_stable(self):
        """Test trend detection for stable data."""
        service = PredictiveCostService()
        data = [5.0, 5.1, 4.9, 5.0, 5.2, 4.8, 5.1, 5.0]
        
        trend = service.detect_trend(data)
        
        assert trend["trend"] == "stable"

    def test_get_recommendation_high_risk(self):
        """Test recommendation for high risk."""
        service = PredictiveCostService()
        rec = service._get_recommendation("high", ["predicted_double_baseline"])
        
        assert "Urgent" in rec
        assert "cost spike" in rec.lower()

    def test_get_recommendation_normal(self):
        """Test recommendation for normal risk."""
        service = PredictiveCostService()
        rec = service._get_recommendation("normal", [])
        
        assert "Normal" in rec


class TestNLAnalyticsService:
    """Tests for natural language analytics service."""

    def test_parse_time_range_last_hour(self):
        """Test parsing last hour time range."""
        service = NLAnalyticsService(api_key="test-key")
        
        result = service._parse_time_range("last_hour")
        
        assert "from" in result
        assert "to" in result
        # Should be approximately 1 hour ago
        from_time = datetime.fromisoformat(result["from"])
        to_time = datetime.fromisoformat(result["to"])
        assert (to_time - from_time).total_seconds() >= 3600

    def test_parse_time_range_today(self):
        """Test parsing today time range."""
        service = NLAnalyticsService(api_key="test-key")
        
        result = service._parse_time_range("today")
        
        assert "from" in result
        assert "to" in result
        from_time = datetime.fromisoformat(result["from"])
        assert from_time.hour == 0

    def test_parse_time_range_specific_date(self):
        """Test parsing specific date."""
        service = NLAnalyticsService(api_key="test-key")
        
        result = service._parse_time_range("2024-01-15")
        
        assert "from" in result
        assert "2024-01-15" in result["from"]

    @patch("app.services.nl_analytics.OpenAI")
    def test_parse_query_success(self, mock_openai):
        """Test successful query parsing."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"intent": "query", "entity_type": "calls", "time_range": "last_24h", "filters": [{"field": "status", "op": "eq", "value": "failed"}], "aggregation": {"type": "count"}}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        service = NLAnalyticsService(api_key="test-key")
        result = service.parse_query("How many failed calls in the last 24 hours?")
        
        assert "error" not in result
        assert result["intent"] == "query"
        assert result["entity_type"] == "calls"

    @patch("app.services.nl_analytics.OpenAI")
    def test_parse_query_failure(self, mock_openai):
        """Test query parsing failure."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client
        
        service = NLAnalyticsService(api_key="test-key")
        result = service.parse_query("Show me calls")
        
        assert "error" in result

    def test_generate_response_aggregation(self):
        """Test generating response for aggregation result."""
        service = NLAnalyticsService(api_key="test-key")
        results = {
            "type": "aggregation",
            "aggregation": {"type": "count"},
            "value": 42,
        }
        
        response = service.generate_response("How many calls?", results)
        
        assert "42" in response["answer"]
        assert response["data"] == results

    def test_generate_response_list(self):
        """Test generating response for list result."""
        service = NLAnalyticsService(api_key="test-key")
        results = {
            "type": "list",
            "count": 10,
            "data": [{"id": "1"}, {"id": "2"}],
        }
        
        response = service.generate_response("Show calls", results)
        
        assert "10" in response["answer"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
