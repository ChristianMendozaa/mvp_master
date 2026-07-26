import { redirect } from "next/navigation";

import { browserSession } from "@/lib/auth";

import { GitHubInstallationCallback } from "./result";

export default async function GitHubInstallation(): Promise<React.ReactElement> {
  const session = await browserSession();
  if (!session) redirect("/");
  return <GitHubInstallationCallback />;
}
