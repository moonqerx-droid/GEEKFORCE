export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Thrown on HTTP 409 — the resource changed since expected_revision was read. */
export class ConflictError extends ApiError {
  constructor(detail?: unknown) {
    super(409, "conflict", detail);
    this.name = "ConflictError";
  }
}

/** Thrown on HTTP 422 — payload failed backend validation. */
export class ValidationError extends ApiError {
  constructor(detail?: unknown) {
    super(422, "validation_error", detail);
    this.name = "ValidationError";
  }
}

export class NotFoundError extends ApiError {
  constructor(detail?: unknown) {
    super(404, "not_found", detail);
    this.name = "NotFoundError";
  }
}

/** Network failure, timeout, or abort — the request never got a response. */
export class NetworkError extends Error {
  cause?: unknown;

  constructor(message = "network_error", cause?: unknown) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
  }
}
