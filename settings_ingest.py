"""
Minimal settings module for Lambda environment.

This is a simplified version of settings.py specifically for Lambda functions
that don't need the full tenant configuration but need basic API keys.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class IngestSettings(BaseSettings):
    """Minimal settings for document ingestion Lambda functions."""
    
    openai_api_key: str = Field(default="")
    pinecone_api_key: str = Field(default="")
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    aws_region_name: str = Field(default="ca-central-1")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from environment


# Initialize settings
settings = IngestSettings()
