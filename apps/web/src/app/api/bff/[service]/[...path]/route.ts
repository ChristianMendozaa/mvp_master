import { NextRequest, NextResponse } from "next/server";

import { authConfig, validAccessToken } from "@/lib/auth";
import { safeEqual, validateSameOrigin } from "@/lib/security";

const services: Record<string, string | undefined> = {
  control: process.env.CONTROL_PLANE_URL ?? "http://control-plane:8000",
  integrations: process.env.INTEGRATIONS_URL ?? "http://integrations:8000",
  delivery: process.env.DELIVERY_URL ?? "http://delivery:8000",
};

type Context = {
  params: Promise<{ service: string; path: string[] }>;
};

async function proxy(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  const { service, path } = await context.params;
  const baseUrl = services[service];
  if (
    !baseUrl ||
    !path.length ||
    path.some((part) => part === ".." || part.includes("\\"))
  ) {
    return NextResponse.json(
      { error: "unknown service route" },
      { status: 404 },
    );
  }
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  if (unsafe) {
    const csrfHeader = request.headers.get("x-csrf-token");
    const csrfCookie = request.cookies.get("mvp_csrf_token")?.value;
    if (
      !validateSameOrigin(request.headers.get("origin"), authConfig.appUrl) ||
      !csrfHeader ||
      !csrfCookie ||
      !safeEqual(csrfHeader, csrfCookie)
    ) {
      return NextResponse.json(
        { error: "CSRF validation failed" },
        { status: 403 },
      );
    }
  }
  const token = await validAccessToken();
  if (!token.accessToken) {
    return NextResponse.json(
      { error: "authentication required" },
      { status: 401 },
    );
  }
  const target = new URL(
    `/api/v1/${path.map(encodeURIComponent).join("/")}`,
    baseUrl,
  );
  target.search = request.nextUrl.search;
  const headers = new Headers({
    authorization: `Bearer ${token.accessToken}`,
    accept: request.headers.get("accept") ?? "application/json",
    "x-correlation-id":
      request.headers.get("x-correlation-id") ?? crypto.randomUUID(),
  });
  for (const name of ["content-type", "idempotency-key", "last-event-id"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: unsafe ? await request.arrayBuffer() : undefined,
    cache: "no-store",
    redirect: "manual",
  });
  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
  if (token.refreshed) {
    const secure = authConfig.appUrl.startsWith("https://");
    response.cookies.set("mvp_access_token", token.refreshed.accessToken, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      maxAge: token.refreshed.maxAge,
    });
    if (token.refreshed.refreshToken) {
      response.cookies.set("mvp_refresh_token", token.refreshed.refreshToken, {
        httpOnly: true,
        sameSite: "strict",
        secure,
        path: "/",
        maxAge: 28800,
      });
    }
  }
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
