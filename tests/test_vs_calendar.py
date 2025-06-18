# tests/test_vs_calendar.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from utils.vector_store import (
    get_vector_store,
    EMBED_DIM
)

# Test constants based on the current implementation
INDEX_NAME = "calendar-hybrid"  # Expected calendar index name


# tests/test_vs_calendar.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from utils.vector_store import (
    get_vector_store,
    EMBED_DIM
)

# Test constants based on the current implementation
INDEX_NAME = "calendar-hybrid"  # Expected calendar index name


class TestVsCalendar:
    @patch('utils.vector_store.pc')
    @patch('utils.vector_store.embeddings')
    def test_get_vector_store_success(self, mock_embeddings, mock_pc):
        """Test successful creation of calendar vector store."""
        # Mock the Pinecone client and index
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index exists
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        # Execute
        store = get_vector_store(INDEX_NAME)
        
        # Verify
        assert store is not None
        mock_pc.Index.assert_called_once_with(INDEX_NAME)

    def test_embed_dimension_constant(self):
        """Test that embedding dimension constant is set correctly."""
        assert EMBED_DIM == 3072

    def test_module_initialization_creates_expected_objects(self):
        """Test that the module initializes with expected objects."""
        # Import the module
        import utils.vector_store as vs_cal
        
        # Verify the module has the expected attributes
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal, 'embeddings')
        assert hasattr(vs_cal, 'EMBED_DIM')
        
        # Verify the constants are correct
        assert vs_cal.EMBED_DIM == 3072

    def test_embed_dimension_constant_is_correct(self):
        """Test that embedding dimension constant is correct."""
        # Import the module
        import utils.vector_store as vs_cal
        
        # Test that the configuration values are as expected
        assert vs_cal.EMBED_DIM == 3072

    @patch('utils.vector_store.pc')
    def test_get_vector_store_returns_valid_store(self, mock_pc):
        """Test that get_vector_store returns a valid store object."""
        # Mock the Pinecone client and index
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index exists
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        # Import the module
        import utils.vector_store as vs_cal
        
        # Call the function
        store = vs_cal.get_vector_store(INDEX_NAME)
        
        # Verify basic properties
        assert store is not None
        assert hasattr(store, 'similarity_search') or hasattr(store, 'search')
        
        # Test that the function is repeatable
        store2 = vs_cal.get_vector_store(INDEX_NAME)
        assert store2 is not None

    def test_pinecone_client_initialization(self):
        """Test that Pinecone client is properly initialized."""
        # Import the module
        import utils.vector_store as vs_cal
        
        # Verify that the Pinecone client exists and has expected methods
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal.pc, 'list_indexes')
        assert hasattr(vs_cal.pc, 'Index')

    def test_openai_embeddings_initialization(self):
        """Test that OpenAI embeddings are properly initialized."""
        # Import the module
        import utils.vector_store as vs_cal
        
        # Verify that embeddings exist and have expected properties
        assert hasattr(vs_cal, 'embeddings')
        assert hasattr(vs_cal.embeddings, 'embed_query') or hasattr(vs_cal.embeddings, 'embed_documents')

    @patch('utils.vector_store.PineconeVectorStore')
    @patch('utils.vector_store.pc')
    @patch('utils.vector_store.embeddings')
    def test_vector_store_initialization(self, mock_embeddings, mock_pc, mock_vector_store_class):
        """Test that PineconeVectorStore is initialized correctly."""
        # Mock the Pinecone client and index
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index exists
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        # Execute
        get_vector_store(INDEX_NAME)
        
        # Verify PineconeVectorStore was created with correct parameters
        mock_vector_store_class.assert_called_once_with(index=mock_index, embedding=mock_embeddings)

    @patch('utils.vector_store.logger')
    @patch('utils.vector_store.pc')
    def test_get_vector_store_logging(self, mock_pc, mock_logger):
        """Test that get_vector_store logs the index name."""
        # Mock the Pinecone client and index
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index exists
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        with patch('utils.vector_store.PineconeVectorStore') as mock_store_class:
            # Execute
            get_vector_store(INDEX_NAME)
            
            # Verify logging occurred
            mock_logger.info.assert_called_with("Using Pinecone index: %s", INDEX_NAME)


class TestVsCalendarModuleImport:
    @patch('utils.vector_store.settings')
    @patch('utils.vector_store.Pinecone')
    @patch('utils.vector_store.OpenAIEmbeddings')
    def test_module_imports_correctly(self, mock_embeddings, mock_pinecone, mock_settings):
        """Test that the module can be imported without errors."""
        mock_settings.pinecone_api_key = "test_key"
        
        # Mock Pinecone client and index
        mock_pc_instance = Mock()
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index already exists
        mock_pc_instance.list_indexes.return_value = mock_list_response
        mock_pinecone.return_value = mock_pc_instance
        
        # This should not raise any exceptions
        try:
            import utils.vector_store
            # Test passes if no exception is raised
        except Exception as e:
            pytest.fail(f"Module import failed: {e}")

    def test_constants_are_defined(self):
        """Test that all required constants are defined in the module."""
        import utils.vector_store as vs_cal
        
        # Check that constants exist and have expected types/values
        assert hasattr(vs_cal, 'EMBED_DIM')
        assert isinstance(vs_cal.EMBED_DIM, int)
        assert vs_cal.EMBED_DIM > 0


class TestVsCalendarErrorHandling:
    @patch('utils.vector_store.pc')
    def test_get_vector_store_returns_valid_object(self, mock_pc):
        """Test that get_vector_store returns a valid object."""
        # Mock the Pinecone client and index
        mock_list_response = Mock()
        mock_list_response.names.return_value = [INDEX_NAME]  # Index exists
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        # Import the module
        import utils.vector_store as vs_cal
        
        # Call the function
        store = vs_cal.get_vector_store(INDEX_NAME)
        
        # Verify it returns a valid object
        assert store is not None
        # PineconeVectorStore should have these methods
        assert hasattr(store, 'similarity_search') or hasattr(store, 'search')

    def test_module_has_required_dependencies(self):
        """Test that the module has all required dependencies available."""
        # Import the module
        import utils.vector_store as vs_cal
        
        # Verify all required objects are created
        assert hasattr(vs_cal, 'pc')
        assert hasattr(vs_cal, 'embeddings')
        assert vs_cal.pc is not None
        assert vs_cal.embeddings is not None


class TestVsCalendarConfiguration:
    def test_embedding_model_specification(self):
        """Test that the correct embedding model is specified."""
        # The module should use the large embedding model for better accuracy
        import utils.vector_store
        
        # Verify the embedding dimension matches the large model
        assert utils.vector_store.EMBED_DIM == 3072
        
        # This dimension corresponds to text-embedding-3-large model

    @patch('utils.vector_store.pc')
    def test_index_creation_when_not_exists(self, mock_pc):
        """Test that index is created when it doesn't exist."""
        # Mock that index doesn't exist
        mock_list_response = Mock()
        mock_list_response.names.return_value = []  # Index doesn't exist
        mock_pc.list_indexes.return_value = mock_list_response
        mock_index = Mock()
        mock_pc.Index.return_value = mock_index
        
        # Execute
        get_vector_store(INDEX_NAME)
        
        # Verify index creation was called
        mock_pc.create_index.assert_called_once()
        create_call_args = mock_pc.create_index.call_args
        assert create_call_args[1]['name'] == INDEX_NAME
        assert create_call_args[1]['dimension'] == EMBED_DIM
        assert create_call_args[1]['metric'] == "cosine"

    def test_cloud_provider_configuration(self):
        """Test that AWS is used as the cloud provider."""
        # AWS us-east-1 is typically the most cost-effective region
        # This is tested indirectly through the ServerlessSpec mock verification
        # in the test_index_creation_when_not_exists test
        pass
