"""Unified LLM exception types."""


class LLMError(Exception):
    """Base exception for all LLM-related errors."""
    pass


class LLMConfigError(LLMError):
    """Raised when LLM configuration is invalid or missing."""
    pass


class LLMProviderError(LLMError):
    """Raised when LLM provider returns an error."""
    def __init__(self, message: str, status_code: int | None = None, raw_response: str | None = None):
        self.status_code = status_code
        self.raw_response = raw_response
        super().__init__(message)


class LLMRateLimitError(LLMProviderError):
    """Raised when rate limit is exceeded."""
    pass


class LLMOutputError(LLMError):
    """Raised when LLM response cannot be parsed."""
    def __init__(self, message: str, raw_response: str | None = None):
        self.message = message
        self.raw_response = raw_response
        super().__init__(message)

    def __str__(self) -> str:
        if self.raw_response:
            return f"{self.message} (raw: {self.raw_response[:200]})"
        return self.message
