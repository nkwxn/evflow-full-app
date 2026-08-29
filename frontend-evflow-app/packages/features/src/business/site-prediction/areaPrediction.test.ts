import { describe, expect, it } from 'vitest';
import type { PlannerAreaDistributionApi } from '@evflow/shared';
import {
  BUILT_COLOUR,
  DRAW_LIMIT,
  RADIUS_CHOICES,
  SCORE_LIMIT,
  SUITABILITY_BANDS,
  distributionSummary,
  drawTruncationNote,
  resemblanceCaption,
  RESEMBLANCE_BANDS,
  resemblanceBand,
  resemblanceColour,
  resemblanceOpacity,
  suitabilityColour,
  suitabilityKeyNote,
  suitabilityKeyRows,
  uniformBandNote,
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
    // The band floors, measured over all 27,219 scored cells.
    suitability_scale: { red_floor: 0.8342, yellow_floor: 0.6404,
                         cells_scored: 27_219, model_weight: 0.5 },
    cells_red: 4, cells_yellow: 12, cells_green: 45, median_stations_2km: 3,
    // The prescriptive figures. About 5 sessions per connector per day is what
    // the model returns for central Jakarta at the 2-connector, 22 kW spec.
    mean_sessions_per_connector_day: 5.49,
    median_sessions_per_connector_day: 5.4,
    max_sessions_per_connector_day: 6.86,
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
    expect(text).toMatch(/all 12 places here already have a charger/i);
  });

  it('says so plainly when nothing in the circle is built', () => {
    const text = distributionSummary(distribution({ cells_with_station: 0, cells_without_station: 40, cells_predicted: 40 }));
    expect(text).toMatch(/none of the 40/i);
  });

  it('does not divide by zero on an unscored circle', () => {
    const text = distributionSummary(distribution({ cells_predicted: 0, cells_with_station: 0, cells_without_station: 0 }));
    expect(text).toMatch(/nothing here is scored/i);
    expect(text).not.toContain('NaN');
  });
});

describe('the resemblance figure carries its own scale', () => {
  it('returns the exact legend tier used by site details at both boundaries', () => {
    expect(resemblanceBand(CEILING * 0.66, CEILING)).toBe(RESEMBLANCE_BANDS[0]);
    expect(resemblanceBand(CEILING * 0.33, CEILING)).toBe(RESEMBLANCE_BANDS[1]);
    expect(resemblanceBand(CEILING * 0.329, CEILING)).toBe(RESEMBLANCE_BANDS[2]);
    expect(resemblanceBand(0.2, null)).toBeNull();
    expect(resemblanceBand(0.2, 0)).toBeNull();
  });
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

describe('the legend renders from the same bands the fill is chosen from', () => {
  it('keeps them ordered high to low, which resemblanceColour relies on', () => {
    // The colour is picked with .find on the first floor cleared. Reorder this
    // array and every cell gets the wrong band, with nothing to catch it: the
    // map still renders, in colours that mean something else.
    const floors = RESEMBLANCE_BANDS.map((b) => b.floor);
    expect(floors).toEqual([...floors].sort((a, b) => b - a));
    expect(floors[floors.length - 1]).toBe(0);
  });

  it('gives each band its own colour, so the legend has no duplicate rows', () => {
    const colours = new Set(RESEMBLANCE_BANDS.map((b) => b.colour));
    expect(colours.size).toBe(RESEMBLANCE_BANDS.length);
  });

  it('paints a cell at the ceiling in the band the legend calls the top one', () => {
    // Ties the legend to the fill at the one value a reader is most likely to
    // check: the best cell on screen.
    expect(resemblanceColour(CEILING, CEILING)).toBe(RESEMBLANCE_BANDS[0].colour);
  });

  it('paints a near-zero cell in the band the legend calls the bottom one', () => {
    expect(resemblanceColour(0.001, CEILING))
      .toBe(RESEMBLANCE_BANDS[RESEMBLANCE_BANDS.length - 1].colour);
  });
});

describe('suitability bands', () => {
  const scale = { red_floor: 0.83, yellow_floor: 0.64, cells_scored: 27219, model_weight: 0.5 };

  it('cuts at the floors the API supplied, not at remembered constants', () => {
    expect(suitabilityColour(0.90, scale)).toBe(SUITABILITY_BANDS[0].colour);
    expect(suitabilityColour(0.83, scale)).toBe(SUITABILITY_BANDS[0].colour);
    expect(suitabilityColour(0.8299, scale)).toBe(SUITABILITY_BANDS[1].colour);
    expect(suitabilityColour(0.64, scale)).toBe(SUITABILITY_BANDS[1].colour);
    expect(suitabilityColour(0.6399, scale)).toBe(SUITABILITY_BANDS[2].colour);
    expect(suitabilityColour(0.0, scale)).toBe(SUITABILITY_BANDS[2].colour);
  });

  it('follows the floors when a retrain moves them', () => {
    // The whole reason the scale travels with the cells. Under a scale whose
    // floors have moved up, a value that was red must stop being red.
    const moved = { ...scale, red_floor: 0.95, yellow_floor: 0.80 };
    expect(suitabilityColour(0.90, scale)).toBe(SUITABILITY_BANDS[0].colour);
    expect(suitabilityColour(0.90, moved)).toBe(SUITABILITY_BANDS[1].colour);
  });

  it('paints nothing at all when there is no scale', () => {
    // Not green. Green means "already well served", which is a claim; no scale
    // means no claim can be made, and the two must not look the same.
    expect(suitabilityColour(0.9, null)).toBeNull();
    expect(suitabilityColour(null, scale)).toBeNull();
  });

  it('keeps the purple resemblance palette out of the red-green one', () => {
    // Two layers, two questions, two scales. They were merged once by accident
    // and the map said "high demand" where the model meant "looks like a place
    // someone already built".
    const suit = SUITABILITY_BANDS.map((b) => b.colour);
    for (const band of RESEMBLANCE_BANDS) expect(suit).not.toContain(band.colour);
    expect(suit).not.toContain(BUILT_COLOUR);
  });

  it('labels the bands by what they are, not by "high demand"', () => {
    // A quantile band cannot support "high demand": it says where a cell sits
    // among the others, not how much charging happens there.
    for (const band of SUITABILITY_BANDS) {
      expect(band.label.toLowerCase()).not.toContain('high demand');
      expect(band.label).toMatch(/\S/);
    }
  });
});

describe('the colour key a planner reads', () => {
  const scale = { red_floor: 0.83, yellow_floor: 0.64, cells_scored: 27219, model_weight: 0.5 };

  it('lists every colour on the map, with how many of each are here', () => {
    const rows = suitabilityKeyRows(distribution({
      suitability_scale: scale, cells_red: 4, cells_yellow: 12, cells_green: 45,
      cells_with_station: 55
    }));
    expect(rows.map((r) => r.count)).toEqual([4, 12, 45, 55]);
    // Grey is on the map, so it is in the key. It was the one colour the card
    // described in prose and never showed.
    expect(rows[3]?.colour).toBe(BUILT_COLOUR);
    expect(rows.every((r) => r.label.length > 0)).toBe(true);
  });

  it('says nothing rather than guessing when there is no scale', () => {
    expect(suitabilityKeyRows(distribution({ suitability_scale: null }))).toEqual([]);
  });

  it('speaks about places and chargers, not cells and stations', () => {
    // The planner is not a developer. "Cell" is a 500 m grid square we chose;
    // "station" is our column name.
    const rows = suitabilityKeyRows(distribution({ suitability_scale: scale }));
    const text = rows.map((r) => r.label).join(' ').toLowerCase();
    for (const jargon of ['cell', 'station', 'resemblance', 'quantile', 'percentile']) {
      expect(text).not.toContain(jargon);
    }
  });

  it('explains the blend in the planner\'s terms, from the scale it was given', () => {
    const lines = suitabilityKeyNote(scale);
    expect(lines).toContain('27,219');
    expect(lines).toContain('50%');
    expect(lines.toLowerCase()).not.toContain('model_weight');
    expect(suitabilityKeyNote(null)).toBe('');
  });
});


it('keeps the map legend and the panel key on one set of words', () => {
  // They were written twice, in two files, and would have disagreed the first
  // time either was reworded — which is the same class of bug as the map and the
  // card describing different quantities.
  const scale = { red_floor: 0.83, yellow_floor: 0.64, cells_scored: 27219, model_weight: 0.5 };
  const rows = suitabilityKeyRows(distribution({ suitability_scale: scale }));
  expect(rows.slice(0, 3).map((r) => r.label)).toEqual(SUITABILITY_BANDS.map((b) => b.label));
});

describe('a one-colour view explains itself', () => {
  const scale = { red_floor: 0.83, yellow_floor: 0.64, cells_scored: 27219, model_weight: 0.5 };

  it('says why a saturated area is uniformly green', () => {
    // The real case: 313 places around central Jakarta, every one green, and no
    // way for a planner to tell that from a broken scale. The median already
    // holds 25 chargers within 2 km — that is the answer, not a bug.
    const note = uniformBandNote(distribution({
      suitability_scale: scale, cells_red: 0, cells_yellow: 0, cells_green: 313,
      cells_without_station: 313, median_stations_2km: 25
    }));
    expect(note).toContain('25');
    expect(note?.toLowerCase()).toContain('already');
  });

  it('stays quiet when the view actually has a mix', () => {
    expect(uniformBandNote(distribution({
      suitability_scale: scale, cells_red: 4, cells_yellow: 12, cells_green: 45,
      cells_without_station: 61, median_stations_2km: 3
    }))).toBeNull();
  });

  it('stays quiet when there is no scale, and when there is nothing to describe', () => {
    expect(uniformBandNote(distribution({ suitability_scale: null }))).toBeNull();
    expect(uniformBandNote(distribution({
      suitability_scale: scale, cells_red: 0, cells_yellow: 0, cells_green: 0,
      cells_without_station: 0
    }))).toBeNull();
  });

  it('handles a uniformly strong area too, not just a saturated one', () => {
    const note = uniformBandNote(distribution({
      suitability_scale: scale, cells_red: 40, cells_yellow: 0, cells_green: 0,
      cells_without_station: 40, median_stations_2km: 0
    }));
    expect(note).toContain('40');
    expect(note?.toLowerCase()).toContain('best 10%');
  });
});
