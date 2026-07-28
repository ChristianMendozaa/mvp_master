"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

function csrfToken(): string {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("mvp_csrf_token="))
      ?.split("=")[1] ?? ""
  );
}

export function GitHubInstallationCallback(): React.ReactElement {
  const search = useSearchParams();
  const submitted = useRef(false);
  const [status, setStatus] = useState("Verifying GitHub installation…");

  useEffect(() => {
    if (submitted.current) return;
    submitted.current = true;
    const organizationId = sessionStorage.getItem("mvp_github_organization_id");
    const code = search.get("code");
    const state = search.get("state");
    const installationId = search.get("installation_id");
    if (!organizationId || !code || !state || !installationId) {
      const timer = window.setTimeout(
        () => setStatus("The GitHub installation callback is incomplete."),
        0,
      );
      return () => window.clearTimeout(timer);
    }
    void fetch(
      `/api/bff/integrations/organizations/${encodeURIComponent(organizationId)}/github/installations/complete`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken(),
        },
        body: JSON.stringify({
          code,
          state,
          installation_id: installationId,
        }),
      },
    ).then(async (response) => {
      if (response.ok) {
        sessionStorage.removeItem("mvp_github_organization_id");
        setStatus("GitHub repository access connected.");
      } else {
        setStatus(`Connection failed: ${await response.text()}`);
      }
    });
    return undefined;
  }, [search]);

  return (
    <main className="shell">
      <h1>GitHub installation</h1>
      <p>{status}</p>
      <a className="button" href="/app/onboarding">
        Return to onboarding
      </a>
    </main>
  );
}
