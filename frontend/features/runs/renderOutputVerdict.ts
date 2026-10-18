/**
 * Mirrors web_api/routers/render.py's render_output_verdict(). A render
 * run is SUCCEEDED whenever the request completed - including when ffmpeg
 * exited non-zero or the file failed postflight validation, which are
 * recorded as data in the run's result rather than as a FAILED run. The
 * run status alone therefore can't say whether a usable video exists
 * (issue #2); this reads the verdict the Execution Engine already computed.
 *
 * Returns null when the result isn't a render result, or is a dry run.
 */
export type RenderOutputVerdict = { ok: true } | { ok: false; reason: string };

export function renderOutputVerdict(result: Record<string, unknown> | null): RenderOutputVerdict | null {
  const render = result?.render;
  if (!render || typeof render !== "object") return null;
  const r = render as Record<string, unknown>;
  if (r.dry_run === true) return null;
  if (r.success !== true) {
    return { ok: false, reason: typeof r.error === "string" && r.error ? r.error : "Render failed" };
  }

  const validation = result?.validation;
  if (validation && typeof validation === "object") {
    const v = validation as Record<string, unknown>;
    if (v.is_valid === false) {
      const checks = Array.isArray(v.checks) ? (v.checks as Record<string, unknown>[]) : [];
      const failed = checks.filter((c) => c.passed === false).map((c) => String(c.name ?? "?"));
      return {
        ok: false,
        reason: `Rendered video failed postflight validation: ${failed.length ? failed.join(", ") : "unspecified check"}`,
      };
    }
  }
  return { ok: true };
}
