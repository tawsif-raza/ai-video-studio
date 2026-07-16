class AgentError(Exception):
    """Base exception every agent-related error inherits from."""


class LLMCallError(AgentError):
    """The LLM call itself failed or returned nothing usable."""


class SchemaValidationError(AgentError):
    """The LLM's JSON doesn't match the expected schema shape."""


class ContractViolationError(AgentError):
    """Valid shape, but violates a business rule (e.g. duration way off target)."""