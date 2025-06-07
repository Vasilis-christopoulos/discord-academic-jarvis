# tests/test_bot_commands.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import discord
from discord.ext import commands

# Mock external dependencies before importing main modules
with patch('supabase.create_client'), \
     patch('pinecone.Pinecone'), \
     patch('openai.OpenAI'), \
     patch('rag_module.rag_handler.respond') as mock_rag, \
     patch('calendar_module.calendar_handler.respond') as mock_cal:
    
    mock_rag.return_value = "[RAG ANSWER] Test response"
    mock_cal.return_value = "[CALENDAR ANSWER] Test response"
    
    from main_bot import build_ctx_cfg, send_answer
    import main_bot

@pytest.fixture
def mock_interaction():
    """Create a mock Discord interaction for slash commands."""
    interaction = MagicMock()
    interaction.guild_id = 111
    interaction.channel_id = 222
    interaction.user = MagicMock()
    interaction.user.id = 12345
    interaction.user.__str__ = MagicMock(return_value="testuser#1234")
    interaction.channel = MagicMock()
    interaction.channel.name = "test-channel"
    
    # Mock response handling
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    
    return interaction

@pytest.fixture 
def valid_tenant_config():
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
    async def test_jarvis_rag_command(self, mock_interaction, valid_tenant_config):
        """Test /jarvis_rag slash command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.rag_respond', new_callable=AsyncMock) as mock_rag:
            
            mock_rag.return_value = "Test RAG response"
            
            await main_bot.jarvis_rag.callback(mock_interaction, "What is the syllabus?")
            
            # Verify interaction response was deferred
            mock_interaction.response.defer.assert_called_once()
            
            # Verify RAG handler was called with correct parameters
            mock_rag.assert_called_once()
            call_args = mock_rag.call_args
            assert call_args[0][0] == "What is the syllabus?"  # query parameter
            
            # Verify context was built correctly
            ctx = call_args[0][1]  # context parameter
            assert ctx["guild_id"] == 111
            assert ctx["channel_id"] == 222
            assert ctx["user_id"] == 12345
    
    @pytest.mark.asyncio
    async def test_jarvis_calendar_command(self, mock_interaction, valid_tenant_config):
        """Test /jarvis_calendar slash command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.cal_respond', new_callable=AsyncMock) as mock_cal:
            
            mock_cal.return_value = "Test calendar response"
            
            await main_bot.jarvis_calendar.callback(mock_interaction, "What's next week?")
            
            # Verify interaction response was deferred
            mock_interaction.response.defer.assert_called_once()
            
            # Verify calendar handler was called with correct parameters
            mock_cal.assert_called_once()
            call_args = mock_cal.call_args
            assert call_args[0][0] == "What's next week?"  # query parameter
            
            # Verify context was built correctly
            ctx = call_args[0][1]  # context parameter
            assert ctx["guild_id"] == 111
            assert ctx["channel_id"] == 222
            assert ctx["user_id"] == 12345

class TestContextBuilding:
    """Test the context building functionality."""
    
    @pytest.mark.asyncio
    async def test_build_ctx_cfg_with_tenant_config(self, mock_interaction, valid_tenant_config):
        """Test context building with valid tenant configuration."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config):
            
            ctx = await build_ctx_cfg(mock_interaction)
            
            # Verify tenant config is merged
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
        with patch('main_bot.load_tenant_context', return_value=None):
            
            ctx = await build_ctx_cfg(mock_interaction)
            
            # Verify defaults are used
            assert ctx["name"] == "test-channel"  # from interaction.channel.name
            assert ctx["timezone"] == "UTC"
            
            # Verify interaction data is still added
            assert ctx["guild_id"] == 111
            assert ctx["channel_id"] == 222
            assert ctx["user_id"] == 12345
            assert ctx["username"] == "testuser#1234"

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
    async def test_rag_command_handler_error(self, mock_interaction, valid_tenant_config):
        """Test error handling in RAG command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.rag_respond', new_callable=AsyncMock) as mock_rag:
            
            mock_rag.side_effect = Exception("Test error")
            
            with pytest.raises(Exception, match="Test error"):
                await main_bot.jarvis_rag.callback(mock_interaction, "test query")
    
    @pytest.mark.asyncio
    async def test_calendar_command_handler_error(self, mock_interaction, valid_tenant_config):
        """Test error handling in calendar command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.cal_respond', new_callable=AsyncMock) as mock_cal:
            
            mock_cal.side_effect = Exception("Test error")
            
            with pytest.raises(Exception, match="Test error"):
                await main_bot.jarvis_calendar.callback(mock_interaction, "test query")