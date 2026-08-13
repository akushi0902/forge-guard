/**
 * Typed error classes for the ForgeGuard API client.
 */

/**
 * Represents a non-2xx HTTP response from the API.
 * Maps to the backend standard error format: { detail, status_code, error_code }.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly errorCode: string;

  constructor(status: number, detail: string, errorCode: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.errorCode = errorCode;
  }
}

/**
 * Represents a network-level failure (no HTTP response received).
 * Thrown when fetch itself throws (timeout, DNS failure, etc.).
 */
export class NetworkError extends Error {
  override readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'NetworkError';
    this.cause = cause;
  }
}

/**
 * Represents an unexpected response shape (schema mismatch or invalid JSON).
 */
export class ParseError extends Error {
  override readonly cause: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'ParseError';
    this.cause = cause;
  }
}
