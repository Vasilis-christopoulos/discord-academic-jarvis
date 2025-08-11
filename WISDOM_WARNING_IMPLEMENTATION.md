# Wisdom Warning System Implementation

## Overview
Implemented a new wisdom warning system that alerts users when they reach 70% of their daily RAG request limit. This provides an earlier warning than the existing 80% threshold, encouraging users to use their remaining requests wisely.

## Implementation Details

### Core Changes

1. **Enhanced RateLimitResult Dataclass** (`rag_module/rate_limiter.py`)
   - Added `wisdom_warning: bool` field to track 70% threshold
   - Added `wisdom_threshold: float = 0.7` to RateLimitConfig

2. **Updated Rate Limiting Logic**
   - Calculates wisdom warning at 70% of daily limit: `int(daily_limit * 0.7)`
   - For default limit of 10 requests: wisdom warning triggers at 7 requests
   - Maintains existing 80% warning for backwards compatibility

3. **Enhanced Message Generation**
   - New wisdom warning message format: "🧠 **Wisdom Warning**: You have completed X/Y requests. Spend the next Z wisely."
   - Prioritizes warnings: wisdom (70%) < regular (80%) < limit exceeded (100%)

4. **RAG Handler Integration** (`rag_module/rag_handler_optimized.py`)
   - Detects wisdom warning status during rate limit check
   - Appends wisdom warning message to successful RAG responses
   - Only shows for RAG requests (not other limit types)

### Warning Threshold Behavior

| Requests Used | Daily Limit | Percentage | Warning Type | Message Displayed |
|---------------|-------------|------------|--------------|-------------------|
| 0-6 | 10 | 0-60% | None | Normal response only |
| 7 | 10 | 70% | 🧠 Wisdom | Response + wisdom warning |
| 8-9 | 10 | 80-90% | ⚠️ Regular | Response + regular warning |
| 10+ | 10 | 100%+ | 🔴 Blocked | Rate limit exceeded message |

### Example Messages

**Wisdom Warning (7/10 requests):**
```
[Normal RAG Response]

🧠 **Wisdom Warning**: You have completed 7/10 requests. Spend the next 3 wisely.
```

**Regular Warning (8/10 requests):**
```
⚠️ **Approaching limit**: 8/10 rag_requests used today
🔄 **Resets in**: 5h 23m
```

**Limit Exceeded (10/10 requests):**
```
⏰ **Daily limit reached!** You've used 10/10 RAG queries today.
🔄 **Resets in**: 5h 23m
💡 **Tip**: Try refining your questions to get better results with fewer queries.
```

## Testing

### Test Utility
- Created `test_wisdom_warning.py` to demonstrate threshold behavior
- Shows warning progression from 6 to 10 requests
- Validates message generation logic

### Database Inspector
- Use `inspect_database.py` to view current user request counts
- Monitor rate limiting effectiveness

## Configuration

The wisdom threshold is configurable in `RateLimitConfig`:

```python
@dataclass
class RateLimitConfig:
    wisdom_threshold: float = 0.7   # 70% threshold for wisdom warning
    warning_threshold: float = 0.8  # 80% threshold for regular warning
```

## Benefits

1. **Early Warning**: Users get notified at 70% instead of waiting until 80%
2. **Encourages Thoughtful Usage**: "Spend wisely" message promotes better query formulation
3. **Backwards Compatible**: Existing 80% warnings still work
4. **User-Friendly**: Clear, actionable messaging with remaining request counts
5. **Configurable**: Thresholds can be adjusted if needed

## Usage in Discord

Users will see the wisdom warning appended to their RAG responses when they hit the 70% threshold:

1. User asks 7th question of the day
2. Bot provides normal RAG response
3. Bot adds wisdom warning message below the response
4. User is informed they have 3 requests remaining

This provides a smooth user experience while encouraging mindful usage of the rate-limited resource.
