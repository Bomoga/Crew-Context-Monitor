import type { Domain, Level } from "../api/types.gen";

export const LEVELS: readonly Level[] = ["green", "yellow", "red"];

/** Each level shows its word beside the color (D14). */
export const LEVEL_WORD: Record<Level, string> = {
  green: "Green",
  yellow: "Yellow",
  red: "Red",
};

export const LEVEL_RANK: Record<Level, number> = { green: 0, yellow: 1, red: 2 };

/** Class names for text, background and mark color of a level (Tailwind tokens in index.css). */
export const LEVEL_CLASSES: Record<Level, { text: string; bg: string; mark: string }> = {
  green: { text: "text-level-green", bg: "bg-level-green-bg", mark: "bg-level-green-mark" },
  yellow: { text: "text-level-yellow", bg: "bg-level-yellow-bg", mark: "bg-level-yellow-mark" },
  red: { text: "text-level-red", bg: "bg-level-red-bg", mark: "bg-level-red-mark" },
};

/** Fixed card order and names. Radiation is always a proxy. */
export const DOMAINS: readonly Domain[] = ["cardio", "air", "thermal", "radiation"];

export const DOMAIN_NAME: Record<Domain, string> = {
  cardio: "Cardiovascular",
  air: "Air quality",
  thermal: "Thermal",
  radiation: "Radiation (proxy)",
};

export function isDomain(value: string | undefined): value is Domain {
  return DOMAINS.includes(value as Domain);
}
