from collections.abc import Collection

from mvp_control_plane.domain.errors import PermissionDenied
from mvp_control_plane.domain.models import Role

PROJECT_EDITORS = {Role.OWNER, Role.ADMIN, Role.DEVELOPER}
REVIEWERS = {Role.OWNER, Role.ADMIN, Role.REVIEWER}
INTAKE_CREATORS = PROJECT_EDITORS | {Role.CLIENT}
EXECUTION_REQUESTERS = PROJECT_EDITORS | {Role.REVIEWER}


def require_role(actual: Role | None, allowed: Collection[Role]) -> Role:
    if actual is None or actual not in allowed:
        raise PermissionDenied("the current membership cannot perform this action")
    return actual
