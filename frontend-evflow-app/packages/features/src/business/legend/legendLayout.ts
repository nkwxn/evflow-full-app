/**
 * Whether the map key has to fold away, and how much room it may take.
 *
 * On a wide screen the legends sit in the empty corner of a map that is still
 * mostly visible, so they simply stay open. On a phone they do not: each one is
 * a title, four or five colour rows and a footnote, and two of them stacked
 * cover the map they are supposed to explain. Measured on a 390pt viewport, land
 * use plus demand fills 60% of the height and the user is reading a key to a map
 * they can no longer see.
 *
 * So the rule is not "hide the legends on mobile". The footnotes are the part
 * that matters most -- "unshaded ground is unmapped, not empty" is a fact a
 * planner would otherwise get wrong -- and dropping them to save space would
 * trade the map for the map's meaning. They fold behind one tap instead, and
 * open over a capped, scrollable area.
 */

/** Matches the panel-docking breakpoint, so one screen never mixes the two modes. */
export const LEGEND_BREAKPOINT = 768;

/** Share of viewport height the open key may occupy on a phone. */
export const LEGEND_MAX_HEIGHT_FRACTION = 0.45;

/** Widest a legend card may be on a phone, in points. */
export const LEGEND_MAX_WIDTH = 260;

export function shouldCollapseLegends(width: number, activeLegends: number): boolean {
  if (width >= LEGEND_BREAKPOINT) return false;
  return activeLegends > 0;
}

/**
 * Pixels the open key may use, never more than the fraction above.
 *
 * Taken from the viewport rather than a constant because a phone in landscape
 * and a phone upright differ by more than any fixed number would survive.
 */
export function legendMaxHeight(viewportHeight: number): number {
  return Math.round(viewportHeight * LEGEND_MAX_HEIGHT_FRACTION);
}

/** What the closed pill says, so it names what is on rather than just "Key". */
export function legendPillLabel(activeLegends: number): string {
  if (activeLegends <= 0) return 'Map key';
  return activeLegends === 1 ? '1 layer key' : `${activeLegends} layer keys`;
}
