"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import type { BrowserSession } from "@/lib/auth";

type OrganizationChoice = {
  organization: { id: string; name: string };
  role: string;
};
type Dashboard = {
  projects: Array<{ id: string; name: string; description: string }>;
  intakes: Array<{
    id: string;
    project_id: string;
    problem: string;
    status: string;
  }>;
  specifications: Array<{
    id: string;
    intake_id: string;
    status: string;
    current_version: number;
  }>;
  work_items: Array<{
    id: string;
    title: string;
    status: string;
    version: number;
    budget?: { max_cost_minor: number; currency: string };
  }>;
  audits: Array<{
    id: number;
    action: string;
    actor_subject: string;
    created_at: string;
  }>;
};
type Repository = {
  id: string;
  owner: string;
  name: string;
  is_development_substitute: boolean;
};
type Provider = {
  id: string;
  display_name: string;
  provider: string;
  runtime: string;
  model: string;
  is_development_substitute: boolean;
  verification_status: string;
};
type SourceControlConfiguration = {
  id: string;
  display_name: string;
  provider: string;
  app_slug: string;
  webhook_mode: string;
};
type RunnerPool = {
  id: string;
  name: string;
  runner_type: string;
  online_runner_count: number;
  capabilities: string[];
};
type Execution = {
  id: string;
  work_item_id: string;
  status: string;
  approval_status: string;
  attempt_count: number;
  turn_count: number;
  cost_minor: number;
  budget: { max_cost_minor: number; currency: string };
  result_reference?: {
    external_id: string;
    repository?: string;
    provider: string;
  };
};
type TimelineEvent = {
  sequence: number;
  kind: string;
  name: string;
  message: string;
};

function csrfToken(): string {
  const entry = document.cookie
    .split("; ")
    .find((item) => item.startsWith("mvp_csrf_token="));
  return entry?.split("=")[1] ?? "";
}

async function api<T>(
  service: "control" | "integrations" | "delivery",
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/bff/${service}/${path}`, {
    ...options,
    headers: {
      "content-type": "application/json",
      "x-csrf-token": csrfToken(),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function ControlPlane({
  session,
}: {
  session: BrowserSession;
}): React.ReactElement {
  const [organizations, setOrganizations] = useState<OrganizationChoice[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [sourceConfigurations, setSourceConfigurations] = useState<
    SourceControlConfiguration[]
  >([]);
  const [pools, setPools] = useState<RunnerPool[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [selectedExecution, setSelectedExecution] = useState("");
  const [selectedRepository, setSelectedRepository] = useState("");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [selectedPool, setSelectedPool] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const reloadOrganizations = useCallback(async () => {
    const data = await api<OrganizationChoice[]>("control", "organizations");
    setOrganizations(data);
    setOrganizationId((current) => current || data[0]?.organization.id || "");
  }, []);

  const reload = useCallback(async () => {
    if (!organizationId) return;
    const [
      control,
      repos,
      providerData,
      poolData,
      executionData,
      sourceConfigurationData,
    ] = await Promise.all([
      api<Dashboard>("control", `organizations/${organizationId}/dashboard`),
      api<Repository[]>(
        "integrations",
        `organizations/${organizationId}/repositories`,
      ),
      api<Provider[]>(
        "delivery",
        `organizations/${organizationId}/provider-configurations`,
      ),
      api<RunnerPool[]>(
        "delivery",
        `organizations/${organizationId}/runner-pools`,
      ),
      api<Execution[]>(
        "delivery",
        `organizations/${organizationId}/executions`,
      ),
      api<SourceControlConfiguration[]>(
        "integrations",
        `organizations/${organizationId}/source-control-configurations`,
      ).catch(() => []),
    ]);
    setDashboard(control);
    setRepositories(repos);
    setProviders(providerData);
    setPools(poolData);
    setExecutions(executionData);
    setSourceConfigurations(sourceConfigurationData);
    setSelectedExecution((current) => current || executionData[0]?.id || "");
    if (
      (!repos.length ||
        !providerData.some(
          (provider) => provider.verification_status === "PASSED",
        )) &&
      window.location.pathname === "/app"
    ) {
      window.location.replace("/app/onboarding");
    }
  }, [organizationId]);

  async function installGitHub(configurationId: string): Promise<void> {
    const result = await api<{ installation_url: string; state: string }>(
      "integrations",
      `organizations/${organizationId}/github/installations`,
      {
        method: "POST",
        body: JSON.stringify({ configuration_id: configurationId }),
      },
    );
    window.sessionStorage.setItem("mvp_github_organization_id", organizationId);
    window.location.assign(result.installation_url);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reloadOrganizations().catch((cause: unknown) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "Failed to load organizations",
        ),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [reloadOrganizations]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reload().catch((cause: unknown) =>
        setError(
          cause instanceof Error ? cause.message : "Failed to load workspace",
        ),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [reload]);

  useEffect(() => {
    if (!selectedExecution || !organizationId) return;
    const resetTimer = window.setTimeout(() => setTimeline([]), 0);
    const source = new EventSource(
      `/api/bff/delivery/organizations/${organizationId}/executions/${selectedExecution}/events`,
    );
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as TimelineEvent;
      setTimeline((current) =>
        current.some((item) => item.sequence === event.sequence)
          ? current
          : [...current, event],
      );
    };
    source.onerror = () => {
      source.close();
      void reload();
    };
    return () => {
      window.clearTimeout(resetTimer);
      source.close();
    };
  }, [organizationId, reload, selectedExecution]);

  async function action(
    label: string,
    operation: () => Promise<unknown>,
  ): Promise<void> {
    setBusy(label);
    setError("");
    try {
      await operation();
      await reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy("");
    }
  }

  async function createOrganization(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await action("organization", async () => {
      const created = await api<{ id: string }>("control", "organizations", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name") }),
      });
      await reloadOrganizations();
      setOrganizationId(created.id);
    });
  }

  async function createProject(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await action("project", () =>
      api("control", `organizations/${organizationId}/projects`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description"),
        }),
      }),
    );
    event.currentTarget.reset();
  }

  async function submitIntake(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await action("intake", () =>
      api("control", `organizations/${organizationId}/intakes`, {
        method: "POST",
        body: JSON.stringify({
          project_id: form.get("project_id"),
          problem: form.get("problem"),
          intended_users: form.get("intended_users"),
          required_functionality: String(form.get("functionality"))
            .split("\n")
            .filter(Boolean),
          exclusions: String(form.get("exclusions"))
            .split("\n")
            .filter(Boolean),
          constraints: String(form.get("constraints"))
            .split("\n")
            .filter(Boolean),
        }),
      }),
    );
    event.currentTarget.reset();
  }

  const currentExecution = executions.find(
    (item) => item.id === selectedExecution,
  );
  const readyRepository = repositories.find(
    (item) => item.id === selectedRepository,
  );
  const readyProvider = providers.find((item) => item.id === selectedProvider);
  const readyPool = pools.find((item) => item.id === selectedPool);

  return (
    <main className="shell">
      <header
        className="card"
        style={{
          display: "flex",
          gap: "1rem",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <span className="eyebrow">MVP Master</span>
          <h1 style={{ margin: "0.25rem 0 0" }}>Delivery control plane</h1>
        </div>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
          <span className="muted">{session.email ?? session.subject}</span>
          {session.isPlatformOperator ? (
            <a href="/app/admin/integrations/github">GitHub settings</a>
          ) : null}
          <form action="/api/auth/logout" method="post">
            <button className="secondary" type="submit">
              Sign out
            </button>
          </form>
        </div>
      </header>

      {error ? (
        <div
          className="card"
          role="alert"
          style={{ borderColor: "var(--danger)", marginBottom: "1rem" }}
        >
          <strong>Action required</strong>
          <p style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : null}

      <section className="card" style={{ marginBottom: "1rem" }}>
        <div
          style={{
            display: "grid",
            gap: "1rem",
            gridTemplateColumns: "2fr 1fr",
          }}
        >
          <label>
            Organization
            <select
              value={organizationId}
              onChange={(event) => setOrganizationId(event.target.value)}
            >
              {organizations.map((choice) => (
                <option
                  key={choice.organization.id}
                  value={choice.organization.id}
                >
                  {choice.organization.name} · {choice.role}
                </option>
              ))}
            </select>
          </label>
          <form
            onSubmit={createOrganization}
            style={{ display: "flex", gap: "0.5rem", alignItems: "end" }}
          >
            <label style={{ flex: 1 }}>
              New organization
              <input
                name="name"
                minLength={2}
                required
                placeholder="Organization name"
              />
            </label>
            <button disabled={busy === "organization"}>Create</button>
          </form>
        </div>
      </section>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        <section className="card">
          <p className="eyebrow">1 · Project and intake</p>
          <h2>Define the client need</h2>
          {!dashboard?.projects.length ? (
            <form
              onSubmit={createProject}
              style={{ display: "grid", gap: "0.8rem" }}
            >
              <label>
                Project name
                <input name="name" required minLength={2} />
              </label>
              <label>
                Description
                <textarea name="description" required />
              </label>
              <button disabled={busy === "project"}>Create project</button>
            </form>
          ) : (
            <form
              onSubmit={submitIntake}
              style={{ display: "grid", gap: "0.8rem" }}
            >
              <label>
                Project
                <select name="project_id">
                  {dashboard.projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Problem
                <textarea
                  name="problem"
                  required
                  minLength={10}
                  placeholder="What is not working today?"
                />
              </label>
              <label>
                Intended users
                <input
                  name="intended_users"
                  required
                  placeholder="Client stakeholders"
                />
              </label>
              <label>
                Required functionality · one per line
                <textarea name="functionality" required />
              </label>
              <label>
                Exclusions · one per line
                <textarea name="exclusions" />
              </label>
              <label>
                Constraints · one per line
                <textarea name="constraints" />
              </label>
              <button disabled={busy === "intake"}>
                Submit structured intake
              </button>
            </form>
          )}
        </section>

        <section className="card">
          <p className="eyebrow">2 · Scope approval</p>
          <h2>Review the specification</h2>
          {!dashboard?.intakes.length ? (
            <p className="muted">No intake has been submitted.</p>
          ) : null}
          {dashboard?.intakes.map((intake) => {
            const specification = dashboard.specifications.find(
              (item) => item.intake_id === intake.id,
            );
            return (
              <article
                key={intake.id}
                style={{
                  borderTop: "1px solid var(--line)",
                  padding: "1rem 0",
                }}
              >
                <span className="status">
                  {intake.status.replaceAll("_", " ")}
                </span>
                <p>{intake.problem}</p>
                {!specification ? (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void action("draft", () =>
                        api(
                          "control",
                          `organizations/${organizationId}/intakes/${intake.id}/specifications`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              title: "Approved client requirement",
                            }),
                          },
                        ),
                      )
                    }
                  >
                    Draft specification v1
                  </button>
                ) : specification.status === "DRAFT" ? (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void action("submit-spec", () =>
                        api(
                          "control",
                          `organizations/${organizationId}/specifications/${specification.id}/submit`,
                          { method: "POST", body: "{}" },
                        ),
                      )
                    }
                  >
                    Submit v{specification.current_version} for approval
                  </button>
                ) : specification.status === "AWAITING_APPROVAL" ? (
                  <button
                    disabled={Boolean(busy)}
                    onClick={() =>
                      void action("approve-spec", () =>
                        api(
                          "control",
                          `organizations/${organizationId}/specifications/${specification.id}/approve`,
                          {
                            method: "POST",
                            body: JSON.stringify({
                              reason: "Scope reviewed in the control plane.",
                            }),
                          },
                        ),
                      )
                    }
                  >
                    Approve exact version
                  </button>
                ) : (
                  <p className="muted">
                    Version {specification.current_version} approved.
                  </p>
                )}
              </article>
            );
          })}
        </section>

        <section className="card">
          <p className="eyebrow">3 · Execution readiness</p>
          <h2>Authorize controlled work</h2>
          <p className="muted">
            The local connector and deterministic agent are development
            substitutes.
          </p>
          {readyRepository ? (
            <p>
              <span
                className={
                  readyRepository.is_development_substitute
                    ? "status local"
                    : "status"
                }
              >
                {readyRepository.is_development_substitute
                  ? "Local substitute"
                  : "GitHub"}
              </span>{" "}
              {readyRepository.owner}/{readyRepository.name}
            </p>
          ) : repositories.length === 0 ? (
            <button
              onClick={() =>
                void action("connector", () =>
                  api(
                    "integrations",
                    `organizations/${organizationId}/connections`,
                    {
                      method: "POST",
                      body: JSON.stringify({
                        provider: "github-local",
                        external_account_id: "acme-local",
                        account_login: "Acme Local",
                      }),
                    },
                  ),
                )
              }
            >
              Connect simulated GitHub App
            </button>
          ) : null}
          {sourceConfigurations.map((configuration) => (
            <button
              className="secondary"
              key={configuration.id}
              onClick={() =>
                void action("github-installation", () =>
                  installGitHub(configuration.id),
                )
              }
            >
              Connect {configuration.display_name}
            </button>
          ))}
          {repositories.length && providers.length && pools.length ? (
            <div
              style={{
                display: "grid",
                gap: "0.75rem",
                margin: "1rem 0",
              }}
            >
              <label>
                Repository for this work
                <select
                  value={selectedRepository}
                  onChange={(event) =>
                    setSelectedRepository(event.target.value)
                  }
                >
                  <option value="">Select repository</option>
                  {repositories.map((repository) => (
                    <option key={repository.id} value={repository.id}>
                      {repository.owner}/{repository.name}
                      {repository.is_development_substitute ? " · local" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Coding agent
                <select
                  value={selectedProvider}
                  onChange={(event) => setSelectedProvider(event.target.value)}
                >
                  <option value="">Select verified agent</option>
                  {providers
                    .filter(
                      (provider) => provider.verification_status === "PASSED",
                    )
                    .map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.display_name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Runner pool
                <select
                  value={selectedPool}
                  onChange={(event) => setSelectedPool(event.target.value)}
                >
                  <option value="">Select available runner</option>
                  {pools
                    .filter((pool) => pool.online_runner_count > 0)
                    .map((pool) => (
                      <option key={pool.id} value={pool.id}>
                        {pool.name} · {pool.online_runner_count} online
                      </option>
                    ))}
                </select>
              </label>
            </div>
          ) : null}
          {dashboard?.work_items.map((item) => (
            <article
              key={item.id}
              data-testid={`work-item-${item.id}`}
              style={{ borderTop: "1px solid var(--line)", padding: "1rem 0" }}
            >
              <span className="status">{item.status.replaceAll("_", " ")}</span>
              <h3>{item.title}</h3>
              {item.status === "WORK_ITEMS_GENERATED" ? (
                <button
                  onClick={() =>
                    void action("review-work", () =>
                      api(
                        "control",
                        `organizations/${organizationId}/work-items/${item.id}/review`,
                        {
                          method: "POST",
                          body: "{}",
                        },
                      ),
                    )
                  }
                >
                  Mark work item reviewed
                </button>
              ) : item.status === "WORK_ITEMS_REVIEWED" ? (
                <button
                  disabled={
                    !readyRepository ||
                    !readyProvider ||
                    !readyPool ||
                    !readyPool.capabilities.includes(readyProvider.runtime)
                  }
                  onClick={() =>
                    void action("ready-work", () =>
                      api(
                        "control",
                        `organizations/${organizationId}/work-items/${item.id}/ready`,
                        {
                          method: "POST",
                          body: JSON.stringify({
                            repository_connection_id: readyRepository?.id,
                            provider_configuration_id: readyProvider?.id,
                            runner_pool_id: readyPool?.id,
                            budget: {
                              max_duration_seconds: 600,
                              max_attempts: 2,
                              max_turns: 8,
                              max_cost_minor: 500,
                              currency: "USD",
                            },
                          }),
                        },
                      ),
                    )
                  }
                >
                  Ready with $5.00 maximum
                </button>
              ) : (
                <p className="muted">Ready event published idempotently.</p>
              )}
            </article>
          ))}
        </section>

        <section className="card">
          <p className="eyebrow">4 · Independent evidence</p>
          <h2>Execution timeline</h2>
          <label>
            Execution
            <select
              value={selectedExecution}
              onChange={(event) => setSelectedExecution(event.target.value)}
            >
              <option value="">No execution yet</option>
              {executions.map((execution) => (
                <option key={execution.id} value={execution.id}>
                  {execution.status} · {execution.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          {currentExecution?.status === "AWAITING_APPROVAL" ? (
            <button
              style={{ marginTop: "1rem" }}
              onClick={() =>
                void action("approve-execution", () =>
                  api(
                    "delivery",
                    `organizations/${organizationId}/executions/${currentExecution.id}/approve`,
                    { method: "POST", body: "{}" },
                  ),
                )
              }
            >
              Approve execution budget
            </button>
          ) : null}
          {currentExecution ? (
            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "0.5rem",
              }}
            >
              <div>
                <dt className="muted">Status</dt>
                <dd>{currentExecution.status}</dd>
              </div>
              <div>
                <dt className="muted">Cost</dt>
                <dd>
                  ${(currentExecution.cost_minor / 100).toFixed(2)} / $
                  {(currentExecution.budget.max_cost_minor / 100).toFixed(2)}
                </dd>
              </div>
            </dl>
          ) : null}
          <ol style={{ paddingLeft: "1.25rem" }}>
            {timeline.map((event) => (
              <li key={event.sequence} style={{ marginBottom: "0.75rem" }}>
                <strong>{event.name}</strong>
                <div className="muted">{event.message}</div>
              </li>
            ))}
          </ol>
          {currentExecution?.result_reference ? (
            <div>
              <span className="status local">Simulated pull request</span>
              <p>
                {currentExecution.result_reference.repository} #
                {currentExecution.result_reference.external_id}
              </p>
            </div>
          ) : null}
        </section>

        <section className="card">
          <p className="eyebrow">Audit</p>
          <h2>Security-sensitive decisions</h2>
          {!dashboard?.audits.length ? (
            <p className="muted">No audit events yet.</p>
          ) : null}
          {dashboard?.audits.slice(0, 12).map((audit) => (
            <div
              key={audit.id}
              style={{
                borderTop: "1px solid var(--line)",
                padding: "0.7rem 0",
              }}
            >
              <strong>{audit.action}</strong>
              <div className="muted">
                {new Date(audit.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
