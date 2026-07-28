"use client";

import { FormEvent, useEffect, useState } from "react";

type Configuration = {
  id: string;
  display_name: string;
  app_slug: string;
  webhook_mode: string;
  health: string;
};

type ManifestStart = {
  registration_url: string;
  state: string;
  manifest: Record<string, unknown>;
};

function csrfToken(): string {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("mvp_csrf_token="))
      ?.split("=")[1] ?? ""
  );
}

async function integrations<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/bff/integrations/${path}`, {
    ...options,
    headers: {
      "content-type": "application/json",
      "x-csrf-token": csrfToken(),
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export function GitHubSetup(): React.ReactElement {
  const [configurations, setConfigurations] = useState<Configuration[]>([]);
  const [registration, setRegistration] = useState<ManifestStart | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void integrations<Configuration[]>("platform/source-control-configurations")
      .then(setConfigurations)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "Load failed"),
      );
  }, []);

  async function prepare(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError("");
    const values = new FormData(event.currentTarget);
    const displayName = String(values.get("display_name") ?? "");
    const webhookMode = String(values.get("webhook_mode") ?? "POLLING");
    try {
      sessionStorage.setItem("mvp_github_display_name", displayName);
      sessionStorage.setItem("mvp_github_webhook_mode", webhookMode);
      setRegistration(
        await integrations<ManifestStart>(
          "platform/source-control-configurations/github/manifest",
          {
            method: "POST",
            body: JSON.stringify({
              display_name: displayName,
              owner: values.get("owner") || null,
              webhook_mode: webhookMode,
            }),
          },
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Setup failed");
    }
  }

  return (
    <main className="shell">
      <p className="eyebrow">Platform operation</p>
      <h1>GitHub App</h1>
      <p className="muted">
        Register one GitHub App owned by this deployment. Secret values return
        directly to the integrations service and are encrypted before storage.
      </p>
      <p>
        <a href="/app/onboarding">← Return to onboarding</a>
      </p>
      {error ? <div role="alert">{error}</div> : null}
      {configurations.map((item) => (
        <section className="card" key={item.id}>
          <strong>{item.display_name}</strong>
          <p>
            {item.app_slug} · {item.webhook_mode} · {item.health}
          </p>
        </section>
      ))}
      <section className="card">
        <form onSubmit={(event) => void prepare(event)}>
          <label>
            Display name
            <input
              name="display_name"
              defaultValue="MVP Master GitHub"
              required
            />
          </label>
          <label>
            GitHub owner (optional organization)
            <input name="owner" pattern="[A-Za-z0-9-]{1,39}" />
          </label>
          <label>
            Synchronization
            <select name="webhook_mode" defaultValue="POLLING">
              <option value="POLLING">
                Polling for private/local deployments
              </option>
              <option value="WEBHOOK">Public HTTPS webhook</option>
            </select>
          </label>
          <button type="submit">Prepare GitHub registration</button>
        </form>
        {registration ? (
          <form action={registration.registration_url} method="post">
            <input
              type="hidden"
              name="manifest"
              value={JSON.stringify(registration.manifest)}
            />
            <button type="submit">Continue on GitHub</button>
          </form>
        ) : null}
      </section>
    </main>
  );
}
