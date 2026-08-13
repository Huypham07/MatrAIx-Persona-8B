import type { PersonaPoolCatalog } from "./types";

export function poolSlugLabel(poolPath: string): string {
  const slug = poolPath.split("/").filter(Boolean).pop() ?? poolPath;
  return slug.replace(/-/g, " ");
}

export function personaPoolEmptyMessage(
  catalog: PersonaPoolCatalog | null | undefined,
): string {
  const pool = catalog?.pool ? poolSlugLabel(catalog.pool) : "persona pool";
  return `${pool} is empty or could not be loaded.`;
}

/** Backend / sampling errors that mean the fixture pool is too thin for filters. */
export function isPersonaPoolCoverageError(message: string | null | undefined): boolean {
  const text = message ?? "";
  return (
    text.includes("exceeds matched pool size") ||
    text.includes("No personas with stratify fields") ||
    text.includes("sample_size_per_value_group=") ||
    text.includes("Incomplete stratify coverage") ||
    text.includes("matraix-persona-1m") ||
    text.includes("matraix-persona-dev-sample")
  );
}

export function personaPoolCoverageHint(taskPath?: string | null): string {
  const synthesize = taskPath
    ? " With Task default persona strategy on, you can also Synthesize to fill this task."
    : "";
  return (
    "Not enough matching personas in this dataset for the current filters. " +
    "Consider switching Dataset to matraix-persona-1m for fuller coverage." +
    synthesize +
    " Or widen filters / sources, or use a saved cohort that already has enough matches."
  );
}

/** Prefer the API message; fall back to a production-pool recovery hint. */
export function formatPersonaSampleError(
  message: string,
  taskPath?: string | null,
): string {
  const trimmed = message.trim();
  if (isPersonaPoolCoverageError(trimmed)) {
    const first = trimmed.split("\n").find((line) => line.trim()) || trimmed;
    const alreadyHinted =
      trimmed.includes("matraix-persona-1m") ||
      trimmed.includes("Synthesize to fill") ||
      trimmed.includes("does not synthesize");
    return alreadyHinted ? trimmed : `${first}\n\n${personaPoolCoverageHint(taskPath)}`;
  }
  return trimmed;
}
