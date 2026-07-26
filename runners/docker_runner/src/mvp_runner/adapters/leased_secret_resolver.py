"""The runner's only real `SecretResolver` implementation.

Used exclusively by `entrypoints/daemon.py::run_job`, on the host side, before the
job container is launched — never by anything running inside the isolated job
container. This is the same trust-boundary shape ADR 0008 already establishes for
Git credentials ("coding agents receive neither network access nor source
credentials"): the daemon resolves, the container only ever sees an already-resolved
value, injected as an environment variable, and never a `SecretReference` or the
means to resolve one itself.
"""

from mvp_common.contracts import SecretReference

from mvp_runner.adapters.control_client import (
    ModelCredentialClient,
    RunnerControlClient,
    RunnerIdentity,
)
from mvp_runner.domain.errors import SecretResolutionFailed


class LeasedSecretResolver:
    """Structurally satisfies `application.ports.SecretResolver`."""

    def __init__(
        self,
        *,
        identity: RunnerIdentity,
        job_id: str,
        control: RunnerControlClient,
        credentials: ModelCredentialClient,
    ) -> None:
        self._identity = identity
        self._job_id = job_id
        self._control = control
        self._credentials = credentials

    async def resolve(self, reference: SecretReference) -> str:
        """Mint a fresh, single-use capability for this job and redeem it.

        No caching, no retry-on-401 — one resolve per job attempt, matching the
        capability's short TTL and one-time redemption on the integrations side.
        `reference` is accepted (rather than ignored) so a caller could, in
        principle, assert it matches what the job payload said; delivery is the
        source of truth for the reference embedded in the capability, so this
        resolver does not re-validate it beyond passing the call through.
        """
        try:
            capability = await self._control.model_capability(self._identity, self._job_id)
            return await self._credentials.exchange(capability)
        except Exception as error:  # normalize every failure mode into one error type
            raise SecretResolutionFailed(
                f"could not resolve model credential for job {self._job_id}"
            ) from error
