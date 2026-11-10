export class HttpError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HttpError";
    this.status = status;
  }
}

/** JSON transport for backend services. Non-success responses reject the request. */
export async function postJson<TResponse>(
  url: string,
  body: unknown,
  options: { signal?: AbortSignal } = {},
): Promise<TResponse> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new HttpError(response.status, `Request failed (${response.status}).`);
  }

  return response.json() as Promise<TResponse>;
}
