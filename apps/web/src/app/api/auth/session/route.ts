import { NextResponse } from "next/server";

import { browserSession } from "@/lib/auth";

export async function GET(): Promise<NextResponse> {
  const session = await browserSession();
  return NextResponse.json({ authenticated: Boolean(session), session });
}
