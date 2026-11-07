import { assertSecureProductionApiBaseUrl, LOCAL_BACKEND_PORT, logDevApiBaseUrl, normalizeApiBaseUrl } from './baseUrl.shared';

declare const __DEV__: boolean | undefined;

function pickStringEnv(...values: Array<string | boolean | undefined>) {
  return values.find((value): value is string => typeof value === 'string' && value.trim() !== '');
}

function isDevBuild() {
  return typeof __DEV__ !== 'undefined' && __DEV__ === true;
}

export function getEvflowApiBaseUrl() {
  const env = typeof process !== 'undefined' ? process.env : undefined;
  const override = pickStringEnv(
    env?.EXPO_PUBLIC_EVFLOW_API_BASE_URL,
    env?.EXPO_PUBLIC_API_BASE_URL,
    env?.EVFLOW_API_BASE_URL
  );
  const isDev = isDevBuild();

  // In dev default to the backend running on the dev machine so frontend work
  // never mutates production data; release builds keep the deployed API.
  if (!override && isDev) {
    const localBaseUrl = normalizeApiBaseUrl(`http://localhost:${LOCAL_BACKEND_PORT}`);
    logDevApiBaseUrl(localBaseUrl, 'EXPO_PUBLIC_EVFLOW_API_BASE_URL');
    return localBaseUrl;
  }

  const baseUrl = normalizeApiBaseUrl(override);
  if (isDev) {
    logDevApiBaseUrl(baseUrl, 'EXPO_PUBLIC_EVFLOW_API_BASE_URL');
  }
  return assertSecureProductionApiBaseUrl(baseUrl, isDev);
}

export const getApiBaseUrl = getEvflowApiBaseUrl;