# tests/test_hybrid_search.py
import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document
from utils.hybrid_search_utils import hybrid_search_relative_band, REL_KEEP

class TestHybridSearchRelativeBand:
    """Test hybrid search functionality with relative band threshold."""
    
    @pytest.fixture
    def mock_embed(self):
        """Mock embedding function."""
        embed = MagicMock()
        embed.embed_query.return_value = [0.1] * 1536  # Mock embedding vector
        return embed
    
    @pytest.fixture
    def mock_index(self):
        """Mock Pinecone index."""
        index = MagicMock()
        return index
    
    def test_hybrid_search_above_threshold(self, mock_embed, mock_index):
        """Test that results above threshold are returned."""
        # Mock query response with high scores
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.8,  # Above threshold
                    "metadata": {
                        "text": "High relevance document",
                        "id": "doc1",
                        "type": "event"
                    }
                },
                {
                    "score": 0.6,  # Above threshold
                    "metadata": {
                        "text": "Medium relevance document", 
                        "id": "doc2",
                        "type": "task"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        assert len(result) == 2
        assert all(isinstance(doc, Document) for doc in result)
        assert result[0].page_content == "High relevance document"
        assert result[1].page_content == "Medium relevance document"
    
    def test_hybrid_search_below_threshold(self, mock_embed, mock_index):
        """Test that results below relative threshold are filtered out."""
        # Mock query response where second score is below relative threshold (50% of best)
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 1.0,  # Best score
                    "metadata": {
                        "text": "High relevance document",
                        "id": "doc1",
                        "type": "event"
                    }
                },
                {
                    "score": 0.4,  # Below 50% threshold (0.5 * 1.0 = 0.5)
                    "metadata": {
                        "text": "Low relevance document",
                        "id": "doc2", 
                        "type": "task"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        assert len(result) == 1  # Only first result above threshold
    
    def test_hybrid_search_mixed_scores(self, mock_embed, mock_index):
        """Test filtering with mixed scores above and below threshold."""
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 1.0,  # Best score
                    "metadata": {
                        "text": "High relevance",
                        "id": "doc1",
                        "type": "event"
                    }
                },
                {
                    "score": 0.6,  # Above 50% threshold 
                    "metadata": {
                        "text": "Medium relevance",
                        "id": "doc3",
                        "type": "task"
                    }
                },
                {
                    "score": 0.4,  # Below 50% threshold (0.5 * 1.0 = 0.5)
                    "metadata": {
                        "text": "Low relevance",
                        "id": "doc2",
                        "type": "event"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={},
            index=mock_index,
            embed=mock_embed
        )
        
        assert len(result) == 2  # Only docs 1 and 3
        assert result[0].page_content == "High relevance"
        assert result[1].page_content == "Medium relevance"
    
    def test_hybrid_search_uses_context_fallback(self, mock_embed, mock_index):
        """Test fallback to 'context' field when 'text' is missing."""
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.8,
                    "metadata": {
                        "context": "Document from context field",  # No 'text' field
                        "id": "doc1",
                        "type": "event"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={},
            index=mock_index,
            embed=mock_embed
        )
        
        assert len(result) == 1
        assert result[0].page_content == "Document from context field"
    
    def test_hybrid_search_empty_content_fallback(self, mock_embed, mock_index):
        """Test fallback to empty string when both text and context are missing."""
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.8,
                    "metadata": {
                        "id": "doc1",
                        "type": "event"
                        # No 'text' or 'context' field
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={},
            index=mock_index,
            embed=mock_embed
        )
        
        assert len(result) == 1
        assert result[0].page_content == ""
    
    def test_hybrid_search_parameters_passed_correctly(self, mock_embed, mock_index):
        """Test that all parameters are passed correctly to the index query."""
        mock_index.query.return_value = {"matches": []}
        
        query = "test query"
        k = 10
        meta_filter = {"type": "event", "date": "2025-05-28"}
        embedding_vector = [0.1] * 1536
        mock_embed.embed_query.return_value = embedding_vector
        
        hybrid_search_relative_band(
            query=query,
            k=k,
            meta_filter=meta_filter,
            index=mock_index,
            embed=mock_embed
        )
        
        # Verify embedding was called with query
        mock_embed.embed_query.assert_called_once_with(query)
        
        # Verify index query was called with correct parameters (pool_k = max(30, k*4) = 40)
        mock_index.query.assert_called_once_with(
            vector=embedding_vector,
            text=query,
            top_k=40,  # pool_k = max(30, 10*4) = 40
            filter=meta_filter,
            include_metadata=True
        )

    def test_hybrid_search_no_matches_returned(self, mock_embed, mock_index):
        """Test hybrid search when index returns no matches at all."""
        # Mock query response with no matches
        mock_index.query.return_value = {"matches": []}
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        assert result == []
        assert len(result) == 0

    def test_hybrid_search_single_weak_match_filtered(self, mock_embed, mock_index):
        """Test hybrid search when single weak match gets filtered out by absolute threshold."""
        # Mock query response with single very weak match below MIN_SCORE
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.1,  # Below MIN_SCORE (0.15)
                    "metadata": {
                        "text": "Weak relevance document",
                        "id": "doc1",
                        "type": "event"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        # Single weak match below MIN_SCORE should be filtered out
        assert len(result) == 0

    def test_hybrid_search_single_match_above_min_score(self, mock_embed, mock_index):
        """Test hybrid search when single match is above minimum score threshold."""
        # Mock query response with single match above MIN_SCORE
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 0.2,  # Above MIN_SCORE (0.15)
                    "metadata": {
                        "text": "Acceptable relevance document",
                        "id": "doc1",
                        "type": "event"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        # Single match above MIN_SCORE should pass through
        assert len(result) == 1
        assert result[0].page_content == "Acceptable relevance document"

    def test_hybrid_search_all_matches_below_threshold(self, mock_embed, mock_index):
        """Test hybrid search when all secondary matches are below relative threshold."""
        # Mock query response where all but first are below 50% threshold
        mock_index.query.return_value = {
            "matches": [
                {
                    "score": 1.0,  # Best score
                    "metadata": {
                        "text": "High relevance document",
                        "id": "doc1",
                        "type": "event"
                    }
                },
                {
                    "score": 0.3,  # Below 50% threshold
                    "metadata": {
                        "text": "Low relevance document 1",
                        "id": "doc2",
                        "type": "event"
                    }
                },
                {
                    "score": 0.2,  # Below 50% threshold
                    "metadata": {
                        "text": "Low relevance document 2",
                        "id": "doc3",
                        "type": "event"
                    }
                }
            ]
        }
        
        result = hybrid_search_relative_band(
            query="test query",
            k=5,
            meta_filter={"type": "event"},
            index=mock_index,
            embed=mock_embed
        )
        
        # Only first result should pass threshold
        assert len(result) == 1
        assert result[0].page_content == "High relevance document"
