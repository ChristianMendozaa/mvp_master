import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth";
import { validateSameOrigin } from "@/lib/security";

export async function POST(request: Request): Promise<NextResponse> {
  if (!validateSameOrigin(request.headers.get("origin"), authConfig.appUrl)) {
    return NextResponse.json(
      { error: "invalid request origin" },
      { status: 403 },
    );
  }
  const response = NextResponse.redirect(authConfig.appUrl, { status: 303 });
  for (const name of [
    "mvp_access_token",
    "mvp_refresh_token",
    "mvp_csrf_token",
  ]) {
    response.cookies.delete(name);
  }
  return response;
}
