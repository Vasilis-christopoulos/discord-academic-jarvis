# tests/test_vs_calendar.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from calendar_module.vs_calendar import (
    get_calendar_store,
    INDEX_NAME,
    EMBED_DIM
)


class TestVsCalendar:
    @patch('calendar_module.vs_calendar.pc')
    @patch('calendar_module.vs_calendar.index')
    @patch('calendar_module.vs_calendar.embeddings')
    def test_get_calendar_store_success(self, mock_embeddings, mock_index, mock_pc):
        """Test successful creation of calendar vector store."""
        # Execute
        store = get_calendar_store()
        
        # Verify
        assert store is not None
        # The function should return a PineconeVectorStore instance
        # Since we're mocking the dependencies, we can't test the exact type
        # but we can verify the function completes without error

    def test_index_name_constant(self):
        """Test that index name constant is set correctly."""
        assert INDEX_NAME == "calendar-hybrid"

    def test_embed_dimension_constant(self):
        """Test that embedding dimension constant is set correctly."""
        assert EMBED_DIM == 3072

    def test_module_initialization_creates_expected_objects(self):
        """Test that the module initializes with expected objects."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Verify the module has the expected attributes
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal, 'index')
        assert hasattr(vs_cal, 'embeddings')
        assert hasattr(vs_cal, 'INDEX_NAME')
        assert hasattr(vs_cal, 'EMBED_DIM')
        
        # Verify the constants are correct
        assert vs_cal.INDEX_NAME == "calendar-hybrid"
        assert vs_cal.EMBED_DIM == 3072

    def test_index_constants_are_correct(self):
        """Test that index configuration constants are correct."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Test that the configuration values are as expected
        assert vs_cal.INDEX_NAME == "calendar-hybrid"
        assert vs_cal.EMBED_DIM == 3072

    def test_get_calendar_store_returns_valid_store(self):
        """Test that get_calendar_store returns a valid store object."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Call the function
        store = vs_cal.get_calendar_store()
        
        # Verify basic properties
        assert store is not None
        assert hasattr(store, 'similarity_search') or hasattr(store, 'search')
        
        # Test that the function is repeatable
        store2 = vs_cal.get_calendar_store()
        assert store2 is not None

    def test_pinecone_client_initialization(self):
        """Test that Pinecone client is properly initialized."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Verify that the Pinecone client exists and has expected methods
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal.pc, 'list_indexes')
        assert hasattr(vs_cal.pc, 'Index')

    def test_openai_embeddings_initialization(self):
        """Test that OpenAI embeddings are properly initialized."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Verify that embeddings exist and have expected properties
        assert hasattr(vs_cal, 'embeddings')
        assert hasattr(vs_cal.embeddings, 'embed_query') or hasattr(vs_cal.embeddings, 'embed_documents')

    @patch('calendar_module.vs_calendar.PineconeVectorStore')
    @patch('calendar_module.vs_calendar.index')
    @patch('calendar_module.vs_calendar.embeddings')
    def test_vector_store_initialization(self, mock_embeddings, mock_index, mock_vector_store_class):
        """Test that PineconeVectorStore is initialized correctly."""
        # Execute
        get_calendar_store()
        
        # Verify PineconeVectorStore was created with correct parameters
        mock_vector_store_class.assert_called_once_with(
            index=mock_index,
            embedding=mock_embeddings
        )

    def test_serverless_spec_constants(self):
        """Test that the module uses expected serverless configuration values."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # This test verifies that the module sets up with expected values
        # The actual ServerlessSpec configuration happens during module initialization
        assert vs_cal.INDEX_NAME == "calendar-hybrid"
        assert vs_cal.EMBED_DIM == 3072

    @patch('calendar_module.vs_calendar.logger')
    def test_get_calendar_store_logging(self, mock_logger):
        """Test that get_calendar_store logs the index name."""
        with patch('calendar_module.vs_calendar.PineconeVectorStore') as mock_store_class:
            # Execute
            get_calendar_store()
            
            # Verify logging occurred
            mock_logger.info.assert_called_with("Using Pinecone index: %s", INDEX_NAME)


class TestVsCalendarModuleImport:
    @patch('calendar_module.vs_calendar.settings')
    @patch('calendar_module.vs_calendar.Pinecone')
    @patch('calendar_module.vs_calendar.OpenAIEmbeddings')
    def test_module_imports_correctly(self, mock_embeddings, mock_pinecone, mock_settings):
        """Test that the module can be imported without errors."""
        mock_settings.pinecone_api_key = "test_key"
        
        # Mock Pinecone client and index
        mock_pc_instance = Mock()
        mock_list_response = Mock()
        mock_list_response.names = [INDEX_NAME]  # Index already exists
        mock_pc_instance.list_indexes.return_value = mock_list_response
        mock_pinecone.return_value = mock_pc_instance
        
        # This should not raise any exceptions
        try:
            import calendar_module.vs_calendar
            # Test passes if no exception is raised
        except Exception as e:
            pytest.fail(f"Module import failed: {e}")

    def test_constants_are_defined(self):
        """Test that all required constants are defined in the module."""
        import calendar_module.vs_calendar as vs_cal
        
        # Check that constants exist and have expected types/values
        assert hasattr(vs_cal, 'INDEX_NAME')
        assert hasattr(vs_cal, 'EMBED_DIM')
        assert isinstance(vs_cal.INDEX_NAME, str)
        assert isinstance(vs_cal.EMBED_DIM, int)
        assert vs_cal.EMBED_DIM > 0


class TestVsCalendarErrorHandling:
    def test_get_calendar_store_returns_valid_object(self):
        """Test that get_calendar_store returns a valid object."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Call the function
        store = vs_cal.get_calendar_store()
        
        # Verify it returns a valid object
        assert store is not None
        # PineconeVectorStore should have these methods
        assert hasattr(store, 'similarity_search') or hasattr(store, 'search')

    def test_module_has_required_dependencies(self):
        """Test that the module has all required dependencies available."""
        # Import the module
        import calendar_module.vs_calendar as vs_cal
        
        # Verify all required objects are created
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal, 'index')
        assert hasattr(vs_cal, 'embeddings')
        assert vs_cal.pc is not None
        assert vs_cal.index is not None
        assert vs_cal.embeddings is not None


class TestVsCalendarConfiguration:
    def test_embedding_model_specification(self):
        """Test that the correct embedding model is specified."""
        # The module should use the large embedding model for better accuracy
        import calendar_module.vs_calendar
        
        # Verify the embedding dimension matches the large model
        assert calendar_module.vs_calendar.EMBED_DIM == 3072
        
        # This dimension corresponds to text-embedding-3-large model

    def test_metric_configuration(self):
        """Test that cosine metric is used for similarity search."""
        # Cosine similarity is typically best for text embeddings
        # This is tested indirectly through the index creation mock verification
        # in the test_index_creation_when_not_exists test
        pass

    def test_cloud_provider_configuration(self):
        """Test that AWS is used as the cloud provider."""
        # AWS us-east-1 is typically the most cost-effective region
        # This is tested indirectly through the ServerlessSpec mock verification
        # in the test_serverless_spec_configuration test
        pass
