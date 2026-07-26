import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const baseUrl = process.env.INTEGRATIONS_URL ?? "http://integrations:8000";
  const headers = new Headers();
  for (const name of [
    "content-type",
    "content-length",
    "x-github-delivery",
    "x-github-event",
    "x-hub-signature-256",
    "x-github-hook-installation-target-id",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const upstream = await fetch(`${baseUrl}/webhooks/github`, {
    method: "POST",
    headers,
    body: await request.arrayBuffer(),
    cache: "no-store",
  });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
