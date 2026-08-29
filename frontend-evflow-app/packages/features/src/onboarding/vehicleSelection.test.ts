import { describe, expect, it } from 'vitest';
import type { EVModelApiItem } from '@evflow/shared';
import { brandOf, filterVehicleModels } from './vehicleSelection';

const model = (overrides: Partial<EVModelApiItem>): EVModelApiItem => ({
  id: '1', name: 'Hyundai Ioniq 5', make: 'Hyundai', model: 'Ioniq 5',
  battery_kwh: 72, range_km: 451, price_range: null, charging_time: null,
  source_url: null, ...overrides,
});

describe('vehicle selection filtering', () => {
  const models = [
    model({ id: 'ioniq', name: 'Hyundai Ioniq 5' }),
    model({ id: 'kona', name: 'Hyundai Kona Electric', model: 'Kona Electric' }),
    model({ id: 'atto', name: 'BYD Atto 3', make: 'BYD', model: 'Atto 3' }),
  ];

  it('does not render the full model wall until a brand or search is chosen', () => {
    expect(filterVehicleModels(models, null, '')).toEqual([]);
  });

  it('filters by the compact brand selection', () => {
    expect(filterVehicleModels(models, 'Hyundai', '').map(({ id }) => id)).toEqual(['ioniq', 'kona']);
  });

  it('searches manufacturer, model, and display name while respecting a selected brand', () => {
    expect(filterVehicleModels(models, null, 'byd').map(({ id }) => id)).toEqual(['atto']);
    expect(filterVehicleModels(models, null, 'kona').map(({ id }) => id)).toEqual(['kona']);
    expect(filterVehicleModels(models, 'Hyundai', 'atto')).toEqual([]);
  });

  it('keeps models without a manufacturer under Other', () => {
    expect(brandOf(model({ make: null }))).toBe('Other');
  });
});
