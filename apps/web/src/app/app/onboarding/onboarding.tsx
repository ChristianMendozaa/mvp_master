"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import type { BrowserSession } from "@/lib/auth";

type OrganizationChoice = {
  organization: { id: string; name: string };
  role: string;
};
type Repository = {
  id: string;
  owner: string;
  name: string;
  is_development_substitute: boolean;
};
type SourceConfiguration = {
  id: string;
  display_name: string;
  provider: string;
};
type ProviderConfiguration = {
  id: string;
  display_name: string;
  provider: string;
  runtime: string;
  model: string;
  verification_status: string;
};
type RunnerPool = {
  id: string;
  name: string;
  runner_type: string;
  online_runner_count: number;
  capabilities: string[];
};
type CatalogEntry = {
  provider: string;
  provider_display_name: string;
  runtime: string;
  runtime_display_name: string;
  models: string[];
  recommended_model: string;
  tier: "PRIMARY" | "ADVANCED";
};
type Verification = {
  id: string;
  status: "QUEUED" | "RUNNING" | "PASSED" | "FAILED" | "CANCELLED";
  result?: { summary?: string } | null;
};

function csrfToken(): string {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("mvp_csrf_token="))
      ?.split("=")[1] ?? ""
  );
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
  if (!response.ok)
    throw new Error((await response.text()) || "Request failed");
  return response.json() as Promise<T>;
}

function stepClass(done: boolean, active: boolean): string {
  if (done) return "onboarding-step complete";
  if (active) return "onboarding-step active";
  return "onboarding-step";
}

export function Onboarding({
  session,
}: {
  session: BrowserSession;
}): React.ReactElement {
  const [organizations, setOrganizations] = useState<OrganizationChoice[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [sourceConfigurations, setSourceConfigurations] = useState<
    SourceConfiguration[]
  >([]);
  const [providers, setProviders] = useState<ProviderConfiguration[]>([]);
  const [pools, setPools] = useState<RunnerPool[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [selectedOption, setSelectedOption] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [verification, setVerification] = useState<Verification | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadOrganization = useCallback(async () => {
    const data = await api<OrganizationChoice[]>("control", "organizations");
    setOrganizations(data);
    setOrganizationId((current) => current || data[0]?.organization.id || "");
  }, []);

  const reload = useCallback(async () => {
    if (!organizationId) return;
    const [repoData, sourceData, providerData, poolData, catalogData] =
      await Promise.all([
        api<Repository[]>(
          "integrations",
          `organizations/${organizationId}/repositories`,
        ),
        api<SourceConfiguration[]>(
          "integrations",
          `organizations/${organizationId}/source-control-configurations`,
        ).catch(() => []),
        api<ProviderConfiguration[]>(
          "delivery",
          `organizations/${organizationId}/provider-configurations`,
        ),
        api<RunnerPool[]>(
          "delivery",
          `organizations/${organizationId}/runner-pools`,
        ),
        api<CatalogEntry[]>(
          "delivery",
          `organizations/${organizationId}/agent-catalog`,
        ),
      ]);
    setRepositories(repoData);
    setSourceConfigurations(sourceData);
    setProviders(providerData);
    setPools(poolData);
    setCatalog(catalogData);
    const first = catalogData.find((item) => item.tier === "PRIMARY");
    if (first) {
      setSelectedOption(
        (current) => current || `${first.provider}|${first.runtime}`,
      );
      setSelectedModel((current) => current || first.recommended_model);
    }
  }, [organizationId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadOrganization().catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "No se pudo iniciar"),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadOrganization]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void reload().catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "No se pudo cargar"),
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [reload]);

  useEffect(() => {
    if (
      !verification ||
      !organizationId ||
      !["QUEUED", "RUNNING"].includes(verification.status)
    )
      return;
    const provider = providers.find((item) =>
      item.id
        ? item.verification_status === verification.status ||
          item.verification_status === "NOT_VERIFIED"
        : false,
    );
    const providerId =
      window.sessionStorage.getItem("mvp_provider_verifying") ?? provider?.id;
    if (!providerId) return;
    const timer = window.setInterval(() => {
      void api<Verification>(
        "delivery",
        `organizations/${organizationId}/provider-configurations/${providerId}/verifications/latest`,
      )
        .then((value) => {
          setVerification(value);
          if (!["QUEUED", "RUNNING"].includes(value.status)) {
            window.clearInterval(timer);
            void reload();
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [organizationId, providers, reload, verification]);

  const selected = useMemo(
    () =>
      catalog.find(
        (item) => `${item.provider}|${item.runtime}` === selectedOption,
      ),
    [catalog, selectedOption],
  );
  const readyPool = pools.find(
    (pool) =>
      pool.online_runner_count > 0 &&
      (!selected || pool.capabilities.includes(selected.runtime)),
  );
  const verifiedProvider = providers.find(
    (provider) => provider.verification_status === "PASSED",
  );
  const githubDone = repositories.length > 0;
  const agentDone = Boolean(verifiedProvider);

  async function installGitHub(configurationId: string): Promise<void> {
    setBusy("github");
    setError("");
    try {
      const result = await api<{ installation_url: string }>(
        "integrations",
        `organizations/${organizationId}/github/installations`,
        {
          method: "POST",
          body: JSON.stringify({ configuration_id: configurationId }),
        },
      );
      window.sessionStorage.setItem(
        "mvp_github_organization_id",
        organizationId,
      );
      window.location.assign(result.installation_url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Conexión fallida");
      setBusy("");
    }
  }

  async function connectDevelopmentRepository(): Promise<void> {
    setBusy("local-repository");
    setError("");
    try {
      await api("integrations", `organizations/${organizationId}/connections`, {
        method: "POST",
        body: JSON.stringify({
          provider: "github-local",
          external_account_id: "local-onboarding",
          account_login: "Local onboarding",
        }),
      });
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Conexión local fallida",
      );
    } finally {
      setBusy("");
    }
  }

  async function configureAgent(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    if (!selected || !readyPool) return;
    const form = new FormData(event.currentTarget);
    const key = String(form.get("api_key") ?? "");
    const operationId = crypto.randomUUID();
    setBusy("agent");
    setError("");
    try {
      const credential = await api<{
        store: string;
        namespace: string;
        key: string;
      }>("integrations", `organizations/${organizationId}/model-credentials`, {
        method: "POST",
        headers: { "Idempotency-Key": operationId },
        body: JSON.stringify({
          value: key,
          provider: selected.provider,
          display_name: `${selected.provider_display_name} onboarding key`,
        }),
      });
      const provider = await api<{ id: string }>(
        "delivery",
        `organizations/${organizationId}/provider-configurations`,
        {
          method: "POST",
          body: JSON.stringify({
            display_name: `${selected.runtime_display_name} · ${selectedModel}`,
            provider: selected.provider,
            runtime: selected.runtime,
            model: selectedModel,
            authentication_mode: "API_KEY_REFERENCE",
            secret_reference: {
              store: credential.store,
              namespace: credential.namespace,
              key: credential.key,
            },
            is_development_substitute: false,
          }),
        },
      );
      window.sessionStorage.setItem("mvp_provider_verifying", provider.id);
      const started = await api<Verification>(
        "delivery",
        `organizations/${organizationId}/provider-configurations/${provider.id}/verifications`,
        {
          method: "POST",
          headers: { "Idempotency-Key": operationId },
          body: JSON.stringify({ runner_pool_id: readyPool.id }),
        },
      );
      setVerification(started);
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "No se pudo configurar",
      );
    } finally {
      setBusy("");
    }
  }

  async function configureDevelopmentAgent(): Promise<void> {
    if (!pools[0]) return;
    setBusy("local-agent");
    setError("");
    try {
      const provider = await api<{ id: string }>(
        "delivery",
        `organizations/${organizationId}/provider-configurations`,
        {
          method: "POST",
          body: JSON.stringify({
            display_name: "Deterministic local agent",
            provider: "local",
            runtime: "deterministic",
            model: "deterministic-v1",
            authentication_mode: "NONE",
            secret_reference: null,
            is_development_substitute: true,
          }),
        },
      );
      const operationId = crypto.randomUUID();
      window.sessionStorage.setItem("mvp_provider_verifying", provider.id);
      const started = await api<Verification>(
        "delivery",
        `organizations/${organizationId}/provider-configurations/${provider.id}/verifications`,
        {
          method: "POST",
          headers: { "Idempotency-Key": operationId },
          body: JSON.stringify({ runner_pool_id: pools[0].id }),
        },
      );
      setVerification(started);
      await reload();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "No se pudo configurar",
      );
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="shell onboarding-shell">
      <header className="onboarding-header">
        <div>
          <p className="eyebrow">Configuración inicial</p>
          <h1>Prepara tu equipo de entrega</h1>
          <p className="muted">
            Conecta el código y el agente que trabajará sobre él. Tus claves se
            guardan cifradas y nunca vuelven a mostrarse.
          </p>
        </div>
        <div className="onboarding-account">
          <span>{session.email ?? session.subject}</span>
          <form action="/api/auth/logout" method="post">
            <button className="secondary">Salir</button>
          </form>
        </div>
      </header>

      {error ? (
        <div className="card error-panel" role="alert">
          <strong>Necesitamos tu atención</strong>
          <p>{error}</p>
        </div>
      ) : null}

      <nav className="onboarding-progress" aria-label="Progreso">
        <span className={stepClass(true, false)}>1 · Workspace</span>
        <span className={stepClass(githubDone, !githubDone)}>2 · GitHub</span>
        <span className={stepClass(agentDone, githubDone && !agentDone)}>
          3 · Agente IA
        </span>
        <span className={stepClass(agentDone && githubDone, false)}>
          4 · Listo
        </span>
      </nav>

      <section className="card onboarding-card">
        <div className="step-number">01</div>
        <div>
          <p className="eyebrow">Workspace local</p>
          <h2>
            {organizations[0]?.organization.name ?? "Preparando workspace…"}
          </h2>
          <p className="muted">
            El workspace está vacío y aislado. El runner local es un sustituto
            de desarrollo, no infraestructura productiva.
          </p>
          <span className={readyPool ? "status" : "status local"}>
            {readyPool
              ? `Runner disponible · ${readyPool.name}`
              : "Esperando runner"}
          </span>
        </div>
      </section>

      <section className="card onboarding-card">
        <div className="step-number">02</div>
        <div>
          <p className="eyebrow">Código fuente</p>
          <h2>Conecta GitHub</h2>
          {githubDone ? (
            <>
              <span className="status">Conectado</span>
              <div className="repository-list">
                {repositories.map((repository) => (
                  <div key={repository.id}>
                    <strong>
                      {repository.owner}/{repository.name}
                    </strong>
                    {repository.is_development_substitute ? (
                      <span className="status local">Sustituto local</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          ) : sourceConfigurations.length ? (
            sourceConfigurations.map((configuration) => (
              <button
                key={configuration.id}
                disabled={busy === "github"}
                onClick={() => void installGitHub(configuration.id)}
              >
                Conectar {configuration.display_name}
              </button>
            ))
          ) : session.isPlatformOperator ? (
            <>
              <p className="muted">
                Este despliegue aún no tiene una GitHub App. Regístrala una sola
                vez y volverás a este flujo para instalarla en el workspace.
              </p>
              <a className="button" href="/app/admin/integrations/github">
                Registrar GitHub App
              </a>
            </>
          ) : (
            <p className="muted">
              El operador de plataforma debe registrar la GitHub App antes de
              que puedas continuar.
            </p>
          )}
          {!githubDone ? (
            <details className="development-options">
              <summary>Opciones de desarrollo</summary>
              <p className="muted">
                Usa un repositorio simulado únicamente para probar el sistema.
              </p>
              <button
                className="secondary"
                disabled={Boolean(busy)}
                onClick={() => void connectDevelopmentRepository()}
              >
                Conectar repositorio local simulado
              </button>
            </details>
          ) : null}
        </div>
      </section>

      <section className="card onboarding-card">
        <div className="step-number">03</div>
        <div>
          <p className="eyebrow">Agente de código</p>
          <h2>Elige quién implementará los cambios</h2>
          {!githubDone ? (
            <p className="muted">Completa GitHub para habilitar este paso.</p>
          ) : agentDone ? (
            <>
              <span className="status">Conexión verificada</span>
              <p>
                <strong>{verifiedProvider?.display_name}</strong>
              </p>
            </>
          ) : (
            <form className="agent-form" onSubmit={configureAgent}>
              <div className="agent-options">
                {catalog
                  .filter((entry) => entry.tier === "PRIMARY" || showAdvanced)
                  .map((entry) => {
                    const value = `${entry.provider}|${entry.runtime}`;
                    return (
                      <label
                        className={
                          selectedOption === value
                            ? "agent-option selected"
                            : "agent-option"
                        }
                        key={value}
                      >
                        <input
                          checked={selectedOption === value}
                          name="agent"
                          onChange={() => {
                            setSelectedOption(value);
                            setSelectedModel(entry.recommended_model);
                          }}
                          type="radio"
                          value={value}
                        />
                        <span>
                          <strong>{entry.runtime_display_name}</strong>
                          <small>
                            {entry.provider_display_name}
                            {entry.tier === "ADVANCED" ? " · Avanzado" : ""}
                          </small>
                        </span>
                      </label>
                    );
                  })}
              </div>
              <button
                className="secondary compact"
                onClick={() => setShowAdvanced((current) => !current)}
                type="button"
              >
                {showAdvanced ? "Ocultar avanzadas" : "Ver opciones avanzadas"}
              </button>
              <label>
                Modelo revisado
                <select
                  value={selectedModel}
                  onChange={(event) => setSelectedModel(event.target.value)}
                >
                  {selected?.models.map((model) => (
                    <option key={model} value={model}>
                      {model}
                      {model === selected.recommended_model
                        ? " · recomendado"
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                API key de {selected?.provider_display_name}
                <input
                  autoComplete="off"
                  name="api_key"
                  required
                  type="password"
                />
              </label>
              <p className="muted credential-note">
                Se enviará una prueba mínima aislada que puede consumir una
                pequeña cantidad de tokens. La clave es write-only.
              </p>
              <button disabled={!readyPool || busy === "agent"}>
                {busy === "agent"
                  ? "Guardando y verificando…"
                  : "Guardar y verificar conexión"}
              </button>
              {verification ? (
                <div className="verification-state">
                  <span
                    className={
                      verification.status === "FAILED"
                        ? "status local"
                        : "status"
                    }
                  >
                    {verification.status}
                  </span>
                  <p>{verification.result?.summary}</p>
                </div>
              ) : null}
            </form>
          )}
          {githubDone && !agentDone ? (
            <details className="development-options">
              <summary>Opciones de desarrollo</summary>
              <button
                className="secondary"
                disabled={Boolean(busy)}
                onClick={() => void configureDevelopmentAgent()}
              >
                Usar agente determinista sin red
              </button>
            </details>
          ) : null}
        </div>
      </section>

      {githubDone && agentDone ? (
        <section className="onboarding-finish">
          <div>
            <p className="eyebrow">Configuración completa</p>
            <h2>Ya puedes crear tu primer proyecto</h2>
            <p>
              GitHub, el agente y el runner están listos. Cada ejecución seguirá
              requiriendo selección y aprobación explícitas.
            </p>
          </div>
          <a className="button" href="/app">
            Entrar al workspace
          </a>
        </section>
      ) : null}
    </main>
  );
}
