/** Client-side credential sanitizer — defense-in-depth before displaying agent responses. */

const REDACTED = '[REDACTED]';

const PATTERNS: RegExp[] = [
  // Bearer / Authorization header values
  /Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi,
  // OpenAI / Stripe / generic sk-/pk- prefixed API keys
  /\b(?:sk|pk|rk|ak|ek)-[A-Za-z0-9]{16,}/g,
  // AWS access key IDs
  /\b(?:AKIA|ASIA|AROA|AIDA|ANPA|ANVA|APKA)[A-Z0-9]{16}\b/g,
  // Generic "password=" or "secret=" style values in query strings / logs
  /(?:password|passwd|secret|token|apikey|api_key|access_token|auth_token)\s*[:=]\s*["']?[^\s"',;)>]{6,}["']?/gi,
  // Connection strings (mongodb://, postgres://, mysql://, etc.)
  /(?:mongodb|postgresql|postgres|mysql|mssql|redis|amqp):\/\/[^\s"'<>]+/gi,
  // Basic auth credentials embedded in URLs: http://user:pass@host
  /https?:\/\/[^@\s]+:[^@\s]+@/gi,
];

/**
 * Replaces known credential patterns in `text` with "[REDACTED]".
 * Pure function — does not modify its argument.
 */
export function sanitizeCredentials(text: string): string {
  return PATTERNS.reduce((acc, re) => acc.replace(re, REDACTED), text);
}
