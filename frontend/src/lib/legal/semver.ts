/**
 * Semver-based re-consent policy.
 *
 *   PATCH  (x.y.Z) → typo/technical fix → NEVER re-prompt.
 *   MINOR  (x.Y.z) → meaningful update   → re-prompt ONLY if the document is
 *                     flagged `reconsentOnMinor` (the author's call).
 *   MAJOR  (X.y.z) → legal-meaning change → ALWAYS re-prompt.
 *
 * This keeps the re-consent modal from disrupting users for trivial edits while
 * still forcing fresh consent when it legally matters.
 */
export interface Semver {
  major: number;
  minor: number;
  patch: number;
}

export function parseSemver(v?: string | null): Semver | null {
  if (!v) return null;
  const m = /^(\d+)\.(\d+)\.(\d+)/.exec(v.trim());
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]) };
}

/**
 * Whether a user who accepted `accepted` must re-consent to `current`.
 * - no recorded acceptance → true (must consent)
 * - MAJOR increased → true
 * - MINOR increased AND reconsentOnMinor → true
 * - otherwise (PATCH-only, or unflagged MINOR) → false
 */
export function needsReconsent(
  accepted: string | null | undefined,
  current: string,
  reconsentOnMinor = false,
): boolean {
  const c = parseSemver(current);
  if (!c) return false; // no valid current version → nothing to enforce
  const a = parseSemver(accepted);
  if (!a) return true; // never accepted
  if (c.major > a.major) return true;
  if (reconsentOnMinor && c.major === a.major && c.minor > a.minor) return true;
  return false;
}
