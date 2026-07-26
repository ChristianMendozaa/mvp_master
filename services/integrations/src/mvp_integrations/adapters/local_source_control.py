from uuid import uuid4

from mvp_common.contracts import ExternalReference

from mvp_integrations.application.ports import RepositoryDescriptor
from mvp_integrations.domain.models import (
    ConnectorInstallation,
    PullRequestResult,
    RepositoryConnection,
)


class LocalSourceControl:
    provider_name = "github-local"
    is_development_substitute = True

    def __init__(self) -> None:
        self.pull_requests: dict[str, PullRequestResult] = {}
        self.comments: list[dict[str, str]] = []
        self.check_runs: dict[str, dict[str, str]] = {}

    async def repositories(self, external_account_id: str) -> tuple[RepositoryDescriptor, ...]:
        return (
            RepositoryDescriptor(
                external_id=f"local-{external_account_id}-sample",
                owner=external_account_id,
                name="sample-webapp",
                default_branch="main",
                clone_locator="file:///fixtures/sample-webapp.git",
                is_private=True,
            ),
        )

    async def create_pull_request(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
        idempotency_key: str,
    ) -> PullRequestResult:
        existing = self.pull_requests.get(idempotency_key)
        if existing is not None:
            return existing
        number = len(self.pull_requests) + 1
        result = PullRequestResult(
            reference=ExternalReference(
                provider=self.provider_name,
                account_id=installation.external_account_id,
                repository=repository.full_name,
                resource_type="pull_request",
                external_id=str(number),
            ),
            title=title,
            url=f"http://localhost:3000/dev/github/pulls/{number}",
            head_branch=head_branch,
            base_branch=base_branch,
            is_development_substitute=True,
        )
        self.pull_requests[idempotency_key] = result
        return result

    async def add_comment(
        self,
        *,
        installation: ConnectorInstallation,
        external_reference_id: str,
        body: str,
        idempotency_key: str,
    ) -> None:
        self.comments.append(
            {
                "installation_id": str(installation.id),
                "external_reference_id": external_reference_id,
                "body": body,
                "idempotency_key": idempotency_key,
                "comment_id": str(uuid4()),
            }
        )

    async def create_check_run(
        self,
        *,
        installation: ConnectorInstallation,
        repository: RepositoryConnection,
        head_sha: str,
        name: str,
        summary: str,
        idempotency_key: str,
    ) -> None:
        self.check_runs.setdefault(
            idempotency_key,
            {
                "repository": repository.full_name,
                "head_sha": head_sha,
                "name": name,
                "summary": summary,
            },
        )
