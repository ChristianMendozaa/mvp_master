class IntegrationError(Exception):
    code = "integration_error"


class InvalidInstallationState(IntegrationError):
    code = "invalid_installation_state"


class RepositoryAccessDenied(IntegrationError):
    code = "repository_access_denied"


class DuplicateDelivery(IntegrationError):
    code = "duplicate_delivery"
