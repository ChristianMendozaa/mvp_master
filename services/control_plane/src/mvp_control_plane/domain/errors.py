class DomainError(Exception):
    code = "domain_error"


class InvalidTransition(DomainError):
    code = "invalid_transition"


class PermissionDenied(DomainError):
    code = "permission_denied"


class NotFound(DomainError):
    code = "not_found"


class Conflict(DomainError):
    code = "conflict"
