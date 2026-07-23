import { NextRequest, NextResponse } from "next/server";

import { authConfig, tokenResponseSchema } from "@/lib/auth";
import { safeEqual } from "@/lib/security";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const state = request.nextUrl.searchParams.get("state");
  const code = request.nextUrl.searchParams.get("code");
  const expectedState = request.cookies.get("mvp_oidc_state")?.value;
  const verifier = request.cookies.get("mvp_oidc_verifier")?.value;
  if (
    !state ||
    !code ||
    !expectedState ||
    !verifier ||
    !safeEqual(state, expectedState)
  ) {
    return NextResponse.json(
      { error: "OIDC callback state is invalid" },
      { status: 400 },
    );
  }
  const tokenResponse = await fetch(
    `${authConfig.internalIssuer}/protocol/openid-connect/token`,
    {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: authConfig.clientId,
        redirect_uri: `${authConfig.appUrl}/api/auth/callback`,
        code,
        code_verifier: verifier,
      }),
      cache: "no-store",
    },
  );
  if (!tokenResponse.ok) {
    return NextResponse.json(
      { error: "OIDC token exchange failed" },
      { status: 502 },
    );
  }
  const tokens = tokenResponseSchema.parse(await tokenResponse.json());
  const response = NextResponse.redirect(`${authConfig.appUrl}/app`);
  const secure = authConfig.appUrl.startsWith("https://");
  response.cookies.set("mvp_access_token", tokens.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: tokens.expires_in,
  });
  if (tokens.refresh_token) {
    response.cookies.set("mvp_refresh_token", tokens.refresh_token, {
      httpOnly: true,
      sameSite: "strict",
      secure,
      path: "/",
      maxAge: 28800,
    });
  }
  response.cookies.delete("mvp_oidc_state");
  response.cookies.delete("mvp_oidc_verifier");
  return response;
}
