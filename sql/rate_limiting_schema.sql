-- ===================================================================
-- RATE LIMITING SCHEMA FOR DISCORD ACADEMIC JARVIS
-- ===================================================================
-- This schema implements daily rate limiting for:
-- 1. User RAG requests (10 per day per user)
-- 2. Global file uploads (10 per day total across all users)
-- 3. PDF page validation (20 page limit per file)
-- 4. OpenAI usage monitoring
--
-- Timezone: America/Toronto (EST/EDT with automatic DST handling)
-- Reset: Daily at midnight Toronto time
-- ===================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===================================================================
-- TABLE: rate_limits
-- ===================================================================
-- Stores individual user rate limits (like RAG requests per user)
-- Each user can have multiple limit types tracked separately
-- ===================================================================
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,                    -- Discord user ID (64-bit integer)
    limit_type VARCHAR(50) NOT NULL,            -- 'rag_requests', 'file_uploads', etc.
    current_count INTEGER DEFAULT 0,            -- Current usage count for today
    daily_limit INTEGER NOT NULL,               -- Maximum allowed per day
    last_reset_date DATE DEFAULT CURRENT_DATE,  -- Last date when counter was reset
    timezone VARCHAR(50) DEFAULT 'America/Toronto', -- User's timezone (for future use)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure one record per user per limit type
    UNIQUE(user_id, limit_type)
);

-- ===================================================================
-- TABLE: global_limits
-- ===================================================================
-- Stores system-wide limits shared across all users
-- Example: Total file uploads per day across entire system
-- ===================================================================
CREATE TABLE IF NOT EXISTS global_limits (
    limit_type VARCHAR(50) PRIMARY KEY,         -- 'total_file_uploads', 'total_processing_time'
    current_count INTEGER DEFAULT 0,            -- Current usage count for today
    daily_limit INTEGER NOT NULL,               -- Maximum allowed per day globally
    last_reset_date DATE DEFAULT CURRENT_DATE,  -- Last date when counter was reset
    timezone VARCHAR(50) DEFAULT 'America/Toronto',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ===================================================================
-- TABLE: openai_usage_tracking
-- ===================================================================
-- Monitors OpenAI API usage for cost tracking and analytics
-- Not used for rate limiting, only for monitoring and alerting
-- ===================================================================
CREATE TABLE IF NOT EXISTS openai_usage_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,                    -- Discord user ID
    date DATE DEFAULT CURRENT_DATE,             -- Usage date (Toronto timezone)
    tokens_used INTEGER DEFAULT 0,              -- Total tokens consumed
    estimated_cost DECIMAL(10,4) DEFAULT 0,     -- Estimated cost in USD
    request_count INTEGER DEFAULT 0,            -- Number of OpenAI API calls
    model_used VARCHAR(100),                    -- GPT model used (gpt-4, gpt-3.5-turbo, etc.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- One record per user per date
    UNIQUE(user_id, date)
);

-- ===================================================================
-- INDEXES FOR PERFORMANCE
-- ===================================================================
-- These indexes ensure fast queries for rate limit checks
-- ===================================================================

-- Fast lookups for user rate limit checks
CREATE INDEX IF NOT EXISTS idx_rate_limits_user_type 
ON rate_limits(user_id, limit_type);

-- Fast identification of records that need reset
CREATE INDEX IF NOT EXISTS idx_rate_limits_reset_date 
ON rate_limits(last_reset_date);

-- Fast global limit lookups
CREATE INDEX IF NOT EXISTS idx_global_limits_reset_date 
ON global_limits(last_reset_date);

-- Fast OpenAI usage queries by date
CREATE INDEX IF NOT EXISTS idx_openai_usage_date 
ON openai_usage_tracking(date);

-- Fast OpenAI usage queries by user
CREATE INDEX IF NOT EXISTS idx_openai_usage_user_date 
ON openai_usage_tracking(user_id, date);

-- ===================================================================
-- FUNCTION: reset_toronto_limits()
-- ===================================================================
-- Resets all daily limits at midnight Toronto time
-- Called by cron job or manually for testing
-- Returns count of reset records for monitoring
-- ===================================================================
CREATE OR REPLACE FUNCTION reset_toronto_limits()
RETURNS TABLE(user_resets INTEGER, global_resets INTEGER, reset_date DATE) AS $$
DECLARE
    toronto_date DATE;
    user_reset_count INTEGER;
    global_reset_count INTEGER;
BEGIN
    -- Get current date in Toronto timezone
    -- This automatically handles EST/EDT transitions
    toronto_date := (NOW() AT TIME ZONE 'America/Toronto')::DATE;
    
    -- Reset user limits that are outdated
    UPDATE rate_limits 
    SET 
        current_count = 0,
        last_reset_date = toronto_date,
        updated_at = NOW()
    WHERE last_reset_date < toronto_date;
    
    GET DIAGNOSTICS user_reset_count = ROW_COUNT;
    
    -- Reset global limits that are outdated
    UPDATE global_limits 
    SET 
        current_count = 0,
        last_reset_date = toronto_date,
        updated_at = NOW()
    WHERE last_reset_date < toronto_date;
    
    GET DIAGNOSTICS global_reset_count = ROW_COUNT;
    
    -- Return reset statistics
    RETURN QUERY SELECT user_reset_count, global_reset_count, toronto_date;
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- FUNCTION: check_user_limit()
-- ===================================================================
-- Checks if a user can perform an action based on their daily limit
-- Automatically creates user record if it doesn't exist
-- Automatically resets counter if it's a new day
-- ===================================================================
CREATE OR REPLACE FUNCTION check_user_limit(
    p_user_id BIGINT,
    p_limit_type VARCHAR(50)
) RETURNS TABLE(
    can_proceed BOOLEAN, 
    current_count INTEGER, 
    daily_limit INTEGER, 
    warning_threshold BOOLEAN,
    reset_time TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    toronto_date DATE;
    user_record RECORD;
    limit_value INTEGER;
    next_reset TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Get current date in Toronto timezone
    toronto_date := (NOW() AT TIME ZONE 'America/Toronto')::DATE;
    
    -- Calculate next reset time (midnight Toronto time)
    next_reset := (toronto_date + INTERVAL '1 day')::TIMESTAMP AT TIME ZONE 'America/Toronto';
    
    -- Determine default daily limit based on limit type
    CASE p_limit_type
        WHEN 'rag_requests' THEN limit_value := 10;
        WHEN 'file_uploads' THEN limit_value := 999999; -- User file uploads not limited individually
        ELSE limit_value := 0; -- Unknown limit types default to 0
    END CASE;
    
    -- Insert or update user limit record
    INSERT INTO rate_limits (user_id, limit_type, daily_limit, last_reset_date, current_count)
    VALUES (p_user_id, p_limit_type, limit_value, toronto_date, 0)
    ON CONFLICT (user_id, limit_type) 
    DO UPDATE SET 
        -- Reset counter if it's a new day
        last_reset_date = CASE 
            WHEN rate_limits.last_reset_date < toronto_date THEN toronto_date
            ELSE rate_limits.last_reset_date
        END,
        current_count = CASE 
            WHEN rate_limits.last_reset_date < toronto_date THEN 0
            ELSE rate_limits.current_count
        END,
        updated_at = NOW();
    
    -- Get the updated record
    SELECT * INTO user_record FROM rate_limits 
    WHERE user_id = p_user_id AND limit_type = p_limit_type;
    
    -- Return status information
    RETURN QUERY SELECT 
        (user_record.current_count < user_record.daily_limit) AS can_proceed,
        user_record.current_count,
        user_record.daily_limit,
        (user_record.current_count >= (user_record.daily_limit * 0.8)::INTEGER) AS warning_threshold,
        next_reset;
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- FUNCTION: check_global_limit()
-- ===================================================================
-- Checks if a global limit allows the action to proceed
-- Used for system-wide limits like total file uploads per day
-- ===================================================================
CREATE OR REPLACE FUNCTION check_global_limit(
    p_limit_type VARCHAR(50)
) RETURNS TABLE(
    can_proceed BOOLEAN, 
    current_count INTEGER, 
    daily_limit INTEGER, 
    warning_threshold BOOLEAN,
    reset_time TIMESTAMP WITH TIME ZONE
) AS $$
DECLARE
    toronto_date DATE;
    global_record RECORD;
    limit_value INTEGER;
    next_reset TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Get current date in Toronto timezone
    toronto_date := (NOW() AT TIME ZONE 'America/Toronto')::DATE;
    
    -- Calculate next reset time
    next_reset := (toronto_date + INTERVAL '1 day')::TIMESTAMP AT TIME ZONE 'America/Toronto';
    
    -- Determine default daily limit based on limit type
    CASE p_limit_type
        WHEN 'total_file_uploads' THEN limit_value := 10;
        WHEN 'total_processing_minutes' THEN limit_value := 1440; -- 24 hours
        ELSE limit_value := 100; -- Default global limit
    END CASE;
    
    -- Insert or update global limit record
    INSERT INTO global_limits (limit_type, daily_limit, last_reset_date, current_count)
    VALUES (p_limit_type, limit_value, toronto_date, 0)
    ON CONFLICT (limit_type) 
    DO UPDATE SET 
        -- Reset counter if it's a new day
        last_reset_date = CASE 
            WHEN global_limits.last_reset_date < toronto_date THEN toronto_date
            ELSE global_limits.last_reset_date
        END,
        current_count = CASE 
            WHEN global_limits.last_reset_date < toronto_date THEN 0
            ELSE global_limits.current_count
        END,
        updated_at = NOW();
    
    -- Get the updated record
    SELECT * INTO global_record FROM global_limits 
    WHERE limit_type = p_limit_type;
    
    -- Return status information
    RETURN QUERY SELECT 
        (global_record.current_count < global_record.daily_limit) AS can_proceed,
        global_record.current_count,
        global_record.daily_limit,
        (global_record.current_count >= (global_record.daily_limit * 0.8)::INTEGER) AS warning_threshold,
        next_reset;
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- FUNCTION: increment_user_count()
-- ===================================================================
-- Safely increments a user's usage counter
-- Should be called after successful completion of the action
-- ===================================================================
CREATE OR REPLACE FUNCTION increment_user_count(
    p_user_id BIGINT,
    p_limit_type VARCHAR(50)
) RETURNS INTEGER AS $$
DECLARE
    new_count INTEGER;
BEGIN
    UPDATE rate_limits 
    SET 
        current_count = current_count + 1,
        updated_at = NOW()
    WHERE user_id = p_user_id AND limit_type = p_limit_type
    RETURNING current_count INTO new_count;
    
    RETURN COALESCE(new_count, 0);
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- FUNCTION: increment_global_count()
-- ===================================================================
-- Safely increments a global usage counter
-- ===================================================================
CREATE OR REPLACE FUNCTION increment_global_count(
    p_limit_type VARCHAR(50)
) RETURNS INTEGER AS $$
DECLARE
    new_count INTEGER;
BEGIN
    UPDATE global_limits 
    SET 
        current_count = current_count + 1,
        updated_at = NOW()
    WHERE limit_type = p_limit_type
    RETURNING current_count INTO new_count;
    
    RETURN COALESCE(new_count, 0);
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- FUNCTION: track_openai_usage()
-- ===================================================================
-- Records OpenAI API usage for monitoring and cost tracking
-- ===================================================================
CREATE OR REPLACE FUNCTION track_openai_usage(
    p_user_id BIGINT,
    p_tokens INTEGER,
    p_estimated_cost DECIMAL(10,4),
    p_model VARCHAR(100) DEFAULT 'gpt-4'
) RETURNS VOID AS $$
DECLARE
    toronto_date DATE;
BEGIN
    toronto_date := (NOW() AT TIME ZONE 'America/Toronto')::DATE;
    
    INSERT INTO openai_usage_tracking (user_id, date, tokens_used, estimated_cost, request_count, model_used)
    VALUES (p_user_id, toronto_date, p_tokens, p_estimated_cost, 1, p_model)
    ON CONFLICT (user_id, date)
    DO UPDATE SET
        tokens_used = openai_usage_tracking.tokens_used + p_tokens,
        estimated_cost = openai_usage_tracking.estimated_cost + p_estimated_cost,
        request_count = openai_usage_tracking.request_count + 1,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ===================================================================
-- INITIAL DATA SETUP
-- ===================================================================
-- Create the global file upload limit record
-- ===================================================================
INSERT INTO global_limits (limit_type, daily_limit, current_count) 
VALUES ('total_file_uploads', 10, 0)
ON CONFLICT (limit_type) DO NOTHING;

-- ===================================================================
-- COMMENTS AND DOCUMENTATION
-- ===================================================================
COMMENT ON TABLE rate_limits IS 'Tracks daily usage limits per user for various actions';
COMMENT ON TABLE global_limits IS 'Tracks system-wide daily limits shared across all users';
COMMENT ON TABLE openai_usage_tracking IS 'Monitors OpenAI API usage for cost tracking and analytics';

COMMENT ON FUNCTION reset_toronto_limits() IS 'Resets all daily counters at midnight Toronto time';
COMMENT ON FUNCTION check_user_limit(BIGINT, VARCHAR) IS 'Checks if user can perform action based on daily limit';
COMMENT ON FUNCTION check_global_limit(VARCHAR) IS 'Checks if global limit allows action to proceed';
COMMENT ON FUNCTION increment_user_count(BIGINT, VARCHAR) IS 'Increments user usage counter after successful action';
COMMENT ON FUNCTION increment_global_count(VARCHAR) IS 'Increments global usage counter after successful action';
COMMENT ON FUNCTION track_openai_usage(BIGINT, INTEGER, DECIMAL, VARCHAR) IS 'Records OpenAI usage for monitoring';
