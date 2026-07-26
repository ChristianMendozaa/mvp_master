import { redirect } from "next/navigation";

import { browserSession } from "@/lib/auth";

import { GitHubManifestCallback } from "./result";

export default async function GitHubCallback(): Promise<React.ReactElement> {
  const session = await browserSession();
  if (!session) redirect("/");
  if (!session.isPlatformOperator) redirect("/app");
  return <GitHubManifestCallback />;
}
