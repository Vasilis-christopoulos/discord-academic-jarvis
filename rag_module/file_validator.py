"""
File validation and rate limiting for Discord Academic Jarvis.
Handles file upload limits, PDF page validation, and file size checks.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import os
import tempfile
import aiofiles
import PyPDF2
from io import BytesIO

from rag_module.rate_limiter import get_rate_limiter, RateLimitConfig
from rag_module.database_utils import get_supabase_client
from utils.logging_config import logger


@dataclass
class FileValidationResult:
    """Result of file validation including rate limiting."""
    allowed: bool
    message: str
    file_count: int
    daily_limit: int
    file_size_mb: float
    pdf_pages: Optional[int] = None
    error_code: Optional[str] = None


@dataclass
class FileValidationConfig:
    """Configuration for file validation."""
    max_files_per_day: int = 10
    max_pdf_pages: int = 20
    max_file_size_mb: int = 25
    allowed_extensions: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.allowed_extensions is None:
            self.allowed_extensions = ['.pdf', '.docx', '.txt', '.md']


class FileValidator:
    """Handles file validation and upload rate limiting."""
    
    def __init__(self, supabase_client, config: Optional[FileValidationConfig] = None):
        """Initialize file validator with database and configuration."""
        self.supabase = supabase_client
        self.config = config or FileValidationConfig()
        
        # Initialize rate limiter for global file limits
        rate_limit_config = RateLimitConfig(
            global_file_uploads=self.config.max_files_per_day,
            enable_rate_limiting=True
        )
        self.rate_limiter = get_rate_limiter(supabase_client, rate_limit_config)
        
        logger.info(f"File validator initialized: max_files={self.config.max_files_per_day}, "
                   f"max_pdf_pages={self.config.max_pdf_pages}, "
                   f"max_size={self.config.max_file_size_mb}MB")
    
    async def validate_file_upload(self, file_content: bytes, filename: str, 
                                  user_id: str) -> FileValidationResult:
        """
        Validate file upload against all limits.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            user_id: Discord user ID
            
        Returns:
            FileValidationResult with validation details
        """
        try:
            # Check file extension
            file_ext = os.path.splitext(filename.lower())[1]
            allowed_extensions = self.config.allowed_extensions or []
            if file_ext not in allowed_extensions:
                return FileValidationResult(
                    allowed=False,
                    message=f"❌ File type '{file_ext}' not allowed. Supported: {', '.join(allowed_extensions)}",
                    file_count=0,
                    daily_limit=self.config.max_files_per_day,
                    file_size_mb=0,
                    error_code="INVALID_FILE_TYPE"
                )
            
            # Check file size
            file_size_mb = len(file_content) / (1024 * 1024)
            if file_size_mb > self.config.max_file_size_mb:
                return FileValidationResult(
                    allowed=False,
                    message=f"❌ File too large: {file_size_mb:.1f}MB (max: {self.config.max_file_size_mb}MB)",
                    file_count=0,
                    daily_limit=self.config.max_files_per_day,
                    file_size_mb=file_size_mb,
                    error_code="FILE_TOO_LARGE"
                )
            
            # Check global file upload limit
            global_limit_result = await self.rate_limiter.check_global_limit("total_file_uploads")
            if not global_limit_result.allowed:
                return FileValidationResult(
                    allowed=False,
                    message=f"❌ Server upload limit reached: {global_limit_result.current_count}/{global_limit_result.daily_limit} files today",
                    file_count=global_limit_result.current_count,
                    daily_limit=global_limit_result.daily_limit,
                    file_size_mb=file_size_mb,
                    error_code="GLOBAL_LIMIT_EXCEEDED"
                )
            
            # Additional PDF validation
            pdf_pages = None
            if file_ext == '.pdf':
                pdf_pages = await self._validate_pdf(file_content)
                if pdf_pages is None:
                    return FileValidationResult(
                        allowed=False,
                        message="❌ Invalid or corrupted PDF file",
                        file_count=global_limit_result.current_count,
                        daily_limit=self.config.max_files_per_day,
                        file_size_mb=file_size_mb,
                        error_code="INVALID_PDF"
                    )
                
                if pdf_pages > self.config.max_pdf_pages:
                    return FileValidationResult(
                        allowed=False,
                        message=f"❌ PDF too long: {pdf_pages} pages (max: {self.config.max_pdf_pages} pages)",
                        file_count=global_limit_result.current_count,
                        daily_limit=self.config.max_files_per_day,
                        file_size_mb=file_size_mb,
                        pdf_pages=pdf_pages,
                        error_code="PDF_TOO_LONG"
                    )
            
            # All validations passed
            return FileValidationResult(
                allowed=True,
                message=f"✅ File validated: {filename} ({file_size_mb:.1f}MB{f', {pdf_pages} pages' if pdf_pages else ''})",
                file_count=global_limit_result.current_count,
                daily_limit=self.config.max_files_per_day,
                file_size_mb=file_size_mb,
                pdf_pages=pdf_pages
            )
            
        except Exception as e:
            logger.error(f"File validation error for {filename}: {e}")
            return FileValidationResult(
                allowed=False,
                message=f"❌ File validation failed: {str(e)}",
                file_count=0,
                daily_limit=self.config.max_files_per_day,
                file_size_mb=0,
                error_code="VALIDATION_ERROR"
            )
    
    async def increment_upload_count(self) -> int:
        """Increment the global file upload counter after successful upload."""
        try:
            new_count = await self.rate_limiter.increment_global_count("total_file_uploads")
            logger.info(f"Global file upload count incremented to: {new_count}")
            return new_count
        except Exception as e:
            logger.error(f"Failed to increment upload count: {e}")
            return 0
    
    async def get_upload_stats(self) -> Dict[str, Any]:
        """Get current upload statistics."""
        try:
            global_result = await self.rate_limiter.check_global_limit("total_file_uploads")
            return {
                'files_uploaded_today': global_result.current_count,
                'daily_limit': global_result.daily_limit,
                'remaining': global_result.daily_limit - global_result.current_count,
                'reset_time': 'midnight Toronto time'
            }
        except Exception as e:
            logger.error(f"Failed to get upload stats: {e}")
            return {'error': str(e)}
    
    async def _validate_pdf(self, file_content: bytes) -> Optional[int]:
        """
        Validate PDF and count pages.
        
        Args:
            file_content: PDF file bytes
            
        Returns:
            Number of pages, or None if invalid PDF
        """
        try:
            # Use BytesIO to read PDF from memory
            pdf_stream = BytesIO(file_content)
            
            # Try to read PDF with PyPDF2
            pdf_reader = PyPDF2.PdfReader(pdf_stream)
            
            # Get number of pages
            num_pages = len(pdf_reader.pages)
            
            # Basic validation - ensure we can read at least the first page
            if num_pages > 0:
                try:
                    first_page = pdf_reader.pages[0]
                    # Try to extract text to ensure it's a valid page
                    _ = first_page.extract_text()
                except:
                    # If we can't read the first page, treat as invalid
                    logger.warning("PDF appears corrupted - cannot read first page")
                    return None
            
            return num_pages
            
        except Exception as e:
            logger.error(f"PDF validation failed: {e}")
            return None
    
    def get_allowed_file_types(self) -> List[str]:
        """Get list of allowed file extensions."""
        return self.config.allowed_extensions.copy() if self.config.allowed_extensions else []
    
    def get_limits_summary(self) -> Dict[str, Any]:
        """Get summary of all file limits."""
        return {
            'max_files_per_day': self.config.max_files_per_day,
            'max_pdf_pages': self.config.max_pdf_pages,
            'max_file_size_mb': self.config.max_file_size_mb,
            'allowed_extensions': self.config.allowed_extensions,
            'timezone': 'America/Toronto'
        }


# Singleton instance
_file_validator = None

def get_file_validator(supabase_client=None, config: Optional[FileValidationConfig] = None) -> FileValidator:
    """Get singleton file validator instance."""
    global _file_validator
    
    if _file_validator is None:
        if supabase_client is None:
            supabase_client = get_supabase_client()
        _file_validator = FileValidator(supabase_client, config)
    
    return _file_validator
