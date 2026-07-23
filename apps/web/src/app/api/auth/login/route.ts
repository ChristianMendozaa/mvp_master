import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth";
import { pkceChallenge, randomUrlToken } from "@/lib/security";

export async function GET(): Promise<NextResponse> {
  const state = randomUrlToken();
  const verifier = randomUrlToken(48);
  const csrf = randomUrlToken();
  const authorization = new URL(
    `${authConfig.browserIssuer}/protocol/openid-connect/auth`,
  );
  authorization.search = new URLSearchParams({
    client_id: authConfig.clientId,
    redirect_uri: `${authConfig.appUrl}/api/auth/callback`,
    response_type: "code",
    scope: "openid profile email",
    state,
    code_challenge: pkceChallenge(verifier),
    code_challenge_method: "S256",
  }).toString();
  const response = NextResponse.redirect(authorization);
  const common = {
    sameSite: "lax" as const,
    secure: authConfig.appUrl.startsWith("https://"),
    path: "/",
    maxAge: 600,
  };
  response.cookies.set("mvp_oidc_state", state, { ...common, httpOnly: true });
  response.cookies.set("mvp_oidc_verifier", verifier, {
    ...common,
    httpOnly: true,
  });
  response.cookies.set("mvp_csrf_token", csrf, {
    ...common,
    httpOnly: false,
    maxAge: 86400,
  });
  return response;
}
