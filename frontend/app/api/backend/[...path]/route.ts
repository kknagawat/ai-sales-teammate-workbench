import { NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000";

type RouteContext = {
  params: {
    path: string[];
  };
};

function forwardedHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const cookie = request.headers.get("cookie");
  const idempotencyKey = request.headers.get("idempotency-key");
  const userAgent = request.headers.get("user-agent");
  const fetchSite = request.headers.get("sec-fetch-site");
  const origin =
    request.headers.get("origin") ?? (fetchSite === "same-origin" ? request.nextUrl.origin : null);
  const forwardedFor = request.headers.get("x-forwarded-for");
  const realIp = request.headers.get("x-real-ip");

  if (contentType) headers.set("content-type", contentType);
  if (cookie) headers.set("cookie", cookie);
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
  if (userAgent) headers.set("user-agent", userAgent);
  if (origin) headers.set("origin", origin);
  if (forwardedFor) {
    headers.set("x-forwarded-for", forwardedFor);
  } else if (realIp) {
    headers.set("x-forwarded-for", realIp);
  }
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  headers.set("x-forwarded-host", request.headers.get("host") ?? "localhost");
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  return headers;
}

function appendSetCookie(source: Response, target: NextResponse) {
  const getSetCookie = (source.headers as Headers & { getSetCookie?: () => string[] })
    .getSetCookie;
  const cookies = getSetCookie ? getSetCookie.call(source.headers) : [];
  const fallbackCookie = source.headers.get("set-cookie");

  if (cookies.length) {
    for (const cookie of cookies) target.headers.append("set-cookie", cookie);
  } else if (fallbackCookie) {
    target.headers.set("set-cookie", fallbackCookie);
  }
}

async function proxy(request: NextRequest, context: RouteContext) {
  const path = context.params.path.join("/");
  const targetUrl = `${BACKEND_API_URL.replace(/\/$/, "")}/${path}${request.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(request.method);
  const backendResponse = await fetch(targetUrl, {
    method: request.method,
    headers: forwardedHeaders(request),
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
    redirect: "manual"
  });

  const body = backendResponse.status === 204 ? null : await backendResponse.arrayBuffer();
  const response = new NextResponse(body, { status: backendResponse.status });
  const responseType = backendResponse.headers.get("content-type");
  if (responseType) response.headers.set("content-type", responseType);
  appendSetCookie(backendResponse, response);
  return response;
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
