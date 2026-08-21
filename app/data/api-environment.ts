/** Return the canonical public API origin configured for nAIM. */
export function publicApiUrl(): string | undefined {
  return process.env.NEXT_PUBLIC_NAIM_API_URL;
}
