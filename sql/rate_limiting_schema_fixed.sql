-- Update schema to use text for user_id instead of bigint
-- Discord user IDs can be larger than bigint range

-- Drop existing functions
DROP FUNCTION IF EXISTS check_user_limit(TEXT, TEXT);
DROP FUNCTION IF EXISTS increment_user_count(TEXT, TEXT);
DROP FUNCTION IF EXISTS check_global_limit(TEXT);
DROP FUNCTION IF EXISTS increment_global_count(TEXT);
DROP FUNCTION IF EXISTS track_openai_usage(TEXT, INTEGER, DECIMAL, TEXT);
DROP FUNCTION IF EXISTS reset_toronto_limits();

-- Drop and recreate tables with text user_id
DROP TABLE IF EXISTS openai_usage_tracking;
DROP TABLE IF EXISTS rate_limits;
DROP TABLE IF EXISTS global_limits;

-- User rate limits table (text user_id for Discord compatibility)
CREATE TABLE rate_limits (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    limit_type TEXT NOT NULL, -- 'rag_requests', 'file_uploads', etc.
    request_count INTEGER NOT NULL DEFAULT 0,
    date_toronto DATE NOT NULL DEFAULT (CURRENT_DATE AT TIME ZONE 'America/Toronto'),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, limit_type, date_toronto)
);

-- Global rate limits table (server-wide limits)
CREATE TABLE global_limits (
    id SERIAL PRIMARY KEY,
    limit_type TEXT NOT NULL, -- 'total_file_uploads', etc.
    request_count INTEGER NOT NULL DEFAULT 0,
    date_toronto DATE NOT NULL DEFAULT (CURRENT_DATE AT TIME ZONE 'America/Toronto'),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(limit_type, date_toronto)
);

-- OpenAI usage tracking table (text user_id)
CREATE TABLE openai_usage_tracking (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    cost DECIMAL(10, 6) NOT NULL,
    model TEXT NOT NULL,
    date_toronto DATE NOT NULL DEFAULT (CURRENT_DATE AT TIME ZONE 'America/Toronto'),
    timestamp_toronto TIMESTAMPTZ NOT NULL DEFAULT (NOW() AT TIME ZONE 'America/Toronto'),
    INDEX(user_id, date_toronto)
);

-- Indexes for performance
CREATE INDEX idx_rate_limits_user_type_date ON rate_limits(user_id, limit_type, date_toronto);
CREATE INDEX idx_global_limits_type_date ON global_limits(limit_type, date_toronto);
CREATE INDEX idx_openai_usage_user_date ON openai_usage_tracking(user_id, date_toronto);

-- Function to check user rate limit
CREATE OR REPLACE FUNCTION check_user_limit(
    p_user_id TEXT,
    p_limit_type TEXT
) RETURNS TABLE(
    current_count INTEGER,
    is_within_limit BOOLEAN
) AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    count_val INTEGER := 0;
BEGIN
    -- Get current count for user and limit type for today (Toronto time)
    SELECT COALESCE(request_count, 0) INTO count_val
    FROM rate_limits
    WHERE user_id = p_user_id 
    AND limit_type = p_limit_type 
    AND date_toronto = toronto_date;
    
    -- Return count and whether it's within reasonable limits (we'll check limits in Python)
    RETURN QUERY SELECT count_val, TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to increment user count
CREATE OR REPLACE FUNCTION increment_user_count(
    p_user_id TEXT,
    p_limit_type TEXT
) RETURNS INTEGER AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    new_count INTEGER;
BEGIN
    -- Insert or update user rate limit record
    INSERT INTO rate_limits (user_id, limit_type, request_count, date_toronto, last_updated)
    VALUES (p_user_id, p_limit_type, 1, toronto_date, NOW())
    ON CONFLICT (user_id, limit_type, date_toronto)
    DO UPDATE SET 
        request_count = rate_limits.request_count + 1,
        last_updated = NOW()
    RETURNING request_count INTO new_count;
    
    RETURN new_count;
END;
$$ LANGUAGE plpgsql;

-- Function to check global rate limit
CREATE OR REPLACE FUNCTION check_global_limit(
    p_limit_type TEXT
) RETURNS TABLE(
    current_count INTEGER,
    is_within_limit BOOLEAN
) AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    count_val INTEGER := 0;
BEGIN
    -- Get current count for global limit type for today (Toronto time)
    SELECT COALESCE(request_count, 0) INTO count_val
    FROM global_limits
    WHERE limit_type = p_limit_type 
    AND date_toronto = toronto_date;
    
    -- Return count and whether it's within reasonable limits (we'll check limits in Python)
    RETURN QUERY SELECT count_val, TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to increment global count
CREATE OR REPLACE FUNCTION increment_global_count(
    p_limit_type TEXT
) RETURNS INTEGER AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    new_count INTEGER;
BEGIN
    -- Insert or update global rate limit record
    INSERT INTO global_limits (limit_type, request_count, date_toronto, last_updated)
    VALUES (p_limit_type, 1, toronto_date, NOW())
    ON CONFLICT (limit_type, date_toronto)
    DO UPDATE SET 
        request_count = global_limits.request_count + 1,
        last_updated = NOW()
    RETURNING request_count INTO new_count;
    
    RETURN new_count;
END;
$$ LANGUAGE plpgsql;

-- Function to track OpenAI usage
CREATE OR REPLACE FUNCTION track_openai_usage(
    p_user_id TEXT,
    p_tokens_used INTEGER,
    p_cost DECIMAL(10, 6),
    p_model TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    toronto_timestamp TIMESTAMPTZ := NOW() AT TIME ZONE 'America/Toronto';
BEGIN
    -- Insert OpenAI usage record
    INSERT INTO openai_usage_tracking (user_id, tokens_used, cost, model, date_toronto, timestamp_toronto)
    VALUES (p_user_id, p_tokens_used, p_cost, p_model, toronto_date, toronto_timestamp);
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Function to reset rate limits (for daily cleanup at midnight Toronto time)
CREATE OR REPLACE FUNCTION reset_toronto_limits() RETURNS BOOLEAN AS $$
DECLARE
    toronto_date DATE := CURRENT_DATE AT TIME ZONE 'America/Toronto';
    deleted_user_count INTEGER;
    deleted_global_count INTEGER;
    deleted_openai_count INTEGER;
BEGIN
    -- Delete old user rate limit records (older than today Toronto time)
    DELETE FROM rate_limits WHERE date_toronto < toronto_date;
    GET DIAGNOSTICS deleted_user_count = ROW_COUNT;
    
    -- Delete old global rate limit records (older than today Toronto time)
    DELETE FROM global_limits WHERE date_toronto < toronto_date;
    GET DIAGNOSTICS deleted_global_count = ROW_COUNT;
    
    -- Keep OpenAI usage for 30 days for analytics
    DELETE FROM openai_usage_tracking WHERE date_toronto < (toronto_date - INTERVAL '30 days');
    GET DIAGNOSTICS deleted_openai_count = ROW_COUNT;
    
    -- Log the cleanup (this will show in PostgreSQL logs)
    RAISE NOTICE 'Rate limit reset complete: deleted % user records, % global records, % old OpenAI records',
        deleted_user_count, deleted_global_count, deleted_openai_count;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust role name as needed)
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limits TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON global_limits TO postgres;
GRANT SELECT, INSERT, UPDATE, DELETE ON openai_usage_tracking TO postgres;
GRANT USAGE ON SEQUENCE rate_limits_id_seq TO postgres;
GRANT USAGE ON SEQUENCE global_limits_id_seq TO postgres;
GRANT USAGE ON SEQUENCE openai_usage_tracking_id_seq TO postgres;
