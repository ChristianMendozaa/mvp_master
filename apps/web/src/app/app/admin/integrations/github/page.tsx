import { redirect } from "next/navigation";

import { browserSession } from "@/lib/auth";

import { GitHubSetup } from "./setup";

export default async function GitHubAdmin(): Promise<React.ReactElement> {
  const session = await browserSession();
  if (!session) redirect("/");
  if (!session.isPlatformOperator) redirect("/app");
  return <GitHubSetup />;
}
