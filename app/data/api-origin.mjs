/**
 * Normalise the optional frontend API setting to an origin.
 *
 * @param {string | undefined} value
 * @returns {string}
 */
export function normalizeApiOrigin(value) {
  const trimmed = (value ?? "").trim().replace(/\/+$/, "");
  return trimmed.replace(/\/api\/v1$/i, "");
}
