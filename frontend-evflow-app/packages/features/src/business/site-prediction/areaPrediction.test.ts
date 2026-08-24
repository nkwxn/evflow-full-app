import { describe, expect, it } from 'vitest';
import type { PlannerAreaDistributionApi } from '@evflow/shared';
import {
  DRAW_LIMIT,
  RADIUS_CHOICES,
  SCORE_LIMIT,
  distributionSummary,
  drawTruncationNote,
  resemblanceCaption,
  resemblanceColour,
  resemblanceOpacity,
  truncationWarning
} from './areaPrediction';

/** The regional ceiling the API supplies. Measured at 0.305. */
const CEILING = 0.31;

function distribution(over: Partial<PlannerAreaDistributionApi> = {}): PlannerAreaDistributionApi {
  // Roughly the real 3 km circle around Sudirman: 136 cells, 75 already built.
  return {
    cells_in_area: 136, cells_predicted: 136, truncated: false,
    cells_with_station: 75, cells_without_station: 61,
    mean_probability: 0.08, median_probability: 0.05, max_probability: 0.26,
    // Supplied by the API now, measured at 0.305 across all 26,334 unbuilt cells.
    resemblance_ceiling: 0.31, resemblance_ceiling_cells: 26_334,
    ...over
  };
}

describe('the summary leads with what is already built', () => {
  it('names the built cells rather than folding them into a total', () => {
    // The previous version led with "N cells score above 0.5". On the real grid
    // no unbuilt cell reaches 0.305, so that count was existing stations being
    // offered as candidates.
    const text = distributionSummary(distribution());
    expect(text).toContain('75');
    expect(text).toContain('136');
    expect(text).toContain('61');
  });

  it('says so plainly when the whole circle is already built', () => {
    const text = distributionSummary(distribution({ cells_with_station: 12, cells_without_station: 0, cells_predicted: 12 }));
    expect(text).toMatch(/all 12 cells here already have a station/i);
  });

  it('says so plainly when nothing in the circle is built', () => {
    const text = distributionSummary(distribution({ cells_with_station: 0, cells_without_station: 40, cells_predicted: 40 }));
    expect(text).toMatch(/none of the 40/i);
  });

  it('does not divide by zero on an unscored circle', () => {
    const text = distributionSummary(distribution({ cells_predicted: 0, cells_with_station: 0, cells_without_station: 0 }));
    expect(text).toMatch(/no cells/i);
    expect(text).not.toContain('NaN');
  });
});

describe('the resemblance figure carries its own scale', () => {
  it('says what the number is a fraction of', () => {
    // 0.26 reads as "poor" to anyone who does not know that 0.31 is the highest
    // any unbuilt cell in Jabodetabek reaches.
    const text = resemblanceCaption(0.26, CEILING);
    expect(text).toContain('0.26');
    expect(text).toContain('0.31');
    expect(text).toContain('84%');
  });

  it('says there is nothing left to score rather than showing a zero', () => {
    expect(resemblanceCaption(null, CEILING)).toMatch(/nothing here is left to score/i);
  });

  it('drops the comparison entirely when the region-wide scale is unavailable', () => {
    // The percentage is the whole reason this caption exists, and it is only
    // meaningful against the ceiling the model actually produces. Falling back
    // to a remembered 0.31 is precisely the failure that moving the ceiling out
    // of the frontend was meant to end.
    const text = resemblanceCaption(0.26, null);
    expect(text).toContain('0.26');
    expect(text).not.toMatch(/\d+%/);
    expect(text).toMatch(/unavailable/i);
  });

  it('scales the percentage to whatever ceiling the API reports, not a constant', () => {
    // Same local score, two different models: the reading must move with the
    // denominator rather than stay pinned to a number written down last month.
    expect(resemblanceCaption(0.15, 0.30)).toContain('50%');
    expect(resemblanceCaption(0.15, 0.60)).toContain('25%');
  });
});

describe('colour scale for unbuilt cells', () => {
  it('is calibrated to what unbuilt cells actually reach, not to 0.5', () => {
    // Measured: of 26,334 cells with no station, the highest is 0.305 and none
    // crosses 0.5. On a 0-to-1 scale every one of them would render identical.
    expect(CEILING).toBeLessThan(0.5);
    expect(resemblanceColour(0.30, CEILING)).not.toBe(resemblanceColour(0.02, CEILING));
  });

  it('is fixed, so the same colour means the same thing in two places', () => {
    // Normalising per circle would repaint a weak area to look exactly like a
    // strong one, and a planner comparing Serpong with Sudirman would see no
    // difference between 0.18 and 0.26.
    expect(resemblanceColour(0.26, CEILING)).toBe(resemblanceColour(0.26, CEILING));
    expect(resemblanceColour(0.30, CEILING)).toBe(resemblanceColour(0.9, CEILING));
  });

  it('does not borrow the demand heatmap palette', () => {
    // Red/amber/green reads as priority. These numbers are not a priority
    // ranking, and the best unbuilt cell near Sudirman is 0.26.
    const heatmap = ['#ef4444', '#f59e0b', '#10b981'];
    for (const p of [0, 0.1, 0.2, 0.3]) expect(heatmap).not.toContain(resemblanceColour(p, CEILING));
  });

  it('keeps a near-zero cell visible rather than invisible', () => {
    // Invisible reads as "no data", which is a different claim from "scored low".
    expect(resemblanceOpacity(0, CEILING)).toBeGreaterThan(0);
    expect(resemblanceOpacity(CEILING, CEILING)).toBeGreaterThan(resemblanceOpacity(0, CEILING));
  });

  it('clamps out-of-range values instead of running off the scale', () => {
    expect(resemblanceOpacity(-5, CEILING)).toBe(resemblanceOpacity(0, CEILING));
    expect(resemblanceOpacity(99, CEILING)).toBe(resemblanceOpacity(CEILING, CEILING));
  });
});

describe('truncation', () => {
  it('is silent when the circle was fully covered', () => {
    expect(truncationWarning(distribution())).toBeNull();
  });

  it('names both numbers when the circle was clipped', () => {
    const text = truncationWarning(distribution({ truncated: true, cells_predicted: 6_000, cells_in_area: 9_170 }));
    expect(text).toContain('6,000');
    expect(text).toContain('9,170');
  });
});

describe('drawn versus scored', () => {
  it('says so when the map shows fewer cells than were scored', () => {
    // Found by panning the real dashboard: the API reported 9,170 scored and
    // truncated: false, which was correct, while the map quietly drew 6,000.
    const note = drawTruncationNote(6_000, 9_170);
    expect(note).toContain('6,000');
    expect(note).toContain('9,170');
  });

  it('is silent when every scored cell is on the map', () => {
    expect(drawTruncationNote(136, 136)).toBeNull();
  });

  it('is a different caveat from a clipped score, and both can apply', () => {
    const clipped = distribution({ truncated: true, cells_predicted: 9_170, cells_in_area: 12_000 });
    expect(truncationWarning(clipped)).not.toBeNull();
    expect(drawTruncationNote(6_000, clipped.cells_predicted)).not.toBeNull();
  });
});

describe('request limits', () => {
  it('scores at least as many cells as it draws', () => {
    expect(SCORE_LIMIT).toBeGreaterThanOrEqual(DRAW_LIMIT);
  });

  it('covers the largest circle the API allows without truncating', () => {
    // A 25 km circle is about 9,800 cells at 400 m.
    expect(SCORE_LIMIT).toBeGreaterThanOrEqual(9_800);
  });

  it('stays inside the API ceiling it is sent to', () => {
    // Shipped once at 6,000 against a ceiling of 4,000: typecheck clean, every
    // test green, and the dashboard showed nothing but the validation error.
    expect(DRAW_LIMIT).toBeLessThanOrEqual(10_000);
    expect(SCORE_LIMIT).toBeLessThanOrEqual(30_000);
  });

  it('offers radii small enough to describe one place', () => {
    expect(RADIUS_CHOICES.every((km) => km > 0 && km <= 25)).toBe(true);
  });
});
