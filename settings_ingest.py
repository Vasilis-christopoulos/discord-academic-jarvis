from pydantic_settings import BaseSettings, SettingsConfigDict 
from pydantic import Field, AliasChoices

class IngestSettings(BaseSettings):
    pinecone_api_key: str = Field(description="Pinecone API key")
    openai_api_key: str | None = Field(default=None, description="OpenAI API key (needed only if you caption with GPT/Vision)")
    openai_vision_model: str | None = Field(default="gpt-4o-2024-08-06", description="OpenAI vision model to use")
    aws_region_name: str = Field(
        default="ca-central-1", 
        description="AWS region name",
        validation_alias=AliasChoices('aws_region_name', 'AWS_REGION_NAME', 'AWS_REGION')
    )

    model_config = SettingsConfigDict(
        env_file = ".env",           # Load from .env file if present
        env_file_encoding = "utf-8", # Handle unicode in environment files
        case_sensitive = False,      # Allow case-insensitive env var names
        extra = "ignore"            # Ignore unknown environment variables
    )

settings = IngestSettings()