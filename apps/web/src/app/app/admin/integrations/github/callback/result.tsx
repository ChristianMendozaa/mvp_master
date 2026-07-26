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

export function GitHubManifestCallback(): React.ReactElement {
  const search = useSearchParams();
  const submitted = useRef(false);
  const [status, setStatus] = useState("Completing GitHub App registration…");

  useEffect(() => {
    if (submitted.current) return;
    submitted.current = true;
    const code = search.get("code");
    const state = search.get("state");
    if (!code || !state) {
      const timer = window.setTimeout(
        () =>
          setStatus("GitHub did not return a valid manifest code and state."),
        0,
      );
      return () => window.clearTimeout(timer);
    }
    void fetch(
      "/api/bff/integrations/platform/source-control-configurations/github/manifest/complete",
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken(),
        },
        body: JSON.stringify({
          code,
          state,
          display_name:
            sessionStorage.getItem("mvp_github_display_name") ??
            "MVP Master GitHub",
          webhook_mode:
            sessionStorage.getItem("mvp_github_webhook_mode") ?? "POLLING",
        }),
      },
    ).then(async (response) => {
      setStatus(
        response.ok
          ? "GitHub App configured. You may return to the control plane."
          : `Configuration failed: ${await response.text()}`,
      );
    });
    return undefined;
  }, [search]);

  return (
    <main className="shell">
      <h1>GitHub App setup</h1>
      <p>{status}</p>
      <a className="button" href="/app/admin/integrations/github">
        Back to GitHub settings
      </a>
    </main>
  );
}
