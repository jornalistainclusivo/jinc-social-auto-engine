class DomainError(Exception):
    """Base exception for all domain errors."""

    pass


class ConcurrentModificationError(DomainError):
    """Raised when CAS (Compare-And-Swap) fails due to concurrent modifications."""

    pass


class StateTransitionRejected(DomainError):
    """Raised when an invalid state transition is attempted."""

    pass


class InvariantViolationError(DomainError):
    """Raised when a business invariant is violated."""

    pass
