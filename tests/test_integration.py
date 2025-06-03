# tests/test_integration_new.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from settings import TenantConfig, ChannelConfig

class TestIntegrationFlow:
    """Test end-to-end integration scenarios."""
    
    @pytest.fixture
    def sample_tenant_configs(self):
        """Create sample tenant configurations for testing."""
        channel_config = ChannelConfig(
            name="integration-test-channel",
            description="Test channel",
            data_dir="data/12345/67890",
            vector_store_path="vector_store/12345/67890",
            type="rag-calendar"
        )
        
        tenant_config = TenantConfig(
            guild_id=12345,
            name="integration-test-guild",
            description="Test guild for integration",
            calendar_id="test@example.com",
            tasklist_id="test123",
            data_dir="data/12345",
            vector_store_path="vector_store/12345",
            timezone="America/Toronto",
            channels={67890: channel_config}
        )
        
        return [tenant_config]
    
    @pytest.mark.asyncio
    async def test_full_rag_command_flow(self, sample_tenant_configs):
        """Test complete RAG command flow from Discord to response."""
        with patch('tenant_context.TENANT_CONFIGS', sample_tenant_configs):
            from main_bot import jarvis
            
            # Create mock Discord context
            mock_ctx = MagicMock()
            mock_ctx.guild.id = 12345
            mock_ctx.channel.id = 67890
            mock_ctx.author.id = 999
            mock_ctx.send = AsyncMock()
            
            # Mock directory creation
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir = MagicMock()
                mock_path.return_value.exists.return_value = True
                
                # Mock the RAG handler
                with patch('main_bot.rag_respond', new_callable=AsyncMock) as mock_rag:
                    mock_rag.return_value = "This is a test RAG response"
                    
                    # Execute the command
                    await jarvis(mock_ctx, "rag", rest="What is machine learning?")
                    
                    # Verify the flow
                    mock_rag.assert_called_once()
                    call_args = mock_rag.call_args
                    assert call_args[0][0] == "What is machine learning?"  # query
                    assert call_args[0][1]["name"] == "integration-test-channel"  # context
                    
                    mock_ctx.send.assert_called_once_with("This is a test RAG response")
    
    @pytest.mark.asyncio
    async def test_full_calendar_command_flow(self, sample_tenant_configs):
        """Test complete calendar command flow from Discord to response."""
        with patch('tenant_context.TENANT_CONFIGS', sample_tenant_configs):
            from main_bot import jarvis
            
            # Create mock Discord context
            mock_ctx = MagicMock()
            mock_ctx.guild.id = 12345
            mock_ctx.channel.id = 67890
            mock_ctx.author.id = 999
            mock_ctx.send = AsyncMock()
            
            # Mock directory creation
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir = MagicMock()
                mock_path.return_value.exists.return_value = True
                
                # Mock the calendar handler
                with patch('main_bot.cal_respond', new_callable=AsyncMock) as mock_cal:
                    mock_cal.return_value = "This is a test calendar response"
                    
                    # Execute the command
                    await jarvis(mock_ctx, "calendar", rest="What's on my schedule today?")
                    
                    # Verify the flow
                    mock_cal.assert_called_once()
                    call_args = mock_cal.call_args
                    assert call_args[0][0] == "What's on my schedule today?"  # query
                    assert call_args[0][1]["name"] == "integration-test-channel"  # context
                    
                    mock_ctx.send.assert_called_once_with("This is a test calendar response")
    
    def test_tenant_loading_and_context_merge(self, sample_tenant_configs):
        """Test tenant loading and context merging."""
        with patch('tenant_context.TENANT_CONFIGS', sample_tenant_configs):
            from tenant_context import load_tenant_context
            
            # Mock directory creation
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir = MagicMock()
                mock_path.return_value.exists.return_value = True
                
                # Test loading channel-specific context
                context = load_tenant_context(12345, 67890)
                
                assert context is not None
                assert context["guild_id"] == 12345
                assert context["name"] == "integration-test-channel"  # Channel overrides guild
                assert context["type"] == "rag-calendar"
                assert context["calendar_id"] == "test@example.com"
    
    def test_module_routing_integration(self, sample_tenant_configs):
        """Test module routing with real tenant context."""
        with patch('tenant_context.TENANT_CONFIGS', sample_tenant_configs):
            from tenant_context import load_tenant_context
            from message_router import is_module_allowed
            
            # Mock directory creation
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir = MagicMock()
                mock_path.return_value.exists.return_value = True
                
                context = load_tenant_context(12345, 67890)
                
                # Test module routing for rag-calendar channel
                assert is_module_allowed("rag", context) is True
                assert is_module_allowed("calendar", context) is True
                assert is_module_allowed("fallback", context) is True
                assert is_module_allowed("unknown", context) is False
    
    def test_error_propagation_in_integration(self, sample_tenant_configs):
        """Test error handling in integration scenarios."""
        with patch('tenant_context.TENANT_CONFIGS', sample_tenant_configs):
            from tenant_context import load_tenant_context
            
            # Mock directory creation
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir = MagicMock()
                mock_path.return_value.exists.return_value = True
                
                # Test loading context for non-existent channel (should get guild config)
                context = load_tenant_context(12345, 99999)
                
                assert context is not None  # Should return guild config without channel override
                assert context["guild_id"] == 12345
                assert context["name"] == "integration-test-guild"  # Guild name, not channel
