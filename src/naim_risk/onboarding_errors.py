"""Lightweight error contract for governed data onboarding."""


class OnboardingError(RuntimeError):
    """Base error safe to translate into a client validation response."""


class SourceSafetyError(OnboardingError):
    """Raised when a source violates the governed filesystem or format boundary."""


class SourceReadError(OnboardingError):
    """Raised when a supported source is malformed or cannot be read safely."""


class FormulaSafetyError(OnboardingError):
    """Raised when a transformation is outside the restricted expression language."""


class ProfileApprovalError(OnboardingError):
    """Raised when an import profile cannot enter the requested approval state."""
