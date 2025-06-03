# tests/test_handlers.py
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio

class TestRAGHandler:
    """Test RAG module handler."""
    
    async def test_rag_respond_basic(self):
        """Test basic RAG response functionality."""
        from rag_module.rag_handler import respond as rag_respond
        
        context = {"name": "test-channel", "type": "rag"}
        query = "What is machine learning?"
        
        result = await rag_respond(query, context)
        
        # Since it's a stub implementation, check the format
        assert isinstance(result, str)
        assert "RAG ANSWER" in result
        assert query in result

class TestCalendarHandler:
    """Test Calendar module handler - integration test."""
    
    @pytest.fixture
    def mock_context(self):
        """Mock context for calendar tests."""
        return {
            "guild_id": 111,
            "name": "test-channel",
            "type": "calendar",
            "timezone": "America/Toronto",
            "calendar_id": "test@example.com",
            "tasklist_id": "test123"
        }
    
    async def test_non_applicable_query(self, mock_context):
        """Test calendar handler with non-applicable query."""
        from calendar_module.calendar_handler import respond as cal_respond
        
        # Mock the parse_query to return non-applicable
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse:
            mock_parse.return_value.applicable = False
            
            result = await cal_respond("How are you?", mock_context)
            
            assert "not applicable" in result.lower()
    
    async def test_empty_results(self, mock_context):
        """Test calendar handler with no search results."""
        from calendar_module.calendar_handler import respond as cal_respond
        
        # Mock all the dependencies
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse, \
             patch('calendar_module.calendar_handler.delta_sync_calendar') as mock_delta_cal, \
             patch('calendar_module.calendar_handler.delta_sync_tasks') as mock_delta_tasks, \
             patch('calendar_module.calendar_handler.ensure_synced') as mock_sync, \
             patch('calendar_module.calendar_handler.hybrid_search_relative_band') as mock_search:
            
            # Setup mocks
            mock_parse.return_value.applicable = True
            mock_parse.return_value.type = "event"
            mock_parse.return_value.date_from = "2025-05-28T00:00:00-04:00"
            mock_parse.return_value.date_to = "2025-06-28T23:59:59-04:00"
            mock_parse.return_value.filter = "meeting"
            mock_parse.return_value.limit = 10
            
            mock_search.return_value = []  # No results
            
            result = await cal_respond("meeting today", mock_context)
            
            assert "No results found" in result

class TestFallbackHandler:
    """Test Fallback module handler."""
    
    async def test_fallback_respond_basic(self):
        """Test basic fallback response functionality."""
        from fallback_module.fallback_handler import respond as fb_respond
        
        context = {"name": "test-channel", "type": "fallback"}
        query = "How are you today?"
        
        result = await fb_respond(query, context)
        
        # Since it's a stub implementation, check the format
        assert isinstance(result, str)
        assert "FALLBACK ANSWER" in result
        assert query in result

class TestCalendarHandlerEdgeCases:
    """Test Calendar module handler edge cases and complete pipeline scenarios."""
    
    @pytest.fixture
    def mock_context(self):
        """Mock context for calendar tests."""
        return {
            "guild_id": 111,
            "name": "test-channel",
            "type": "calendar", 
            "timezone": "America/Toronto",
            "calendar_id": "test@example.com",
            "tasklist_id": "test123"
        }

    async def test_window_only_query_no_results(self, mock_context):
        """Test window-only query (no text filter) with no matching events."""
        from calendar_module.calendar_handler import respond as cal_respond
        
        # Mock all dependencies
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse, \
             patch('calendar_module.calendar_handler.delta_sync_calendar') as mock_delta_cal, \
             patch('calendar_module.calendar_handler.delta_sync_tasks') as mock_delta_tasks, \
             patch('calendar_module.calendar_handler.ensure_synced') as mock_sync, \
             patch('calendar_module.calendar_handler._index') as mock_index:
            
            # Setup mocks for window-only query (no filter text)
            mock_parse.return_value.applicable = True
            mock_parse.return_value.type = "event"
            mock_parse.return_value.date_from = "2025-05-28T00:00:00-04:00"
            mock_parse.return_value.date_to = "2025-06-28T23:59:59-04:00"
            mock_parse.return_value.filter = ""  # Empty filter = window-only
            mock_parse.return_value.limit = 10
            
            # Mock index query to return no matches
            mock_index.query.return_value = {"matches": []}
            
            result = await cal_respond("today", mock_context)
            
            assert "No results found" in result

    async def test_semantic_search_no_candidates(self, mock_context):
        """Test semantic search when hybrid search returns no candidates."""
        from calendar_module.calendar_handler import respond as cal_respond
        
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse, \
             patch('calendar_module.calendar_handler.delta_sync_calendar') as mock_delta_cal, \
             patch('calendar_module.calendar_handler.delta_sync_tasks') as mock_delta_tasks, \
             patch('calendar_module.calendar_handler.ensure_synced') as mock_sync, \
             patch('calendar_module.calendar_handler.hybrid_search_relative_band') as mock_search:
            
            # Setup mocks for semantic search (with filter text)
            mock_parse.return_value.applicable = True
            mock_parse.return_value.type = "event"
            mock_parse.return_value.date_from = "2025-05-28T00:00:00-04:00"
            mock_parse.return_value.date_to = "2025-06-28T23:59:59-04:00"
            mock_parse.return_value.filter = "nonexistent meeting"
            mock_parse.return_value.limit = 10
            
            # Mock hybrid search to return no candidates
            mock_search.return_value = []
            
            result = await cal_respond("nonexistent meeting today", mock_context)
            
            assert "No results found" in result

    async def test_reranker_rejects_all_candidates(self, mock_context):
        """Test when reranker rejects all candidates (returns empty list)."""
        from calendar_module.calendar_handler import respond as cal_respond
        from langchain_core.documents import Document
        
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse, \
             patch('calendar_module.calendar_handler.delta_sync_calendar') as mock_delta_cal, \
             patch('calendar_module.calendar_handler.delta_sync_tasks') as mock_delta_tasks, \
             patch('calendar_module.calendar_handler.ensure_synced') as mock_sync, \
             patch('calendar_module.calendar_handler.hybrid_search_relative_band') as mock_search, \
             patch('calendar_module.calendar_handler.rerank_llm') as mock_rerank:
            
            # Setup mocks
            mock_parse.return_value.applicable = True
            mock_parse.return_value.type = "event"
            mock_parse.return_value.date_from = "2025-05-28T00:00:00-04:00"
            mock_parse.return_value.date_to = "2025-06-28T23:59:59-04:00"
            mock_parse.return_value.filter = "irrelevant query"
            mock_parse.return_value.limit = 10
            
            # Mock hybrid search to return some candidates
            mock_candidates = [
                Document(
                    page_content="Meeting Title\nMeeting description",
                    metadata={"id": "event1", "type": "event"}
                )
            ]
            mock_search.return_value = mock_candidates
            
            # Mock reranker to reject all candidates
            mock_rerank.return_value = []
            
            result = await cal_respond("irrelevant query today", mock_context)
            
            assert "No results found" in result

    async def test_single_weak_match_pipeline(self, mock_context):
        """Test complete pipeline with single weak match that gets filtered."""
        from calendar_module.calendar_handler import respond as cal_respond
        from langchain_core.documents import Document
        
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse, \
             patch('calendar_module.calendar_handler.delta_sync_calendar') as mock_delta_cal, \
             patch('calendar_module.calendar_handler.delta_sync_tasks') as mock_delta_tasks, \
             patch('calendar_module.calendar_handler.ensure_synced') as mock_sync, \
             patch('calendar_module.calendar_handler.hybrid_search_relative_band') as mock_search, \
             patch('calendar_module.calendar_handler.rerank_llm') as mock_rerank:
            
            # Setup mocks
            mock_parse.return_value.applicable = True
            mock_parse.return_value.type = "event"
            mock_parse.return_value.date_from = "2025-05-28T00:00:00-04:00"
            mock_parse.return_value.date_to = "2025-06-28T23:59:59-04:00"
            mock_parse.return_value.filter = "vague query"
            mock_parse.return_value.limit = 10
            
            # Mock hybrid search returns one weak candidate (but passes through)
            mock_candidates = [
                Document(
                    page_content="Somewhat Related\nWeak match content",
                    metadata={"id": "event1", "type": "event"}
                )
            ]
            mock_search.return_value = mock_candidates
            
            # Mock reranker to reject the weak candidate
            mock_rerank.return_value = []
            
            result = await cal_respond("vague query", mock_context)
            
            assert "No results found" in result

    async def test_empty_query_edge_case(self, mock_context):
        """Test handling of completely empty queries."""
        from calendar_module.calendar_handler import respond as cal_respond
        
        with patch('calendar_module.calendar_handler.parse_query') as mock_parse:
            # Mock parser to return non-applicable for empty query
            mock_parse.return_value.applicable = False
            
            result = await cal_respond("", mock_context)
            
            assert "not applicable" in result.lower()
