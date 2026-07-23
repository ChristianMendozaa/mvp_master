import { redirect } from "next/navigation";

import { browserSession } from "@/lib/auth";

import { ControlPlane } from "./workspace";

export default async function Product(): Promise<React.ReactElement> {
  const session = await browserSession();
  if (!session) redirect("/");
  return <ControlPlane session={session} />;
}
