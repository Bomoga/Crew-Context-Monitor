import type { Level } from "../api/types.gen";
import { LEVEL_CLASSES, LEVEL_WORD } from "../lib/levels";

/**
 * A level as color plus word. Size and layout are identical for every level (D14): the badge has
 * a fixed minimum width, so a change of level never moves anything.
 */
export function LevelBadge({ level, className = "" }: { level: Level; className?: string }) {
  const c = LEVEL_CLASSES[level];
  return (
    <span
      data-level={level}
      className={`inline-flex min-w-[6.5rem] items-center justify-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${c.bg} ${c.text} ${className}`}
    >
      <span aria-hidden="true" className={`inline-block h-2.5 w-2.5 rounded-full ${c.mark}`} />
      {LEVEL_WORD[level]}
    </span>
  );
}
