import { fetchStation, type StationApiItem, type StationConnectorApiItem } from '@evflow/shared';

export type ValidSpkluSelection = {
  station: StationApiItem;
  connector: StationConnectorApiItem;
};

export type SpkluValidationResult =
  | { ok: true; value: ValidSpkluSelection }
  | { ok: false; error: string };

export type StationFetcher = (stationId: string) => Promise<StationApiItem>;

const stationIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

/**
 * EV-FLOW's backend contract identifies a station by its stable station `id`.
 * There is no URL-based QR contract, so scanner payloads are deliberately
 * limited to that identifier and the server remains the source of truth.
 */
export function parseSpkluStationId(payload: string): { ok: true; stationId: string } | { ok: false; error: string } {
  const stationId = payload.trim();
  if (!stationId) return { ok: false, error: 'The QR code or Station ID is empty.' };
  if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(stationId) || stationId.includes('://')) {
    return { ok: false, error: 'This QR code is a URL, not an EV-FLOW Station ID.' };
  }
  if (!stationIdPattern.test(stationId)) {
    return { ok: false, error: 'This QR code does not contain a valid EV-FLOW Station ID.' };
  }
  return { ok: true, stationId };
}

export async function validateSpkluPayload(
  payload: string,
  fetchStationById: StationFetcher = fetchStation,
): Promise<SpkluValidationResult> {
  const parsed = parseSpkluStationId(payload);
  if (!parsed.ok) return parsed;

  try {
    const station = await fetchStationById(parsed.stationId);
    const connector = station.connectors?.[0];
    if (!connector) {
      return { ok: false, error: 'This SPKLU has no charging connector configured.' };
    }
    return { ok: true, value: { station, connector } };
  } catch {
    return { ok: false, error: 'Station ID not found. Check the code and try again.' };
  }
}

export type SpkluSubmissionResult = SpkluValidationResult | { ignored: true };

/** Serializes decoder callbacks and remains locked only after acceptance. */
export class SpkluSubmissionGate {
  private pending = false;
  private accepted = false;

  async submit(
    payload: string,
    validator: (value: string) => Promise<SpkluValidationResult> = validateSpkluPayload,
  ): Promise<SpkluSubmissionResult> {
    if (this.pending || this.accepted) return { ignored: true };
    this.pending = true;
    try {
      const result = await validator(payload);
      if (result.ok) this.accepted = true;
      return result;
    } finally {
      this.pending = false;
    }
  }
}
