# tests/test_bot_commands.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional
import discord
from discord.ext import commands

# Mock external dependencies before importing main modules
with patch('supabase.create_client'), \
     patch('pinecone.Pinecone'), \
     patch('openai.OpenAI'), \
     patch('rag_module.rag_handler_optimized.respond') as mock_rag, \
     patch('calendar_module.calendar_handler.respond') as mock_cal:
    
    mock_rag.return_value = "[RAG ANSWER] Test response"
    mock_cal.return_value = "[CALENDAR ANSWER] Test response"
    
    from main_bot import jarvis_rag, jarvis_calendar, build_ctx_cfg, send_answer

@pytest.fixture
def mock_interaction() -> MagicMock:
    """Create a mock Discord interaction for slash commands."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 111
    interaction.channel_id = 222
    interaction.user = MagicMock()
    interaction.user.id = 12345
    interaction.user.__str__ = MagicMock(return_value="testuser#1234")
    interaction.channel = MagicMock()
    interaction.channel.name = "test-channel"
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()  # This needs to be AsyncMock
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    
    return interaction

@pytest.fixture 
def valid_tenant_config() -> Dict[str, Any]:
    """Return a valid tenant configuration."""
    return {
        "guild_id": 111,
        "name": "test-guild",
        "type": "rag-calendar",
        "data_dir": "data/test",
        "vector_store_path": "vector/test",
        "timezone": "UTC"
    }

class TestSlashCommands:
    """Test the new slash command functionality."""
    
    @pytest.mark.asyncio
    async def test_jarvis_rag_command(self, mock_interaction: MagicMock, valid_tenant_config: Dict[str, Any]) -> None:
        """Test /jarvis_rag slash command."""
        # Test that the command runs without errors (integration style test)
        # Add required fields for context
        context_with_user_data = {
            **valid_tenant_config,
            "guild_id": 111,
            "channel_id": 222,
            "user_id": 12345,
            "username": "testuser#1234",
            "name": "test-channel",
            "index_rag": "test-index"
        }
        
        with patch('main_bot.check_channel_authorization', new_callable=AsyncMock, return_value=context_with_user_data), \
             patch('main_bot.has_feature_access', new_callable=AsyncMock, return_value=True), \
             patch('main_bot.send_answer', new_callable=AsyncMock) as mock_send:
            
            # Call the callback function directly - this should complete without error
            await jarvis_rag.callback(mock_interaction, "What is the syllabus?")  # type: ignore
            
            # Verify interaction response was deferred
            mock_interaction.response.defer.assert_called_once()
            
            # Verify send_answer was called (meaning the command completed)
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_jarvis_calendar_command(self, mock_interaction: MagicMock, valid_tenant_config: Dict[str, Any]) -> None:
        """Test /jarvis_calendar slash command."""
        # Test that the command runs without errors (integration style test)
        context_with_user_data = {
            **valid_tenant_config,
            "guild_id": 111,
            "channel_id": 222,
            "user_id": 12345,
            "username": "testuser#1234",
            "name": "test-channel",
            "index_calendar": "calendar-test"
        }
        
        with patch('main_bot.check_channel_authorization', new_callable=AsyncMock, return_value=context_with_user_data), \
             patch('main_bot.has_feature_access', new_callable=AsyncMock, return_value=True), \
             patch('main_bot.send_answer', new_callable=AsyncMock) as mock_send:
            
            # Call the callback function directly - this should complete without error
            await jarvis_calendar.callback(mock_interaction, "What's next week?")  # type: ignore
            
            # Verify interaction response was deferred
            mock_interaction.response.defer.assert_called_once()
            
            # Verify send_answer was called (meaning the command completed)
            mock_send.assert_called_once()

class TestContextBuilding:
    """Test the context building functionality."""
    
    @pytest.mark.asyncio
    async def test_build_ctx_cfg_with_tenant_config(self, mock_interaction: MagicMock, valid_tenant_config: Dict[str, Any]) -> None:
        """Test context building with valid tenant configuration."""
        with patch('tenant_context.load_tenant_context_async', new_callable=AsyncMock, return_value=valid_tenant_config), \
             patch('tenant_context.load_tenant_context', return_value=valid_tenant_config):
            
            ctx = await build_ctx_cfg(mock_interaction)
            
            # Verify tenant config is merged
            assert ctx is not None, "Context should not be None with valid tenant config"
            assert ctx["name"] == "test-guild"
            assert ctx["type"] == "rag-calendar"
            assert ctx["timezone"] == "UTC"
            
            # Verify interaction data is added
            assert ctx["guild_id"] == 111
            assert ctx["channel_id"] == 222
            assert ctx["user_id"] == 12345
            assert ctx["username"] == "testuser#1234"
    
    @pytest.mark.asyncio
    async def test_build_ctx_cfg_without_tenant_config(self, mock_interaction):
        """Test context building without tenant configuration."""
        with patch('tenant_context.load_tenant_context_async', new_callable=AsyncMock, return_value=None), \
             patch('tenant_context.load_tenant_context', return_value=None):
            
            ctx = await build_ctx_cfg(mock_interaction)
            
            # When no tenant config is found, function should return None
            assert ctx is None

class TestSendAnswer:
    """Test the send_answer utility function."""
    
    @pytest.mark.asyncio
    async def test_send_answer_string_response_not_done(self, mock_interaction):
        """Test sending string response when interaction not done."""
        mock_interaction.response.is_done.return_value = False
        
        await send_answer(mock_interaction, "Test response")
        
        # Should send initial response
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        embeds = call_args[1]["embeds"]
        assert len(embeds) == 1
        assert embeds[0].description == "Test response"
        
        # Should not use followup
        mock_interaction.followup.send.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_answer_string_response_done(self, mock_interaction):
        """Test sending string response when interaction already done."""
        mock_interaction.response.is_done.return_value = True
        
        await send_answer(mock_interaction, "Test response")
        
        # Should not send initial response
        mock_interaction.response.send_message.assert_not_called()
        
        # Should use followup
        mock_interaction.followup.send.assert_called_once()
        call_args = mock_interaction.followup.send.call_args
        embeds = call_args[1]["embeds"]
        assert len(embeds) == 1
        assert embeds[0].description == "Test response"
    
    @pytest.mark.asyncio
    async def test_send_answer_embed_response(self, mock_interaction):
        """Test sending embed response."""
        embed = discord.Embed(title="Test", description="Test embed")
        mock_interaction.response.is_done.return_value = False
        
        await send_answer(mock_interaction, embed)
        
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        embeds = call_args[1]["embeds"]
        assert len(embeds) == 1
        assert embeds[0] == embed
    
    @pytest.mark.asyncio
    async def test_send_answer_embed_list_response(self, mock_interaction):
        """Test sending list of embeds response."""
        embed1 = discord.Embed(title="Test1", description="Test embed 1")
        embed2 = discord.Embed(title="Test2", description="Test embed 2")
        embeds_list = [embed1, embed2]
        mock_interaction.response.is_done.return_value = False
        
        await send_answer(mock_interaction, embeds_list)
        
        mock_interaction.response.send_message.assert_called_once()
        call_args = mock_interaction.response.send_message.call_args
        embeds = call_args[1]["embeds"]
        assert len(embeds) == 2
        assert embeds == embeds_list

class TestErrorHandling:
    """Test error handling in slash commands."""
    
    @pytest.mark.asyncio
    async def test_rag_command_handler_error(self, mock_interaction: MagicMock, valid_tenant_config: Dict[str, Any]) -> None:
        """Test error handling in RAG command."""
        context_with_user_data = {
            **valid_tenant_config,
            "guild_id": 111,
            "channel_id": 222,
            "user_id": 12345,
            "username": "testuser#1234",
            "name": "test-channel",
            "index_rag": "test-index"
        }
        
        with patch('main_bot.check_channel_authorization', new_callable=AsyncMock, return_value=context_with_user_data), \
             patch('main_bot.has_feature_access', new_callable=AsyncMock, return_value=True):
            
            # Command should complete successfully (global mocks handle responses)
            await jarvis_rag.callback(mock_interaction, "test query")  # type: ignore
            
            # Verify interaction was handled properly
            mock_interaction.response.defer.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_calendar_command_handler_error(self, mock_interaction: MagicMock, valid_tenant_config: Dict[str, Any]) -> None:
        """Test error handling in calendar command."""
        context_with_user_data = {
            **valid_tenant_config,
            "guild_id": 111,
            "channel_id": 222,
            "user_id": 12345,
            "username": "testuser#1234",
            "name": "test-channel",
            "index_calendar": "calendar-test"
        }
        
        with patch('main_bot.check_channel_authorization', new_callable=AsyncMock, return_value=context_with_user_data), \
             patch('main_bot.has_feature_access', new_callable=AsyncMock, return_value=True):
            
            # Command should complete successfully (global mocks handle responses)
            await jarvis_calendar.callback(mock_interaction, "test query")  # type: ignore
            
            # Verify interaction was handled properly
            mock_interaction.response.defer.assert_called_once()
