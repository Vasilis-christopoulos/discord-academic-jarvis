# Phase 3 Rate Limiting Implementation Guide

## Overview
Phase 3 rate limiting has been successfully implemented with:
- User-level RAG request limits (10 requests/day)
- Global file upload limits (10 files/day server-wide)
- PDF page validation (20 pages max)
- File size validation (25MB max)
- Toronto timezone daily resets at midnight

## Files Created/Modified

### Database Schema
- `sql/rate_limiting_schema.sql` - Initial schema
- `sql/rate_limiting_schema_fixed.sql` - Updated schema with TEXT user_id for Discord compatibility

### Core Rate Limiting
- `rag_module/rate_limiter.py` - Main rate limiting logic
- `rag_module/database_utils.py` - Supabase client utilities
- `rag_module/file_validator.py` - File upload validation and limits

### Integration
- `rag_module/rag_handler_optimized.py` - Updated with rate limiting
- `requirements.txt` - Already includes required dependencies

## Usage Examples

### 1. RAG Query Rate Limiting (Already Integrated)
The RAG handler now automatically checks rate limits:

```python
from rag_module.rag_handler_optimized import get_optimized_handler

# Get handler (rate limiting is automatic)
handler = get_optimized_handler()

# Process query (rate limits checked automatically)
response = await handler.handle_query(
    query="What is machine learning?",
    context={'guild_id': 'your-guild', 'index_rag': 'your-index'},
    user_id="123456789012345678"  # Discord user ID
)
```

### 2. File Upload Validation
For Discord attachment processing:

```python
from rag_module.file_validator import get_file_validator
import discord

# In your Discord bot command handler
@bot.command()
async def upload_document(ctx):
    if not ctx.message.attachments:
        await ctx.send("❌ Please attach a file to upload.")
        return
    
    attachment = ctx.message.attachments[0]
    
    # Get file content
    file_content = await attachment.read()
    
    # Validate file
    validator = get_file_validator()
    result = await validator.validate_file_upload(
        file_content=file_content,
        filename=attachment.filename,
        user_id=str(ctx.author.id)
    )
    
    if not result.allowed:
        await ctx.send(result.message)
        return
    
    # Process file upload...
    # ... your existing file processing code ...
    
    # Increment counter after successful upload
    new_count = await validator.increment_upload_count()
    await ctx.send(f"✅ File uploaded successfully! Server usage: {new_count}/{result.daily_limit}")
```

### 3. Manual Rate Limit Checks
For custom rate limiting:

```python
from rag_module.rate_limiter import get_rate_limiter, RateLimitConfig
from rag_module.database_utils import get_supabase_client

# Initialize rate limiter
supabase_client = get_supabase_client()
rate_limiter = get_rate_limiter(supabase_client)

# Check user RAG request limit
result = await rate_limiter.check_user_limit(user_id, "rag_requests")
if not result.allowed:
    await ctx.send(result.message)
    return

# Check global file upload limit
result = await rate_limiter.check_global_limit("total_file_uploads")
if not result.allowed:
    await ctx.send(result.message)
    return

# Increment counters after successful operations
await rate_limiter.increment_user_count(user_id, "rag_requests")
await rate_limiter.increment_global_count("total_file_uploads")
```

## Configuration

### Rate Limiter Configuration
```python
from rag_module.rate_limiter import RateLimitConfig

config = RateLimitConfig(
    user_rag_requests=10,      # RAG requests per user per day
    user_file_uploads=5,       # File uploads per user per day
    global_file_uploads=10,    # Total file uploads server-wide per day
    pdf_page_limit=20,         # Maximum pages in PDF files
    timezone="America/Toronto", # Timezone for daily resets
    enable_rate_limiting=True  # Enable/disable rate limiting
)
```

### File Validator Configuration
```python
from rag_module.file_validator import FileValidationConfig

config = FileValidationConfig(
    max_files_per_day=10,         # Global file uploads per day
    max_pdf_pages=20,             # Maximum PDF pages
    max_file_size_mb=25,          # Maximum file size in MB
    allowed_extensions=['.pdf', '.docx', '.txt', '.md']  # Allowed file types
)
```

## Database Setup

1. **Update Schema** (recommended):
   ```sql
   -- Run this in Supabase SQL editor
   \i sql/rate_limiting_schema_fixed.sql
   ```

2. **Verify Functions**:
   - `check_user_limit(user_id TEXT, limit_type TEXT)`
   - `increment_user_count(user_id TEXT, limit_type TEXT)`
   - `check_global_limit(limit_type TEXT)`
   - `increment_global_count(limit_type TEXT)`
   - `track_openai_usage(user_id TEXT, tokens INTEGER, cost DECIMAL, model TEXT)`
   - `reset_toronto_limits()` - for daily cleanup

## Monitoring

### Get User Statistics
```python
# Get detailed user stats
stats = await rate_limiter.get_user_stats(user_id)
print(stats)
# Output: {
#   'user_id': '123456789012345678',
#   'limits': {
#     'rag_requests': {'current_count': 5, 'daily_limit': 10, 'last_reset': '2025-07-21'}
#   },
#   'openai_usage': {...},
#   'next_reset': '2025-07-22T00:00:00-04:00'
# }
```

### Get Upload Statistics
```python
# Get server upload stats
validator = get_file_validator()
stats = await validator.get_upload_stats()
print(stats)
# Output: {
#   'files_uploaded_today': 5,
#   'daily_limit': 10,
#   'remaining': 5,
#   'reset_time': 'midnight Toronto time'
# }
```

## Daily Reset (Production)

For production, set up a cron job to reset limits daily:

```bash
# Add to crontab (0 0 * * * means midnight daily)
0 0 * * * psql $DATABASE_URL -c "SELECT reset_toronto_limits();"
```

Or use a Supabase Edge Function with cron trigger.

## Error Handling

The system is designed to "fail open" - if rate limiting fails, requests are allowed with warnings logged:

```python
# Rate limit failures are logged but don't block requests
# Check logs for: "Error checking user limit" or "Error checking global limit"
```

## Testing

Run the test suites:

```bash
# Test rate limiting
python test_rate_limiting.py

# Test file validation
python test_file_validation.py
```

## Next Steps

1. **Deploy the updated schema** to your production Supabase instance
2. **Update your Discord bot** to use the file validator for attachment processing
3. **Set up daily reset cron job** for production
4. **Monitor rate limiting logs** to ensure it's working correctly
5. **Adjust limits** based on usage patterns

The system is now ready for production use with comprehensive rate limiting across all major operations!
