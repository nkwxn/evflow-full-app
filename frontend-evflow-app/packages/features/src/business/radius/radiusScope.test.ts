import { describe, expect, it } from 'vitest';
import {
  RADIUS_DEFAULT_KM, RADIUS_MAX_KM, RADIUS_MIN_KM, RADIUS_STEP_KM,
  circleBbox, clipToRadius, distanceKm, formatRadius, geometryCentre, ringCentre, withinRadius
} from './radiusScope';

const SUDIRMAN = { latitude: -6.2088, longitude: 106.8206 };

describe('distance', () => {
  it('measures a known separation to within a few metres', () => {
    // Sudirman to Monas is about 3.4 km.
    const monas = { latitude: -6.1754, longitude: 106.8272 };
    expect(distanceKm(SUDIRMAN, monas)).toBeGreaterThan(3.2);
    expect(distanceKm(SUDIRMAN, monas)).toBeLessThan(3.9);
  });

  it('is zero at the centre and symmetric', () => {
    expect(distanceKm(SUDIRMAN, SUDIRMAN)).toBeCloseTo(0, 6);
    const other = { latitude: -6.3, longitude: 106.9 };
    expect(distanceKm(SUDIRMAN, other)).toBeCloseTo(distanceKm(other, SUDIRMAN), 9);
  });
});

describe('bounding box of a circle', () => {
  it('contains the circle on every side', () => {
    const box = circleBbox(SUDIRMAN, 3);
    for (const bearing of [0, 90, 180, 270]) {
      const rad = (bearing * Math.PI) / 180;
      const point = {
        latitude: SUDIRMAN.latitude + (3 / 111.32) * Math.cos(rad),
        longitude: SUDIRMAN.longitude
          + (3 / (111.32 * Math.cos((SUDIRMAN.latitude * Math.PI) / 180))) * Math.sin(rad)
      };
      expect(point.latitude).toBeGreaterThanOrEqual(box.south - 1e-9);
      expect(point.latitude).toBeLessThanOrEqual(box.north + 1e-9);
      expect(point.longitude).toBeGreaterThanOrEqual(box.west - 1e-9);
      expect(point.longitude).toBeLessThanOrEqual(box.east + 1e-9);
    }
  });

  it('widens in longitude to account for converging meridians', () => {
    // A degree of longitude is shorter than a degree of latitude away from the
    // equator, so the same distance needs more degrees east-west.
    const box = circleBbox(SUDIRMAN, 5);
    expect(box.east - SUDIRMAN.longitude).toBeGreaterThan(box.north - SUDIRMAN.latitude);
  });

  it('grows with the radius', () => {
    const small = circleBbox(SUDIRMAN, 1);
    const large = circleBbox(SUDIRMAN, 5);
    expect(large.north - large.south).toBeGreaterThan(small.north - small.south);
  });
});

describe('clipping to the circle', () => {
  const at = (km: number) => ({
    latitude: SUDIRMAN.latitude + km / 111.32,
    longitude: SUDIRMAN.longitude
  });

  it('drops what the box included but the circle does not', () => {
    // This is the whole reason the clip exists: the box is 27% larger than the
    // circle inscribed in it, and its corners are outside the question asked.
    const items = [at(0.5), at(2.9), at(3.4), at(6)];
    const kept = clipToRadius(items, SUDIRMAN, 3, (p) => p);
    expect(kept).toHaveLength(2);
  });

  it('keeps a point exactly on the boundary', () => {
    expect(withinRadius(SUDIRMAN, 3, at(3))).toBe(true);
  });

  it('leaves everything alone before a point has been chosen', () => {
    // No circle means no question has been asked yet, and the layers still
    // follow the viewport so the planner can see where to click.
    const items = [at(1), at(50)];
    expect(clipToRadius(items, null, 3, (p) => p)).toHaveLength(2);
  });

  it('drops an item whose position cannot be read rather than keeping it', () => {
    // Drawn without knowing where it is, it would be inside the circle only by
    // accident.
    const kept = clipToRadius([{ ok: true }, { ok: false }], SUDIRMAN, 3,
      (i) => (i.ok ? SUDIRMAN : null));
    expect(kept).toHaveLength(1);
  });
});

describe('slider bounds', () => {
  it('offers a range that describes one place at both ends', () => {
    expect(RADIUS_MIN_KM).toBeGreaterThan(0);
    expect(RADIUS_MAX_KM).toBeLessThanOrEqual(25);
    expect(RADIUS_DEFAULT_KM).toBeGreaterThanOrEqual(RADIUS_MIN_KM);
    expect(RADIUS_DEFAULT_KM).toBeLessThanOrEqual(RADIUS_MAX_KM);
  });

  it('steps in whole half-kilometres, so the value is never 2.7413', () => {
    const steps = (RADIUS_MAX_KM - RADIUS_MIN_KM) / RADIUS_STEP_KM;
    expect(Number.isInteger(Number(steps.toFixed(6)))).toBe(true);
  });
});

describe('formatting', () => {
  it('uses metres below a kilometre, where the difference decides a site', () => {
    expect(formatRadius(0.5)).toBe('500 m');
  });

  it('uses kilometres above that', () => {
    expect(formatRadius(3.5)).toBe('3.5 km');
  });
});

describe('finding a cell centre', () => {
  const square = [[106.80, -6.20], [106.81, -6.20], [106.81, -6.21], [106.80, -6.21], [106.80, -6.20]];

  it('reads GeoJSON as longitude first', () => {
    // Backwards puts every cell in the Indian Ocean: obvious on a map, and
    // invisible to a test that only checks a centre came back.
    const c = ringCentre(square)!;
    expect(c.longitude).toBeGreaterThan(106);
    expect(c.latitude).toBeLessThan(0);
  });

  it('lands inside the square it was given', () => {
    const c = ringCentre(square)!;
    expect(c.longitude).toBeGreaterThan(106.80);
    expect(c.longitude).toBeLessThan(106.81);
    expect(c.latitude).toBeLessThan(-6.20);
    expect(c.latitude).toBeGreaterThan(-6.21);
  });

  it('handles both Polygon and MultiPolygon', () => {
    expect(geometryCentre({ type: 'Polygon', coordinates: [square] })).not.toBeNull();
    expect(geometryCentre({ type: 'MultiPolygon', coordinates: [[square]] })).not.toBeNull();
  });

  it('returns null rather than a guess for geometry it cannot read', () => {
    // clipToRadius drops what it cannot place, so a wrong guess here would draw
    // a cell inside a circle it is not in.
    expect(ringCentre([])).toBeNull();
    expect(geometryCentre({ type: 'Point', coordinates: [1, 2] })).toBeNull();
    expect(geometryCentre({ type: 'Polygon', coordinates: [] })).toBeNull();
  });
});
