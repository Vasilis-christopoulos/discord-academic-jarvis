# tests/test_reranker.py
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document
from utils.reranker_calendar import rerank_llm, _clean

class TestCleanFunction:
    """Test the text cleaning utility function."""
    
    def test_clean_html_tags(self):
        """Test HTML tag removal."""
        text = "This has <b>bold</b> and <i>italic</i> text"
        result = _clean(text)
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold" in result
        assert "italic" in result
    
    def test_clean_links_preserved(self):
        """Test that markdown links are preserved."""
        text = '<a href="https://example.com">Example Link</a>'
        result = _clean(text) 
        assert "[Example Link](https://example.com)" in result
    
    def test_clean_newlines_collapsed(self):
        """Test that newlines are collapsed to spaces."""
        text = "Line 1\nLine 2\n\nLine 3"
        result = _clean(text)
        assert "\n" not in result
        assert "Line 1 Line 2" in result
    
    def test_clean_length_limit(self):
        """Test that text is truncated to max_tokens."""
        long_text = "a" * 1000  # Very long text
        result = _clean(long_text, max_tokens=10)
        assert len(result) <= 40 + 1  # 10 tokens * 4 chars + ellipsis
        assert result.endswith("…")
    
    def test_clean_short_text_no_truncation(self):
        """Test that short text is not truncated."""
        short_text = "Short text"
        result = _clean(short_text, max_tokens=100)
        assert result == short_text
        assert not result.endswith("…")

class TestRerankerLLM:
    """Test the LLM-based reranking functionality."""
    
    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        docs = [
            Document(
                page_content="Team Meeting\nDiscuss project progress and next steps",
                metadata={
                    "id": "event1",
                    "type": "event", 
                    "start_dt": "2025-05-28T10:00:00"
                }
            ),
            Document(
                page_content="Math Assignment\nComplete exercises 1-10",
                metadata={
                    "id": "task1",
                    "type": "task",
                    "start_dt": "2025-05-30T23:59:59"
                }
            ),
            Document(
                page_content="Conference Call\nQuarterly review with stakeholders", 
                metadata={
                    "id": "event2",
                    "type": "event",
                    "start_dt": "2025-05-29T14:00:00"
                }
            )
        ]
        return docs
    
    def test_rerank_formats_correctly(self, sample_documents):
        """Test that documents are formatted correctly for LLM."""
        query = "What meetings do I have?"
        
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = "[0, 2]"  # Return first and third docs
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            # Check that LLM was called
            mock_llm.invoke.assert_called_once()
            call_args = mock_llm.invoke.call_args[0][0]
            
            # Verify the prompt contains formatted documents
            assert "Team Meeting" in call_args
            assert "🗓 EVENT" in call_args
            assert "✅ TASK" in call_args
            assert query in call_args
    
    def test_rerank_returns_reordered_docs(self, sample_documents):
        """Test that documents are returned in LLM-specified order."""
        query = "meetings"
        
        # Mock LLM to return specific order
        mock_response = MagicMock()
        mock_response.content = "[2, 0]"  # Return docs in reverse order
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            assert len(result) == 2
            assert result[0].metadata["id"] == "event2"  # Third doc first
            assert result[1].metadata["id"] == "event1"  # First doc second
    
    def test_rerank_handles_invalid_json(self, sample_documents):
        """Test handling of invalid JSON response from LLM."""
        query = "test query"
        
        # Mock LLM to return invalid JSON
        mock_response = MagicMock()
        mock_response.content = "invalid json response"
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            # Should return original documents when JSON parsing fails
            assert result == sample_documents
    
    def test_rerank_handles_out_of_bounds_indices(self, sample_documents):
        """Test handling of out-of-bounds indices from LLM."""
        query = "test query"
        
        # Mock LLM to return indices including out-of-bounds
        mock_response = MagicMock()
        mock_response.content = "[0, 5, 1]"  # Index 5 is out of bounds
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            # Should only return valid indices
            assert len(result) == 2
            assert result[0].metadata["id"] == "event1"  # Index 0
            assert result[1].metadata["id"] == "task1"   # Index 1
    
    def test_rerank_limits_input_documents(self):
        """Test that input is limited to 20 documents."""
        # Create 25 documents
        docs = []
        for i in range(25):
            docs.append(Document(
                page_content=f"Doc {i}\nContent {i}",
                metadata={"id": f"doc{i}", "type": "event", "start_dt": "2025-05-28T10:00:00"}
            ))
        
        mock_response = MagicMock()
        mock_response.content = "[]"
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            rerank_llm("test", docs)
            
            # Check that prompt only contains first 20 docs
            call_args = mock_llm.invoke.call_args[0][0]
            assert "[19]" in call_args  # 20th document (0-indexed)
            assert "[20]" not in call_args  # 21st document should not be included

    def test_rerank_returns_empty_list(self, sample_documents):
        """Test that reranker can return empty list (all documents rejected)."""
        query = "irrelevant query"
        
        # Mock LLM to return empty list (all documents rejected)
        mock_response = MagicMock()
        mock_response.content = "[]"
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            assert result == []
            assert len(result) == 0

    def test_rerank_handles_empty_input(self):
        """Test reranker behavior with empty document list."""
        query = "test query"
        empty_docs = []
        
        # Should return empty list immediately without calling LLM
        with patch('utils.reranker_calendar._llm') as mock_llm:
            result = rerank_llm(query, empty_docs)
            
            assert result == []
            mock_llm.invoke.assert_not_called()

    def test_rerank_partial_selection(self, sample_documents):
        """Test reranker selecting subset of documents."""
        query = "meetings only"
        
        # Mock LLM to return only event documents (indices 0 and 2)
        mock_response = MagicMock()
        mock_response.content = "[0, 2]"
        
        with patch('utils.reranker_calendar._llm') as mock_llm:
            mock_llm.invoke.return_value = mock_response
            
            result = rerank_llm(query, sample_documents)
            
            assert len(result) == 2
            assert all(doc.metadata["type"] == "event" for doc in result)
            assert result[0].metadata["id"] == "event1"
            assert result[1].metadata["id"] == "event2"
