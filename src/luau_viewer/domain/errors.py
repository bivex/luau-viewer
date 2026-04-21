"""Domain and application-facing errors."""


class LuauViewerError(Exception):
    """Base type for all system errors."""


class BusinessRuleViolation(LuauViewerError):
    """Raised when a domain invariant is violated."""


class EmptyParsingJobError(BusinessRuleViolation):
    """Raised when a parsing job has no source units."""


class DuplicateSourceUnitError(BusinessRuleViolation):
    """Raised when the same source unit is added twice to one job."""


class UnknownSourceUnitError(BusinessRuleViolation):
    """Raised when an outcome is recorded for an unknown source unit."""


class ParsingJobAlreadyCompletedError(BusinessRuleViolation):
    """Raised when mutating a completed parsing job."""


class ParsingJobNotCompleteError(BusinessRuleViolation):
    """Raised when completing a job before every outcome is known."""


class InputValidationError(LuauViewerError):
    """Raised for invalid user input at the system boundary."""


class SourceAccessError(LuauViewerError):
    """Raised when the system cannot access or decode a source file."""


class GeneratedParserNotAvailableError(LuauViewerError):
    """Raised when generated ANTLR artifacts are missing."""
