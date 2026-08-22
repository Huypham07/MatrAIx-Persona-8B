import { SOURCE_LOCALE, SOURCE_MESSAGES } from "./source";
import type { MessageCatalog, TextDirection } from "./types";

export interface LocaleDefinition<Code extends string = string> {
  code: Code;
  /** Native-script label shown in the locale popover. */
  nativeName: string;
  englishName: string;
  translationStatus?: "source" | "machine-assisted" | "human-reviewed";
  dir: TextDirection;
  fallback: Code | null;
  load: () => Promise<MessageCatalog>;
}

export const LOCALE_REGISTRY = [
  {
    code: SOURCE_LOCALE,
    nativeName: "English",
    englishName: "English",
    translationStatus: "source",
    dir: "ltr",
    fallback: null,
    load: async () => SOURCE_MESSAGES,
  },
  {
    code: "zh-Hans",
    nativeName: "简体中文",
    englishName: "Simplified Chinese",
    translationStatus: "machine-assisted",
    dir: "ltr",
    fallback: SOURCE_LOCALE,
    load: async () => (await import("./messages/zh-Hans.json")).default,
  },
] as const satisfies readonly LocaleDefinition[];

/** Adding a registry entry extends the UI-locale union automatically. */
export type UiLocale = (typeof LOCALE_REGISTRY)[number]["code"];

export function isUiLocale(value: unknown): value is UiLocale {
  return typeof value === "string" && LOCALE_REGISTRY.some((entry) => entry.code === value);
}


/**
 * Alternate tags → canonical `UiLocale` codes in `LOCALE_REGISTRY`.
 *
 * Aliases never appear in the locale popover. Use this for:
 * - legacy region tags (`zh-CN` / `zh-TW`) → script tags (`zh-Hans` / `zh-Hant`)
 * - common short forms once a pack ships (e.g. `pt` → `pt-BR`, `zh` → `zh-Hans`)
 *
 * Resolution only succeeds when the *target* is already registered — so this
 * full table can ship before every target locale exists.
 */
export const LOCALE_ALIASES: Readonly<Record<string, string>> = {
  "zh-CN": "zh-Hans",
  "zh-TW": "zh-Hant",
};

export function resolveUiLocale(value: unknown): UiLocale | null {
  if (typeof value !== "string") return null;
  if (isUiLocale(value)) return value;
  const canonical = LOCALE_ALIASES[value];
  if (canonical && isUiLocale(canonical)) return canonical;
  return null;
}


export function getLocaleDefinition(locale: UiLocale): LocaleDefinition<UiLocale> {
  const definition = LOCALE_REGISTRY.find((candidate) => candidate.code === locale);
  if (!definition) throw new Error(`Locale is not registered: ${locale}`);
  return definition;
}
