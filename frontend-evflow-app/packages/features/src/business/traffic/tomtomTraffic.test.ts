import { describe, expect, it } from 'vitest';
import {
  TOMTOM_ATTRIBUTION, TRAFFIC_EMPTY_NOTE, TRAFFIC_LEGEND, tomtomKey, trafficOverlay
} from './tomtomTraffic';

describe('reading the key', () => {
  it('accepts a real key', () => {
    expect(tomtomKey({ VITE_TOMTOM_API_KEY: 'abc123' })).toBe('abc123');
  });

  it('treats missing, empty and whitespace all as no key', () => {
    // .env.example ships the variable with no value, so "present but empty" is
    // the normal state for anyone who has not signed up.
    expect(tomtomKey(undefined)).toBeNull();
    expect(tomtomKey({})).toBeNull();
    expect(tomtomKey({ VITE_TOMTOM_API_KEY: '' })).toBeNull();
    expect(tomtomKey({ VITE_TOMTOM_API_KEY: '   ' })).toBeNull();
  });
});

describe('the overlay', () => {
  it('is null without a key, rather than a layer of 403s', () => {
    // Every tile would come back forbidden and the map would be pocked with
    // missing squares, which reads as a broken map rather than an absent layer.
    expect(trafficOverlay(null)).toBeNull();
  });

  it('builds a Leaflet tile template with z, x and y placeholders', () => {
    const layer = trafficOverlay('abc123')!;
    expect(layer.url).toContain('{z}');
    expect(layer.url).toContain('{x}');
    expect(layer.url).toContain('{y}');
  });

  it('uses the flow endpoint documented for raster tiles', () => {
    expect(trafficOverlay('abc123')!.url).toContain('/traffic/map/4/tile/flow/');
  });

  it('draws only the roads that differ from free flow', () => {
    // relative0-dark paints every road, so a healthy city is a screen full of
    // green that competes with this dashboard's own green dashed links and
    // buries the few amber segments worth acting on.
    const url = trafficOverlay('abc123')!.url;
    expect(url).toContain('relative-delay');
    expect(url).not.toContain('/absolute/');
    expect(url).not.toContain('relative0');
  });

  it('escapes the key rather than pasting it into the URL raw', () => {
    expect(trafficOverlay('a b&c')!.url).toContain('key=a%20b%26c');
  });

  it('carries the attribution TomTom requires wherever their data is shown', () => {
    expect(trafficOverlay('abc123')!.attribution).toBe(TOMTOM_ATTRIBUTION);
    expect(TOMTOM_ATTRIBUTION).toContain('TomTom');
  });

  it('stops at the base map zoom so it never floats over blank tiles', () => {
    expect(trafficOverlay('abc123')!.maxZoom).toBe(19);
  });
});

describe('the legend', () => {
  it('has no green entry, because free-flowing roads are not drawn at all', () => {
    const greens = TRAFFIC_LEGEND.filter((r) => /free|green|normal/i.test(r.label));
    expect(greens).toHaveLength(0);
  });

  it('runs worst first, which is the order a planner reads', () => {
    expect(TRAFFIC_LEGEND[0].label).toMatch(/closed/i);
  });

  it('says why the layer can look empty', () => {
    // Otherwise "no congestion" and "layer broken" are the same picture.
    expect(TRAFFIC_EMPTY_NOTE).toMatch(/not drawn/i);
  });
});
