/**
 * Turning a metric column into something a planner can actually read on a map.
 *
 * WHY THE OLD SCALE PRODUCED A FLAT WASH
 *
 * It divided each value by the largest value on screen and took a square root.
 * That works when the data runs from near zero to the maximum. Population does
 * not, inside a city. Measured on the Jakarta viewport in the screenshot: 700
 * cells, p25 4,032, median 5,373, p95 7,636, max 10,656. Every one of those is
 * between 38% and 100% of the maximum, and after the square root they all land
 * between opacity 0.29 and 0.38. A range of 0.09 is not a range anyone can see,
 * which is why the layer rendered as one flat purple sheet.
 *
 * WHY FIXED REGIONAL BREAKS WERE NOT THE ANSWER EITHER
 *
 * The obvious fix is absolute thresholds so a colour means the same thing
 * everywhere. Measured region-wide the population quantiles are 11, 241, 790
 * and 2,372, because most of Jabodetabek is countryside. Applying those to the
 * same Jakarta viewport puts 645 of its 700 cells -- 92% -- in the top class.
 * Honest, and just as useless: the planner still sees one flat sheet, only
 * darker.
 *
 * SO: QUANTILES OVER WHAT IS ON SCREEN, WITH THE NUMBERS SHOWN
 *
 * Equal-count classes across the cells actually returned. The full colour range
 * gets used at every zoom, whatever the distribution looks like. That makes the
 * colour relative to the current view, which is the standard trade for a
 * choropleth and only misleads if it is hidden -- so classify() also returns the
 * value at each break, for the legend to print. "Darkest = 8,100 people" is a
 * fact; "darkest = a lot" is not.
 */

/** Five classes: enough to show structure, few enough to tell apart. */
export const DENSITY_CLASSES = 5;

export type DensityScale = {
  /** Upper value of each class except the last. Length is DENSITY_CLASSES - 1. */
  breaks: number[];
  /** Lowest and highest value present, for the legend's end labels. */
  min: number;
  max: number;
  /** Which class a value falls in, 0 to DENSITY_CLASSES - 1. */
  classOf: (value: number) => number;
};

/**
 * Equal-count breaks over the values given.
 *
 * Cells with no value at all are excluded before classifying: a zero-population
 * cell is a real reading and belongs in the bottom class, but a missing one is
 * not a reading and would drag every break down if counted as zero.
 */
export function classify(values: number[]): DensityScale | null {
  const usable = values
    .filter((v) => typeof v === 'number' && Number.isFinite(v))
    .sort((a, b) => a - b);
  if (!usable.length) return null;

  const breaks: number[] = [];
  for (let i = 1; i < DENSITY_CLASSES; i += 1) {
    breaks.push(usable[Math.floor((usable.length * i) / DENSITY_CLASSES)] ?? usable[usable.length - 1]);
  }

  return {
    breaks,
    min: usable[0],
    max: usable[usable.length - 1],
    classOf(value: number) {
      // Upper bound is exclusive so identical values cannot straddle a break and
      // land in two different colours.
      let index = 0;
      while (index < breaks.length && value >= breaks[index]) index += 1;
      return index;
    }
  };
}

/**
 * Opacity per class, spread across a range the eye can separate.
 *
 * Starts at 0.12 rather than 0: the bottom class is "measured and low", not "no
 * data", and an invisible cell says the second thing.
 */
export function classOpacity(classIndex: number): number {
  const step = (0.62 - 0.12) / (DENSITY_CLASSES - 1);
  return Number((0.12 + step * classIndex).toFixed(3));
}

/** Legend rows, coarsest first, each labelled with the values it covers. */
export function legendRows(scale: DensityScale, format: (v: number) => string) {
  const bounds = [scale.min, ...scale.breaks, scale.max];
  return Array.from({ length: DENSITY_CLASSES }, (_, i) => ({
    classIndex: i,
    opacity: classOpacity(i),
    label: `${format(bounds[i])} – ${format(bounds[i + 1])}`
  }));
}

/** Thousands separators, and no decimals: nobody sites a charger on half a person. */
export function formatPeople(value: number): string {
  return Math.round(value).toLocaleString();
}
