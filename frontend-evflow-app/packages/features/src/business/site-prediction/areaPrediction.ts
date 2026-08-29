import type { PlannerAreaDistributionApi } from '@evflow/shared';

/**
 * Presentation logic for on-demand model predictions around a chosen point.
 *
 * Kept out of the map screen because the screen is already at the size this
 * codebase caps files at, and everything here is pure enough to test without
 * mounting a map.
 *
 * TWO THINGS THIS MODULE EXISTS TO ENFORCE
 *
 * 1. An area is described by the DISTRIBUTION of its cells, never one number.
 *    The model was fitted on 500 m cells; summing a 10 x 10 km selection into
 *    one feature vector puts 18 of its 33 additive features past anything in
 *    the training set, where a random forest can only repeat its most extreme
 *    leaves. It answered 0.605 where the true per-cell mean was 0.040.
 *
 * 2. Cells that already have a station are never presented as candidates.
 *    Measured across all 27,219 cells, the model's 500 highest-probability
 *    cells are 100% already built on. On real areas around Sudirman, Cibubur
 *    and Serpong, the three top-scoring cells all had a station.
 */

/**
 * Cells scored per request.
 *
 * A 3 km circle is about 140 cells and a 25 km one about 9,800, so this clears
 * the largest circle the API allows. It stays well under the 30,000 ceiling
 * because an aborted request still runs to completion on the server: the engine
 * pools 15 connections, and a fast sequence of requests at 30,000 once locked
 * the whole API, /health included, for over 30 seconds.
 */
export const SCORE_LIMIT = 10_000;

/** Cells drawn on the map. Must stay inside the API's `top` ceiling of 10,000. */
export const DRAW_LIMIT = 6_000;

/** Radii offered in the UI, in km. Small enough to describe one place. */
export const RADIUS_CHOICES = [1, 3, 5] as const;

/**
 * Fallback denominator for the colour scale when the API cannot supply one.
 *
 * NOT the regional ceiling any more: that now arrives per response as
 * distribution.resemblance_ceiling, computed from the loaded model. This is only
 * a floor on the divisor so a circle whose cells all score near zero does not
 * divide by something tiny and paint every one of them at full strength.
 */
const MIN_SCALE_DIVISOR = 0.05;

/** Slate, for cells that already have a station. Deliberately outside the scale. */
export const BUILT_COLOUR = '#64748B';

/**
 * Colour for a cell with no station, on its own observed range.
 *
 * Not the red/amber/green of the demand heatmap. That palette reads as
 * "priority", and these numbers are not a priority ranking: 0.26 is the best
 * empty cell anywhere near Sudirman, and calling it red would state a
 * recommendation the model cannot make.
 */
/**
 * The bands, in one place, because the legend renders from this array and the
 * fill is chosen from it.
 *
 * They were separate: three hex values in a colour function and three more in
 * whatever explained them. A legend that drifts from the shading it describes is
 * worse than no legend, because it is believed.
 *
 * Thresholds are fractions of the REGIONAL CEILING, not of 1.0. The best unbuilt
 * cell in Jabodetabek reaches about 0.31, so a scale anchored at 1.0 would paint
 * the entire grid pale and say nothing. `label` is written as a share of that
 * best for the same reason the card says "69% of the highest any unbuilt cell
 * reaches": 0.21 reads as poor against 1.0 and as near the top against 0.31.
 */
export const RESEMBLANCE_BANDS = [
  { colour: '#7C3AED', floor: 0.66, label: '66-100% of the regional best' },
  { colour: '#A78BFA', floor: 0.33, label: '33-66%' },
  { colour: '#DDD6FE', floor: 0, label: 'under 33%' }
] as const;

export function resemblanceBand(probability: number, ceiling: number | null) {
  if (ceiling === null || !Number.isFinite(probability) || !Number.isFinite(ceiling) || ceiling <= 0) {
    return null;
  }
  const share = Math.min(Math.max(probability, 0), ceiling) / ceiling;
  return RESEMBLANCE_BANDS.find((band) => share >= band.floor)
    ?? RESEMBLANCE_BANDS[RESEMBLANCE_BANDS.length - 1];
}

export function resemblanceColour(probability: number, ceiling: number | null): string {
  const top = Math.max(ceiling ?? 0, MIN_SCALE_DIVISOR);
  return resemblanceBand(probability, top)?.colour
    ?? RESEMBLANCE_BANDS[RESEMBLANCE_BANDS.length - 1].colour;
}

/**
 * The suitability bands, red to green.
 *
 * SEPARATE FROM RESEMBLANCE ON PURPOSE
 *
 * RESEMBLANCE_BANDS above is purple and answers "does this look like a place
 * someone already built a station". These answer "should someone build here",
 * which is a different question with a different scale, and the two were merged
 * once by accident: the map said "high demand" where the model meant
 * "resembles an existing site". Keeping two palettes is what makes the mistake
 * visible if it happens again.
 *
 * NO FLOORS ARE WRITTEN DOWN HERE
 *
 * The floors arrive per response, computed from the loaded model over the whole
 * region. Hardcoding 0.9 and 0.5 would band cells against a distribution that
 * stops existing the moment the model is retrained or stations are imported.
 *
 * LABELS SAY WHERE, NOT HOW MUCH
 *
 * These are quantile bands. "Top 10% of Jabodetabek" is what a quantile
 * supports; "high demand" is not, and would also collide head-on with the Live
 * Traffic layer on the same screen, where red means congested and bad.
 */
export const SUITABILITY_BANDS = [
  { key: 'red', colour: '#DC2626', label: 'Best 10% in Jabodetabek' },
  { key: 'yellow', colour: '#F59E0B', label: 'Better than average' },
  { key: 'green', colour: '#10B981', label: 'Below average, or already well covered' }
] as const;

/** Grey is a colour on the map, so it belongs in the key beside the bands. */
export const BUILT_LABEL = 'Already has a charger';

/** The floors a band was cut at, as the API returns them. */
export type SuitabilityScale = {
  red_floor: number;
  yellow_floor: number;
  cells_scored: number;
  model_weight: number;
};

/**
 * The fill for one cell, or null when no claim can be made.
 *
 * Null rather than green. Green means "already well served", which is a finding;
 * a missing scale is the absence of one, and painting the two the same colour
 * would turn "we could not score this" into "do not build here".
 */
export function suitabilityColour(value: number | null | undefined,
                                  scale: SuitabilityScale | null | undefined): string | null {
  if (value === null || value === undefined || !scale) return null;
  if (value >= scale.red_floor) return SUITABILITY_BANDS[0].colour;
  if (value >= scale.yellow_floor) return SUITABILITY_BANDS[1].colour;
  return SUITABILITY_BANDS[2].colour;
}

/** Denser where a cell scores higher, without implying a reading of its own. */
export function suitabilityOpacity(value: number | null | undefined): number {
  const t = Math.min(Math.max(value ?? 0, 0), 1);
  return 0.18 + t * 0.42;
}

/**
 * The colour key, as rows a planner can read off the map.
 *
 * WHY THE KEY IS BUILT HERE AND NOT WRITTEN INTO THE PANEL
 *
 * The counts and the colours have to be the ones actually on screen. Typed into
 * JSX they drift the first time a band moves, and a key that disagrees with the
 * map is worse than no key, because a key is believed. The map legend and the
 * panel key both read SUITABILITY_BANDS for the same reason.
 *
 * Grey is included. It is a colour on the map and it was the only one the card
 * described in a sentence and never showed, which is how a planner ends up
 * asking what the grey squares mean.
 *
 * Wording is deliberately free of "cell", "station", "resemblance" and
 * "percentile". A cell is a 500 m square we chose, a station is our column
 * name, and neither is what a planner calls the thing they are looking at.
 */
export function suitabilityKeyRows(distribution: PlannerAreaDistributionApi):
  Array<{ colour: string; label: string; count: number | null }> {
  if (!distribution.suitability_scale) return [];
  const counts = [distribution.cells_red, distribution.cells_yellow, distribution.cells_green];
  return [
    ...SUITABILITY_BANDS.map((band, i) => ({
      colour: band.colour, label: band.label, count: counts[i] ?? null
    })),
    { colour: BUILT_COLOUR, label: BUILT_LABEL, count: distribution.cells_with_station }
  ];
}

/**
 * One sentence under the key saying what the colours were decided on.
 *
 * Read off the scale rather than written down, for the same reason the floors
 * are: the split between demand and competition is a decision that can change,
 * and a sentence claiming 50/50 after it moved would be false.
 *
 * The raw floors are not printed. They are internal scores on a 0-1 range a
 * planner has no way to calibrate, and the API still returns them for anyone
 * who needs to audit the shading.
 */
export function suitabilityKeyNote(scale: SuitabilityScale | null | undefined): string {
  if (!scale) return '';
  const demand = Math.round(scale.model_weight * 100);
  return `Every place is ranked against all ${scale.cells_scored.toLocaleString()} we score `
    + `across Jabodetabek: ${demand}% on how busy we expect a charger there to be, `
    + `${100 - demand}% on how far it is from chargers that already exist. `
    + 'Green includes busy districts that are already well covered.';
}

/**
 * Why every place in view is the same colour, when it is.
 *
 * A uniform map is the one case where a correct answer and a broken scale look
 * identical. Around central Jakarta all 313 places come out green — and they
 * should, because the typical one already has 25 chargers within 2 km. Nothing
 * on screen said so, so it read as the heatmap not working.
 *
 * Returns null whenever there is a mix, which is most of the time. A note that
 * appears on every view is a note nobody reads.
 */
export function uniformBandNote(distribution: PlannerAreaDistributionApi): string | null {
  const { cells_red: red, cells_yellow: yellow, cells_green: green } = distribution;
  if (!distribution.suitability_scale || red === null || yellow === null || green === null) {
    return null;
  }
  const total = red + yellow + green;
  if (total === 0) return null;
  const band = red === total ? SUITABILITY_BANDS[0]
    : yellow === total ? SUITABILITY_BANDS[1]
    : green === total ? SUITABILITY_BANDS[2]
    : null;
  if (!band) return null;

  const lead = `All ${total.toLocaleString()} places here fall in the same band: `
    + `${band.label.toLowerCase()}.`;
  const near = distribution.median_stations_2km;
  if (band.key === 'green' && near !== null && near !== undefined && near > 0) {
    // The number that turns "the map is broken" into "the map is telling you
    // something". Nothing else in the response carries it.
    return `${lead} The typical place here already has ${near.toLocaleString()} `
      + `${near === 1 ? 'charger' : 'chargers'} within 2 km, so this area is well covered `
      + 'rather than unranked. Look further out for openings.';
  }
  return `${lead} There is nothing to separate them at this zoom — widen the area to `
    + 'compare it against somewhere different.';
}

/** Opacity that keeps a near-zero cell visible without implying a reading. */
export function resemblanceOpacity(probability: number, ceiling: number | null): number {
  const top = Math.max(ceiling ?? 0, MIN_SCALE_DIVISOR);
  const t = Math.min(Math.max(probability, 0), top) / top;
  return 0.12 + t * 0.38;
}

/**
 * What to tell the planner about the circle, in one line.
 *
 * Leads with how much of it is already built on, because that is the finding
 * this model is actually good for and the number a siting decision turns on.
 * The previous version led with "N cells score above 0.5", which counted
 * existing stations and offered them as candidates.
 */
export function distributionSummary(distribution: PlannerAreaDistributionApi): string {
  const { cells_with_station: built, cells_without_station: open, cells_predicted: n } = distribution;
  if (n === 0) return 'Nothing here is scored by the planner.';
  if (open === 0) return `All ${built.toLocaleString()} places here already have a charger.`;
  if (built === 0) return `None of the ${open.toLocaleString()} places here has a charger yet.`;
  return `${built.toLocaleString()} of ${n.toLocaleString()} places here already have a charger. `
    + `${open.toLocaleString()} do not.`;
}

/**
 * How to read the resemblance figure, in the planner's own terms.
 *
 * Always shown, never only on edge cases. The number is small by construction
 * and a reader with no scale will treat 0.26 as "26%, so poor", when it is in
 * fact near the top of what any unbuilt cell in Jabodetabek scores.
 */
export function resemblanceCaption(max: number | null, ceiling: number | null): string {
  if (max === null) return 'Nothing here is left to score.';
  // No ceiling means no scale, and a number with no scale is exactly what this
  // caption exists to prevent. Say the figure and stop, rather than reaching for
  // a remembered denominator that may no longer be the model's.
  if (ceiling === null || ceiling <= 0) {
    return `The strongest open place here scores ${max.toFixed(2)}. `
      + 'The Jabodetabek-wide comparison is unavailable right now, so there is nothing to '
      + 'read it against yet.';
  }
  const pctOfRange = Math.round((max / ceiling) * 100);
  // The ceiling stays in the sentence. 0.26 reads as "poor" to anyone who does
  // not know that 0.31 is as high as any place without a charger gets, and that
  // is the entire reason this caption exists.
  return `At ${max.toFixed(2)}, the strongest open place here reaches ${pctOfRange}% of the `
    + `best any place in Jabodetabek without a charger reaches (${ceiling.toFixed(2)}).`;
}

/**
 * The caveat for an area the model could not see all of.
 *
 * A truncated area looks exactly like a complete one on a map.
 */
export function truncationWarning(distribution: PlannerAreaDistributionApi): string | null {
  if (!distribution.truncated) return null;
  const { cells_predicted: scored, cells_in_area: total } = distribution;
  return `Showing the ${scored.toLocaleString()} busiest of ${total.toLocaleString()} places here. `
    + 'Shrink the radius before reading this as full coverage.';
}

/**
 * The caveat for cells scored but not drawn.
 *
 * Distinct from truncationWarning, and both can apply at once. That one means
 * the answer is incomplete; this one means the answer is complete but the
 * picture of it is not. Found by panning the real dashboard, where the API
 * reported 9,170 cells scored and truncated: false while the map drew 6,000.
 */
export function drawTruncationNote(drawn: number, scored: number): string | null {
  if (drawn >= scored) return null;
  return `Map shows the ${drawn.toLocaleString()} highest-scoring of ${scored.toLocaleString()} `
    + 'cells scored here. The summary above covers all of them.';
}
