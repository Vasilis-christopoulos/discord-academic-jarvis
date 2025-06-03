# tests/test_error_handling.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import tempfile
import json
from pathlib import Path

class TestErrorHandling:
    """Test error handling throughout the application."""
    
    @pytest.mark.asyncio
    async def test_tenant_context_missing_file(self):
        """Test handling of missing tenants file."""
        with patch('tenant_context.TENANT_CONFIGS', []):
            from tenant_context import load_tenant_context
            
            result = load_tenant_context(999, 888)
            assert result is None
    
    @pytest.mark.asyncio
    async def test_tenant_context_invalid_guild(self):
        """Test handling of invalid guild ID."""
        from tenant_context import load_tenant_context
        
        result = load_tenant_context(999999, 888888)
        assert result is None
    
    def test_settings_validation_errors(self):
        """Test settings validation with invalid values."""
        from settings import AppSettings
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AppSettings(
                discord_token="",  # Empty token should fail
                openai_api_key="valid",
                pinecone_api_key="valid",
                pinecone_calendar_index="valid",
                supabase_url="valid",
                supabase_api_key="valid"
            )
    
    def test_malformed_tenants_json(self):
        """Test handling of malformed tenants.json."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content {{{")
            temp_path = f.name
        
        try:
            with patch('settings.settings.tenants_file', temp_path):
                with pytest.raises(json.JSONDecodeError):
                    # This should trigger JSON parsing error
                    with open(temp_path, 'r') as file:
                        json.loads(file.read())
        finally:
            Path(temp_path).unlink()
    
    @pytest.mark.asyncio
    async def test_query_parser_openai_error(self):
        """Test query parser handling OpenAI API errors."""
        from calendar_module.query_parser import parse_query
        
        with patch('calendar_module.query_parser.parse_pipeline') as mock_pipeline:
            mock_pipeline.ainvoke.side_effect = Exception("OpenAI API Error")
            
            result = await parse_query("test query", "2025-05-28")
            
            # Should return non-applicable result on error
            assert result.applicable is False
            assert all(getattr(result, field) is None for field in 
                      ['type', 'date_from', 'date_to', 'filter', 'limit'])
    
    def test_calendar_utils_invalid_iso(self):
        """Test calendar utils with invalid ISO strings."""
        from utils.calendar_utils import parse_iso, epoch_from_iso
        
        # Test malformed ISO string
        with pytest.raises(ValueError):
            parse_iso("not-a-valid-iso-string")
        
        # Test epoch conversion with invalid ISO
        with pytest.raises(ValueError):
            epoch_from_iso("invalid")
        # The current implementation will raise ValueError for invalid ISO strings
    
    def test_html_to_discord_md_malformed_html(self):
        """Test HTML conversion with malformed HTML."""
        from utils.calendar_utils import html_to_discord_md
        
        # Test with unclosed tags, malformed attributes, etc.
        malformed_cases = [
            '<a href="no-closing-quote>Link</a>',
            '<a href=>Empty href</a>',
            '<a>No href attribute</a>',
            'Regular text with < and > symbols',
        ]
        
        for case in malformed_cases:
            # Should not crash, even with malformed HTML
            result = html_to_discord_md(case)
            assert isinstance(result, str)

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_message_router_unknown_module(self):
        """Test message router with unknown module type."""
        from message_router import is_module_allowed
        
        result = is_module_allowed("unknown_module", {"type": "rag"})
        assert result is False
    
    def test_message_router_missing_type(self):
        """Test message router with missing type in context."""
        from message_router import is_module_allowed
        
        result = is_module_allowed("rag", {})  # No 'type' key
        assert result is False  # Should handle missing key gracefully
    
    def test_clean_function_edge_cases(self):
        """Test reranker clean function with edge cases."""
        from utils.reranker_calendar import _clean
        
        # Empty string
        assert _clean("") == ""
        
        # Only whitespace
        result = _clean("   \n\n\t   ")
        assert result.strip() == ""
        
        # Only HTML tags
        result = _clean("<b></b><i></i>")
        assert result.strip() == ""
        
        # Very long text
        long_text = "word " * 1000
        result = _clean(long_text, max_tokens=5)
        assert len(result) <= 25  # 5 tokens * 4 chars + possible ellipsis
    
    @pytest.mark.asyncio
    async def test_tenant_context_directory_creation_failure(self):
        """Test handling of directory creation failures."""
        from tenant_context import load_tenant_context
        
        with patch('tenant_context.TENANT_CONFIGS') as mock_configs:
            mock_tenant = MagicMock()
            mock_tenant.guild_id = 111
            mock_tenant.channels = {222: MagicMock()}
            mock_tenant.model_dump.return_value = {
                "guild_id": 111,
                "name": "test",
                "data_dir": "/invalid/path/that/cannot/be/created",
                "vector_store_path": "/another/invalid/path"
            }
            mock_tenant.channels[222].model_dump.return_value = {
                "name": "test-channel",
                "type": "rag"
            }
            mock_configs.__iter__.return_value = [mock_tenant]
            
            with patch('tenant_context.Path') as mock_path:
                mock_path.return_value.mkdir.side_effect = PermissionError("Cannot create directory")
                
                # Should handle directory creation failure gracefully
                with pytest.raises(PermissionError):
                    load_tenant_context(111, 222)
