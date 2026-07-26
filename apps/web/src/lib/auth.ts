import { cookies } from "next/headers";
import { z } from "zod";

const tokenResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string().optional(),
  expires_in: z.number().positive(),
});

export const authConfig = {
  clientId: process.env.OIDC_CLIENT_ID ?? "mvp-web",
  browserIssuer:
    process.env.OIDC_BROWSER_ISSUER ??
    "http://localhost:8081/realms/mvp-master",
  internalIssuer:
    process.env.OIDC_INTERNAL_ISSUER ??
    "http://keycloak:8080/realms/mvp-master",
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
};

export type BrowserSession = {
  subject: string;
  email?: string;
  name?: string;
  expiresAt: number;
  isPlatformOperator: boolean;
};

export function decodeAccessToken(token: string): BrowserSession | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const claims = z
      .object({
        sub: z.string(),
        email: z.string().optional(),
        name: z.string().optional(),
        exp: z.number(),
        mvp_master_platform_operator: z.boolean().optional(),
      })
      .parse(JSON.parse(Buffer.from(part, "base64url").toString("utf8")));
    return {
      subject: claims.sub,
      email: claims.email,
      name: claims.name,
      expiresAt: claims.exp,
      isPlatformOperator: claims.mvp_master_platform_operator === true,
    };
  } catch {
    return null;
  }
}

export async function browserSession(): Promise<BrowserSession | null> {
  const store = await cookies();
  const accessToken = store.get("mvp_access_token")?.value;
  return accessToken ? decodeAccessToken(accessToken) : null;
}

export async function validAccessToken(): Promise<{
  accessToken: string | null;
  refreshed?: {
    accessToken: string;
    refreshToken?: string;
    maxAge: number;
  };
}> {
  const store = await cookies();
  const accessToken = store.get("mvp_access_token")?.value;
  const session = accessToken ? decodeAccessToken(accessToken) : null;
  if (accessToken && session && session.expiresAt > Date.now() / 1000 + 30) {
    return { accessToken };
  }
  const refreshToken = store.get("mvp_refresh_token")?.value;
  if (!refreshToken) return { accessToken: null };
  const response = await fetch(
    `${authConfig.internalIssuer}/protocol/openid-connect/token`,
    {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        client_id: authConfig.clientId,
        refresh_token: refreshToken,
      }),
      cache: "no-store",
    },
  );
  if (!response.ok) return { accessToken: null };
  const tokens = tokenResponseSchema.parse(await response.json());
  return {
    accessToken: tokens.access_token,
    refreshed: {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      maxAge: tokens.expires_in,
    },
  };
}

export { tokenResponseSchema };
