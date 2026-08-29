import { describe, expect, it, vi } from 'vitest';
vi.mock('react-native', () => ({ NativeModules: {} }));
import type { StationApiItem } from '@evflow/shared';
import { parseSpkluStationId, SpkluSubmissionGate, validateSpkluPayload } from './spkluQrValidation';

const station: StationApiItem = {
  id: 'pln_spklu-42', name: 'SPKLU Test', sources: ['pln_spklu'], latitude: -6.2, longitude: 106.8,
  address: null, province: null, city: null, operator: 'PLN', power_kw: 50, charge_type: 'fast',
  speed_tier: 'fast', connectors: [{ type: 'CCS2', count: 1, speed_tier: 'fast', power_kw: 50, type_inferred: false }],
  connector_types: ['CCS2'], connector_inferred: false, status: 'operational', date_verified: null, distance_km: null,
};

describe('SPKLU QR validation', () => {
  it('accepts a valid EV-FLOW SPKLU station identifier after server validation', async () => {
    const fetcher = vi.fn(async () => station);
    await expect(validateSpkluPayload('pln_spklu-42', fetcher)).resolves.toMatchObject({ ok: true, value: { station } });
    expect(fetcher).toHaveBeenCalledWith('pln_spklu-42');
  });

  it('rejects a random HTTPS URL, malformed payload, and empty payload locally', async () => {
    expect(parseSpkluStationId('https://example.com/random')).toMatchObject({ ok: false });
    expect(parseSpkluStationId('{"station":"anything"}')).toMatchObject({ ok: false });
    expect(parseSpkluStationId('   ')).toMatchObject({ ok: false });
  });

  it('rejects an unknown station identifier returned by server validation', async () => {
    const fetcher = vi.fn(async () => { throw new Error('404'); });
    await expect(validateSpkluPayload('pln_spklu-999999', fetcher)).resolves.toEqual({
      ok: false, error: 'Station ID not found. Check the code and try again.',
    });
  });

  it('rejects a known station without a configured connector', async () => {
    await expect(validateSpkluPayload('pln_spklu-42', async () => ({ ...station, connectors: [] }))).resolves.toMatchObject({ ok: false });
  });

  it('ignores duplicate rapid scans while validation or navigation acceptance is pending', async () => {
    let resolve!: (value: Awaited<ReturnType<typeof validateSpkluPayload>>) => void;
    const validator = vi.fn(() => new Promise<Awaited<ReturnType<typeof validateSpkluPayload>>>((done) => { resolve = done; }));
    const gate = new SpkluSubmissionGate();
    const first = gate.submit('pln_spklu-42', validator);
    await expect(gate.submit('pln_spklu-42', validator)).resolves.toEqual({ ignored: true });
    resolve({ ok: true, value: { station, connector: station.connectors[0] } });
    await expect(first).resolves.toMatchObject({ ok: true });
    await expect(gate.submit('pln_spklu-42', validator)).resolves.toEqual({ ignored: true });
    expect(validator).toHaveBeenCalledTimes(1);
  });

  it('allows a valid scan after an invalid scan', async () => {
    const gate = new SpkluSubmissionGate();
    await expect(gate.submit('bad payload', validateSpkluPayload)).resolves.toMatchObject({ ok: false });
    await expect(gate.submit('pln_spklu-42', (value) => validateSpkluPayload(value, async () => station))).resolves.toMatchObject({ ok: true });
  });
});
