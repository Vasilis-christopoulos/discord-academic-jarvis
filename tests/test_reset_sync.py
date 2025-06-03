# tests/test_reset_sync.py
import pytest
from unittest.mock import Mock, patch, MagicMock

from calendar_module.reset_sync import (
    reset_watermarks,
    reset_pinecone,
    MODULE,
    INITIAL_ISO
)


class TestResetWatermarks:
    @patch('calendar_module.reset_sync.supabase')
    def test_reset_watermarks_success(self, mock_supabase):
        """Test successful reset of sync watermarks."""
        mock_table = Mock()
        mock_supabase.table.return_value = mock_table
        
        # Execute
        reset_watermarks()
        
        # Verify supabase calls
        assert mock_supabase.table.call_count == 2  # Once for each type
        mock_supabase.table.assert_any_call("sync_state")
        
        # Verify update calls for both event and task types
        update_calls = mock_table.update.call_args_list
        assert len(update_calls) == 2
        
        # Check that both calls use INITIAL_ISO (None)
        for call in update_calls:
            args, kwargs = call
            update_data = args[0]
            assert update_data["first_synced"] == INITIAL_ISO
            assert update_data["last_synced"] == INITIAL_ISO

    @patch('calendar_module.reset_sync.supabase')
    def test_reset_watermarks_filters_correctly(self, mock_supabase):
        """Test that reset_watermarks filters by module and type correctly."""
        mock_table = Mock()
        mock_eq_chain = Mock()
        mock_table.update.return_value = mock_eq_chain
        mock_eq_chain.eq.return_value = mock_eq_chain
        mock_supabase.table.return_value = mock_table
        
        # Execute
        reset_watermarks()
        
        # Verify filtering chains
        eq_calls = mock_eq_chain.eq.call_args_list
        
        # Should have 4 eq calls total (2 for each type: module filter + type filter)
        assert len(eq_calls) >= 4
        
        # Check module filtering
        module_calls = [call for call in eq_calls if call[0][0] == "module"]
        assert len(module_calls) == 2
        for call in module_calls:
            assert call[0][1] == MODULE  # "calendar"
        
        # Check type filtering
        type_calls = [call for call in eq_calls if call[0][0] == "type"]
        assert len(type_calls) == 2
        type_values = [call[0][1] for call in type_calls]
        assert "event" in type_values
        assert "task" in type_values

    @patch('calendar_module.reset_sync.supabase')
    @patch('builtins.print')
    def test_reset_watermarks_prints_success(self, mock_print, mock_supabase):
        """Test that reset_watermarks prints success message."""
        mock_table = Mock()
        mock_supabase.table.return_value = mock_table
        
        # Execute
        reset_watermarks()
        
        # Verify success message is printed
        mock_print.assert_called_with("✅ watermarks reset")

    @patch('calendar_module.reset_sync.supabase')
    def test_reset_watermarks_exception_handling(self, mock_supabase):
        """Test that reset_watermarks handles exceptions gracefully."""
        mock_table = Mock()
        mock_table.update.side_effect = Exception("Database error")
        mock_supabase.table.return_value = mock_table
        
        # Should not raise exception
        try:
            reset_watermarks()
        except Exception:
            pytest.fail("reset_watermarks should handle exceptions gracefully")


class TestResetPinecone:
    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    @patch('builtins.print')
    def test_reset_pinecone_with_vectors(self, mock_print, mock_settings, mock_pc):
        """Test reset_pinecone when index has vectors."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        # Mock index with vectors
        mock_index = Mock()
        mock_stats = {"total_vector_count": 100}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_pc.Index.return_value = mock_index
        
        # Execute
        reset_pinecone()
        
        # Verify
        mock_pc.Index.assert_called_once_with("test_index")
        mock_index.describe_index_stats.assert_called_once()
        mock_index.delete.assert_called_once_with(delete_all=True)
        mock_print.assert_called_with("✅ cleared Pinecone index")

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    @patch('builtins.print')
    def test_reset_pinecone_empty_index(self, mock_print, mock_settings, mock_pc):
        """Test reset_pinecone when index is already empty."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        # Mock empty index
        mock_index = Mock()
        mock_stats = {"total_vector_count": 0}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_pc.Index.return_value = mock_index
        
        # Execute
        reset_pinecone()
        
        # Verify
        mock_pc.Index.assert_called_once_with("test_index")
        mock_index.describe_index_stats.assert_called_once()
        mock_index.delete.assert_not_called()  # Should not delete if already empty
        mock_print.assert_called_with("⚠️  index already empty")

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    def test_reset_pinecone_uses_settings_index(self, mock_settings, mock_pc):
        """Test that reset_pinecone uses the correct index from settings."""
        test_index_name = "custom_calendar_index"
        mock_settings.pinecone_calendar_index = test_index_name
        
        mock_index = Mock()
        mock_stats = {"total_vector_count": 0}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_pc.Index.return_value = mock_index
        
        # Execute
        reset_pinecone()
        
        # Verify correct index name is used
        mock_pc.Index.assert_called_once_with(test_index_name)

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    def test_reset_pinecone_api_key_usage(self, mock_settings, mock_pc):
        """Test that reset_pinecone uses the correct index from settings."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        mock_index = Mock()
        mock_stats = {"total_vector_count": 0}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_pc.Index.return_value = mock_index
        
        # Execute
        reset_pinecone()
        
        # Verify correct index is used (since pc is module-level, we can't test API key directly)
        mock_pc.Index.assert_called_once_with("test_index")

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    def test_reset_pinecone_exception_handling(self, mock_settings, mock_pc):
        """Test that reset_pinecone handles exceptions gracefully."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        # Mock exception during index operations
        mock_index = Mock()
        mock_index.describe_index_stats.side_effect = Exception("Pinecone error")
        mock_pc.Index.return_value = mock_index
        
        # Should not raise exception
        try:
            reset_pinecone()
        except Exception:
            pytest.fail("reset_pinecone should handle exceptions gracefully")


class TestResetSyncConstants:
    def test_module_constant(self):
        """Test that MODULE constant is set correctly."""
        assert MODULE == "calendar"
        assert isinstance(MODULE, str)

    def test_initial_iso_constant(self):
        """Test that INITIAL_ISO constant is None for reset."""
        assert INITIAL_ISO is None


class TestResetSyncMainExecution:
    @patch('calendar_module.reset_sync.settings')
    @patch('builtins.print')
    def test_main_execution_flow(self, mock_print, mock_settings):
        """Test the main execution flow functions are available and importable."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        # Test that the functions are available and importable
        from calendar_module.reset_sync import reset_watermarks, reset_pinecone
        
        # Verify functions exist and are callable
        assert callable(reset_watermarks)
        assert callable(reset_pinecone)
        
        # Test the module constants
        from calendar_module.reset_sync import MODULE, INITIAL_ISO
        assert MODULE == "calendar"
        assert INITIAL_ISO is None


class TestResetSyncIntegration:
    @patch('calendar_module.reset_sync.supabase')
    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    @patch('builtins.print')
    def test_full_reset_sequence(self, mock_print, mock_settings, mock_pc, mock_supabase):
        """Test the complete reset sequence."""
        # Setup mocks
        mock_settings.pinecone_calendar_index = "test_index"
        mock_settings.pinecone_api_key = "test_key"
        
        # Supabase mocks
        mock_table = Mock()
        mock_supabase.table.return_value = mock_table
        
        # Pinecone mocks
        mock_index = Mock()
        mock_stats = {"total_vector_count": 50}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_pc.Index.return_value = mock_index
        
        # Execute both functions
        reset_watermarks()
        reset_pinecone()
        
        # Verify complete flow
        assert mock_supabase.table.call_count == 2  # For both event and task types
        mock_pc.Index.assert_called_once_with("test_index")
        mock_index.delete.assert_called_once_with(delete_all=True)
        
        # Verify success messages
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert "✅ watermarks reset" in print_calls
        assert "✅ cleared Pinecone index" in print_calls

    def test_settings_dependency(self):
        """Test that the module properly imports settings."""
        # This test ensures the settings import works
        from calendar_module.reset_sync import settings
        assert settings is not None

    def test_required_imports(self):
        """Test that all required imports are available."""
        try:
            from calendar_module.reset_sync import (
                reset_watermarks,
                reset_pinecone,
                MODULE,
                INITIAL_ISO
            )
        except ImportError as e:
            pytest.fail(f"Required import failed: {e}")


class TestResetSyncErrorScenarios:
    @patch('calendar_module.reset_sync.supabase')
    def test_supabase_connection_error(self, mock_supabase):
        """Test handling of Supabase connection errors."""
        mock_supabase.table.side_effect = Exception("Connection failed")
        
        # Should not raise exception
        try:
            reset_watermarks()
        except Exception:
            pytest.fail("Should handle Supabase connection errors gracefully")

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    def test_pinecone_connection_error(self, mock_settings, mock_pc):
        """Test handling of Pinecone connection errors."""
        mock_settings.pinecone_calendar_index = "test_index"
        mock_pc.side_effect = Exception("Pinecone connection failed")
        
        # Should not raise exception
        try:
            reset_pinecone()
        except Exception:
            pytest.fail("Should handle Pinecone connection errors gracefully")

    @patch('calendar_module.reset_sync.pc')
    @patch('calendar_module.reset_sync.settings')
    def test_index_delete_error(self, mock_settings, mock_pc):
        """Test handling of index deletion errors."""
        mock_settings.pinecone_calendar_index = "test_index"
        
        mock_index = Mock()
        mock_stats = {"total_vector_count": 100}
        mock_index.describe_index_stats.return_value = mock_stats
        mock_index.delete.side_effect = Exception("Delete failed")
        mock_pc.Index.return_value = mock_index
        
        # Should not raise exception
        try:
            reset_pinecone()
        except Exception:
            pytest.fail("Should handle index deletion errors gracefully")
