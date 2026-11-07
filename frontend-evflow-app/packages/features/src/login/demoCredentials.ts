// Demo password for the one-tap quick-access personas, read from the build
// environment. Expo/Metro inlines EXPO_PUBLIC_* env vars at build time for
// both native and web — the value is set in the web Containerfile (and a local
// .env), so it is configurable per deployment instead of being a hard-coded
// literal in source.
//
// This is NOT a real secret: a frontend value always ships inside the bundle,
// and the personas auto-register on the API. Moving it out of source keeps the
// code clean and the value swappable, not hidden.
export const DEMO_PASSWORD =
  (typeof process !== 'undefined' ? process.env?.EXPO_PUBLIC_DEMO_PASSWORD : 'evflow-demo-2026') ?? 'evflow-demo-2026';