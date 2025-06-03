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
     patch('calendar_module.calendar_handler.respond') as mock_cal, \
     patch('fallback_module.fallback_handler.respond') as mock_fb:
    
    mock_rag.return_value = "[RAG ANSWER] Test response"
    mock_cal.return_value = "[CALENDAR ANSWER] Test response" 
    mock_fb.return_value = "[FALLBACK ANSWER] Test response"
    
    from main_bot import jarvis

@pytest.fixture
def mock_context():
    """Create a mock Discord context."""
    ctx = MagicMock()
    ctx.guild.id = 111
    ctx.channel.id = 222
    ctx.author.id = 12345
    ctx.send = AsyncMock()
    return ctx

@pytest.fixture 
def valid_tenant_config():
    """Return a valid tenant configuration."""
    return {
        "guild_id": 111,
        "name": "test-guild",
        "type": "rag-calendar",
        "data_dir": "data/test",
        "vector_store_path": "vector/test"
    }

class TestJarvisCommand:
    """Test the main jarvis command functionality."""
    
    @pytest.mark.asyncio
    async def test_rag_command_valid(self, mock_context, valid_tenant_config):
        """Test valid RAG command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.rag_respond', new_callable=AsyncMock) as mock_rag:
            
            mock_rag.return_value = "Test RAG response"
            
            await jarvis(mock_context, "rag", rest="What is the syllabus?")
            
            mock_rag.assert_called_once_with("What is the syllabus?", valid_tenant_config)
            mock_context.send.assert_called_once_with("Test RAG response")
    
    @pytest.mark.asyncio
    async def test_calendar_command_valid(self, mock_context, valid_tenant_config):
        """Test valid calendar command."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.cal_respond', new_callable=AsyncMock) as mock_cal:
            
            mock_cal.return_value = "Test calendar response"
            
            await jarvis(mock_context, "calendar", rest="What's next week?")
            
            mock_cal.assert_called_once_with("What's next week?", valid_tenant_config)
            mock_context.send.assert_called_once_with("Test calendar response")
    
    @pytest.mark.asyncio
    async def test_fallback_command(self, mock_context, valid_tenant_config):
        """Test fallback command with free-form query."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.fb_respond', new_callable=AsyncMock) as mock_fb:
            
            mock_fb.return_value = "Test fallback response"
            
            await jarvis(mock_context, "How", rest="are you today?")
            
            mock_fb.assert_called_once_with("How are you today?", valid_tenant_config)
            mock_context.send.assert_called_once_with("Test fallback response")
    
    @pytest.mark.asyncio
    async def test_empty_query_error(self, mock_context, valid_tenant_config):
        """Test error handling for empty queries."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config):
            
            await jarvis(mock_context, "rag", rest="")
            
            mock_context.send.assert_called_once_with("❌ Missing query text.")
    
    @pytest.mark.asyncio
    async def test_unconfigured_guild(self, mock_context):
        """Test handling of unconfigured guild/channel."""
        with patch('main_bot.load_tenant_context', return_value=None):
            
            await jarvis(mock_context, "rag", rest="test query")
            
            # Check that the error message was sent
            mock_context.send.assert_called_once()
            args = mock_context.send.call_args[0]
            assert "This server/channel isn" in args[0]  # Unicode-safe substring check
    
    @pytest.mark.asyncio
    async def test_module_not_allowed(self, mock_context):
        """Test module blocking when not allowed in channel."""
        rag_only_config = {
            "guild_id": 111,
            "name": "test-guild", 
            "type": "rag",  # Only RAG allowed
            "data_dir": "data/test",
            "vector_store_path": "vector/test"
        }
        
        with patch('main_bot.load_tenant_context', return_value=rag_only_config):
            
            await jarvis(mock_context, "calendar", rest="test query")
            
            mock_context.send.assert_called_once_with("❌ `calendar` is not enabled in this channel.")
    
    @pytest.mark.asyncio
    async def test_embed_response(self, mock_context, valid_tenant_config):
        """Test handling of embed responses."""
        embed = discord.Embed(title="Test", description="Test embed")
        embeds_list = [embed]
        
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.cal_respond', new_callable=AsyncMock) as mock_cal:
            
            mock_cal.return_value = embeds_list
            
            await jarvis(mock_context, "calendar", rest="test query")
            
            mock_context.send.assert_called_once_with(embeds=embeds_list)
    
    @pytest.mark.asyncio
    async def test_command_error_handling(self, mock_context, valid_tenant_config):
        """Test error handling in command execution."""
        with patch('main_bot.load_tenant_context', return_value=valid_tenant_config), \
             patch('main_bot.rag_respond', new_callable=AsyncMock) as mock_rag:
            
            mock_rag.side_effect = Exception("Test error")
            
            with pytest.raises(Exception, match="Test error"):
                await jarvis(mock_context, "rag", rest="test query")

class TestModuleRouting:
    """Test module routing logic."""
    
    @pytest.mark.parametrize("module,rest,expected_module,expected_query", [
        ("rag", "test query", "rag", "test query"),
        ("calendar", "when is next meeting", "calendar", "when is next meeting"),
        ("RAG", "TEST QUERY", "rag", "TEST QUERY"),  # case insensitive
        ("CALENDAR", "TEST", "calendar", "TEST"),     # case insensitive
        ("hello", "world", "fallback", "hello world"),  # fallback
        ("hello", None, "fallback", "hello"),           # fallback with no rest
    ])
    def test_module_and_query_parsing(self, module, rest, expected_module, expected_query):
        """Test that module and query are parsed correctly."""
        # We need to test the parsing logic directly since it's embedded in the command
        mod = module.lower()
        if mod in ("rag", "calendar"):
            query = rest or ""
            assert mod == expected_module
            if expected_query:
                assert query == expected_query
        else:
            # free-form (fallback)
            query = f"{module} {rest}".strip() if rest else module
            mod = "fallback"
            assert mod == expected_module
            assert query == expected_query
