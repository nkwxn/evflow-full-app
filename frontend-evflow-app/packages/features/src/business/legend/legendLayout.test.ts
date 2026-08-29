import { describe, expect, it } from 'vitest';
import {
  LEGEND_BREAKPOINT, legendMaxHeight, legendPillLabel, shouldCollapseLegends
} from './legendLayout';

describe('shouldCollapseLegends', () => {
  it('leaves a wide screen alone: the map is still visible beside the key', () => {
    expect(shouldCollapseLegends(1440, 3)).toBe(false);
    expect(shouldCollapseLegends(LEGEND_BREAKPOINT, 3)).toBe(false);
  });

  it('folds the key on a phone, where two legends cover the map', () => {
    expect(shouldCollapseLegends(390, 2)).toBe(true);
    expect(shouldCollapseLegends(LEGEND_BREAKPOINT - 1, 1)).toBe(true);
  });

  it('has nothing to fold when no layer is on', () => {
    expect(shouldCollapseLegends(390, 0)).toBe(false);
  });
});

describe('legendMaxHeight', () => {
  it('scales with the viewport rather than a fixed guess', () => {
    expect(legendMaxHeight(844)).toBe(380);
    expect(legendMaxHeight(390)).toBe(176);
  });
});

describe('legendPillLabel', () => {
  it('names how many layers are on, so the pill is not a mystery button', () => {
    expect(legendPillLabel(1)).toBe('1 layer key');
    expect(legendPillLabel(3)).toBe('3 layer keys');
  });

  it('falls back to a plain name when nothing is on', () => {
    expect(legendPillLabel(0)).toBe('Map key');
  });
});
