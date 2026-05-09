export class ApiError extends Error {
  status: number;
  detail: string;
  code?: string;

  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

type ApiOptions = Omit<RequestInit, "body"> & {
  json?: unknown;
  idempotencyKey?: string;
};

function errorInfo(payload: unknown): { message: string; code?: string } {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return { message: detail };
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message: unknown }).message;
      const code = (detail as { code?: unknown }).code;
      if (typeof message === "string") {
        return { message, code: typeof code === "string" ? code : undefined };
      }
    }
    return { message: JSON.stringify(detail) };
  }
  return { message: "Something went wrong." };
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  let body: BodyInit | undefined;

  if (options.json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(options.json);
  }
  if (options.idempotencyKey) {
    headers.set("idempotency-key", options.idempotencyKey);
  }

  const response = await fetch(`/api/backend${path}`, {
    ...options,
    headers,
    body,
    credentials: "include",
    cache: "no-store"
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const { message, code } = errorInfo(payload);
    throw new ApiError(response.status, message, code);
  }

  return payload as T;
}
