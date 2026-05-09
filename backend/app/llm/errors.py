class LLMConfigurationError(RuntimeError):
    """Raised when the selected LLM provider is not configured enough to run."""


class LLMProviderError(RuntimeError):
    """Raised when a provider fails or returns invalid structured output."""
