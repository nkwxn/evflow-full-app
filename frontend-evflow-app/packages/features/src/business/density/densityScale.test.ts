import { describe, expect, it } from 'vitest';
import {
  DENSITY_CLASSES, classOpacity, classify, formatPeople, legendRows
} from './densityScale';

/** Roughly the real Jakarta viewport: 700 cells, p25 4,032, median 5,373, max 10,656. */
function jakartaLike(): number[] {
  return Array.from({ length: 700 }, (_, i) => 647 + Math.round((10_656 - 647) * ((i / 699) ** 0.6)));
}

describe('why the old scale failed', () => {
  it('uses the whole colour range even when values never approach zero', () => {
    // The old formula was 0.08 + sqrt(v / max) * 0.30. On this distribution it
    // put every cell between 0.29 and 0.38, a spread of 0.09, which is the flat
    // purple sheet the layer actually rendered.
    const scale = classify(jakartaLike())!;
    const opacities = jakartaLike().map((v) => classOpacity(scale.classOf(v)));
    const spread = Math.max(...opacities) - Math.min(...opacities);
    expect(spread).toBeGreaterThan(0.4);
  });

  it('spreads cells across every class rather than piling them into one', () => {
    // Fixed regional breaks (11 / 241 / 790 / 2,372) put 92% of this same
    // viewport in the top class. Equal-count classes cannot do that.
    const values = jakartaLike();
    const scale = classify(values)!;
    const counts = Array.from({ length: DENSITY_CLASSES }, () => 0);
    values.forEach((v) => { counts[scale.classOf(v)] += 1; });
    const share = counts.map((c) => c / values.length);
    expect(Math.max(...share)).toBeLessThan(0.35);
    expect(Math.min(...share)).toBeGreaterThan(0.1);
  });
});

describe('classification', () => {
  it('returns one fewer break than classes', () => {
    expect(classify([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])!.breaks).toHaveLength(DENSITY_CLASSES - 1);
  });

  it('puts the lowest value in the bottom class and the highest in the top', () => {
    const s = classify(jakartaLike())!;
    expect(s.classOf(s.min)).toBe(0);
    expect(s.classOf(s.max)).toBe(DENSITY_CLASSES - 1);
  });

  it('keeps identical values in one class rather than straddling a break', () => {
    const s = classify([5, 5, 5, 5, 5, 5, 5, 5])!;
    expect(new Set([5, 5, 5].map((v) => s.classOf(v))).size).toBe(1);
  });

  it('ignores values that are not numbers instead of counting them as zero', () => {
    // A missing reading is not a reading of zero. Counting it as zero would drag
    // every break down and darken the whole map.
    const withHoles = [1000, 2000, Number.NaN, 3000, Infinity, 4000] as number[];
    const s = classify(withHoles)!;
    expect(s.min).toBe(1000);
    expect(s.max).toBe(4000);
  });

  it('says so rather than guessing when there is nothing to classify', () => {
    expect(classify([])).toBeNull();
    expect(classify([Number.NaN])).toBeNull();
  });
});

describe('opacity', () => {
  it('keeps the lowest class visible, because low is a reading and blank is not', () => {
    expect(classOpacity(0)).toBeGreaterThan(0.1);
  });

  it('rises with the class and stays under full opacity', () => {
    const all = Array.from({ length: DENSITY_CLASSES }, (_, i) => classOpacity(i));
    expect(all).toEqual([...all].sort((a, b) => a - b));
    expect(all[all.length - 1]).toBeLessThan(0.7);
  });
});

describe('legend', () => {
  it('prints the real values, which is what stops a relative scale misleading', () => {
    // The colours are relative to what is on screen. That is the standard trade
    // for a choropleth and only misleads when hidden.
    const rows = legendRows(classify(jakartaLike())!, formatPeople);
    expect(rows).toHaveLength(DENSITY_CLASSES);
    expect(rows[0].label).toMatch(/^\d/);
    expect(rows[rows.length - 1].label).toContain('10,6');
  });

  it('formats people as whole numbers with separators', () => {
    expect(formatPeople(5373.4)).toBe('5,373');
  });
});
