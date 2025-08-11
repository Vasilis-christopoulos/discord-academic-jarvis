-- CLEANUP SCRIPT: Remove old function signatures that conflict with new TEXT versions
-- Run this BEFORE running the main schema update

-- Drop all possible function signatures (both old bigint and new text versions)
DROP FUNCTION IF EXISTS check_user_limit(bigint, character varying);
DROP FUNCTION IF EXISTS check_user_limit(bigint, text);
DROP FUNCTION IF EXISTS check_user_limit(text, character varying);
DROP FUNCTION IF EXISTS check_user_limit(text, text);

DROP FUNCTION IF EXISTS increment_user_count(bigint, character varying);
DROP FUNCTION IF EXISTS increment_user_count(bigint, text);
DROP FUNCTION IF EXISTS increment_user_count(text, character varying);
DROP FUNCTION IF EXISTS increment_user_count(text, text);

DROP FUNCTION IF EXISTS check_global_limit(character varying);
DROP FUNCTION IF EXISTS check_global_limit(text);

DROP FUNCTION IF EXISTS increment_global_count(character varying);
DROP FUNCTION IF EXISTS increment_global_count(text);

DROP FUNCTION IF EXISTS track_openai_usage(bigint, integer, numeric, character varying);
DROP FUNCTION IF EXISTS track_openai_usage(bigint, integer, numeric, text);
DROP FUNCTION IF EXISTS track_openai_usage(text, integer, numeric, character varying);
DROP FUNCTION IF EXISTS track_openai_usage(text, integer, numeric, text);
DROP FUNCTION IF EXISTS track_openai_usage(text, integer, decimal, text);

DROP FUNCTION IF EXISTS reset_toronto_limits();

-- Now the main schema can be applied without conflicts
