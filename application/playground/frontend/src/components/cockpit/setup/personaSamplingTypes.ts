/** Persona sampling state shared by the cockpit left rail. */

import type { TaskPersonaStrategy } from "@/lib/types";

export type PersonaSamplingMode = "single" | "random" | "stratified" | "all";

export type StratifiedAllocation = "perCell" | "proportional" | "equalTotal";

export interface PersonaDimensionFilters {
  sources: string[];
  /** dimension id → selected values (multi-select per dimension). */
  dimensionFilters: Record<string, string[]>;
}

export function emptyPersonaDimensionFilters(): PersonaDimensionFilters {
  return { sources: [], dimensionFilters: {} };
}

export function activeFilterCount(filters: PersonaDimensionFilters): number {
  const dimCount = Object.values(filters.dimensionFilters).filter((values) => values.length > 0).length;
  return filters.sources.length + dimCount;
}

export function filtersForSampleApi(
  filters: PersonaDimensionFilters,
): Record<string, string | string[]> | undefined {
  const entries = Object.entries(filters.dimensionFilters).filter(([, values]) => values.length > 0);
  if (entries.length === 0) return undefined;
  return Object.fromEntries(entries.map(([key, values]) => [key, values.length === 1 ? values[0] : values]));
}

export interface StrategySamplingView {
  mode: PersonaSamplingMode;
  fields: string[];
  allocation: StratifiedAllocation;
  sampleSize: number | null;
  perCell: number | null;
}

function asSamplingMode(value: string | null | undefined): PersonaSamplingMode {
  if (value === "random" || value === "stratified" || value === "all" || value === "single") {
    return value;
  }
  return "single";
}

function asAllocation(
  value: string | null | undefined,
  fallback: StratifiedAllocation,
): StratifiedAllocation {
  if (value === "perCell" || value === "proportional" || value === "equalTotal") {
    return value;
  }
  return fallback;
}

/** Read the unified ``strategy.sampling`` block (required on valid strategies). */
export function readStrategySampling(
  strategy: TaskPersonaStrategy | null | undefined,
): StrategySamplingView {
  const sampling = strategy?.sampling;
  if (!sampling || typeof sampling !== "object") {
    return {
      mode: "single",
      fields: [],
      allocation: "perCell",
      sampleSize: null,
      perCell: null,
    };
  }
  const mode = asSamplingMode(sampling.mode);
  const fields = Array.isArray(sampling.fields)
    ? sampling.fields.filter(
        (field): field is string => typeof field === "string" && Boolean(field.trim()),
      )
    : [];
  const sampleSize =
    typeof sampling.sampleSize === "number" && sampling.sampleSize > 0
      ? Math.round(sampling.sampleSize)
      : null;
  const perCell =
    typeof sampling.perCell === "number" && sampling.perCell >= 1
      ? Math.round(sampling.perCell)
      : null;
  const allocationFallback: StratifiedAllocation =
    perCell != null ? "perCell" : sampleSize != null ? "equalTotal" : "perCell";
  return {
    mode,
    fields,
    allocation: asAllocation(sampling.allocation, allocationFallback),
    sampleSize,
    perCell,
  };
}
