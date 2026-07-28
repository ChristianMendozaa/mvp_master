import { redirect } from "next/navigation";

import { browserSession } from "@/lib/auth";

import { Onboarding } from "./onboarding";

export default async function OnboardingPage(): Promise<React.ReactElement> {
  const session = await browserSession();
  if (!session) redirect("/");
  return <Onboarding session={session} />;
}
