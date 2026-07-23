"""Universal, provider-neutral primitives shared across service boundaries."""

from mvp_common.contracts import EventEnvelope, ExternalReference, SecretReference
from mvp_common.ids import EntityId, new_id

__all__ = [
    "EntityId",
    "EventEnvelope",
    "ExternalReference",
    "SecretReference",
    "new_id",
]
