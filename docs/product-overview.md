# Product overview

MVP Master helps an organization receive client requirements, preserve their review history, convert approved specifications into executable work items, and deliver independently verified repository changes.

The canonical domain does not depend on GitHub, OpenAI, Anthropic, Docker, or any cloud. Those systems enter through adapters. A provider, model, agent runtime, authentication mode, and billing mode are separate explicit selections.

The first implemented product path is intentionally narrow:

1. Authenticate and create an organization and project.
2. Connect a simulated GitHub App/repository through the production connector port.
3. Submit structured intake and approve a versioned specification.
4. Review and ready a generated work item.
5. Select a deterministic coding-agent adapter and a registered local runner.
6. Execute in an isolated workspace, independently run validation, and produce a commit plus simulated pull request.
7. Review execution events, evidence, costs, and audit history.

Real GitHub App and Codex adapters are opt-in. They are never substituted silently.
