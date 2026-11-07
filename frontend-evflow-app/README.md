# EVFlow Frontend

Expo Router + React Native TypeScript monorepo for EVFlow. One Metro pipeline
bundles the shared screens for web, Android, and iOS.

For the full-stack development workflow, architecture, API, environment behavior,
and current implementation gaps, start with the root
[documentation index](../docs/README.md).

## Project Structure

```text
apps/
  mobile/       Expo Router app: Android, iOS, and web (one Metro pipeline)

packages/
  shared/       API client, TypeScript types, data helpers, charger filtering, route planning logic
  ui/           Shared buttons, cards, filters, and layout components
  features/     Shared feature modules and screens used by mobile and web
```

`packages/features` holds screens and user flows. Keep `apps/mobile` focused on
platform startup code, the Expo Router route tree (`app/`), fonts, and native
metadata, while feature screens live in reusable modules.

## Prerequisites

- Node.js 20.19.4 or newer on the Node 20 line, or Node.js 22.12 or newer
- npm 10 or newer
- Expo tooling through `npx expo`
- Android Studio for Android emulator builds
- Xcode for iOS simulator builds on macOS

## Install

```bash
npm ci
```

npm is the repository's current package-manager convention: the committed
lockfile, container build, and scripts all use it, despite the legacy Yarn value
in `package.json` metadata.

## Run Mobile

Start Expo from the mobile app workspace:

```bash
npm run mobile
```

Run on a physical device over the same Wi-Fi network:

```bash
npm run mobile:lan
```

If Expo Go cannot connect to a local `exp://192.168.x.x:8081` URL, use a tunnel instead:

```bash
npm run mobile:tunnel
```

Use tunnel mode when the phone and computer are on different networks, a VPN is active, a firewall blocks port `8081`, or the Wi-Fi network blocks device-to-device traffic.

Run Android:

```bash
npm run mobile:android
```

Run iOS:

```bash
npm run mobile:ios
```

You can also run Expo directly:

```bash
npm run start --workspace @evflow/mobile
```

## Run Web

Start the Expo web dev server (Metro):

```bash
npm run web
```

Build the production web bundle:

```bash
npm run build:web
```

Preview the production web build:

```bash
npx serve dist
```

## Typecheck

```bash
npm run typecheck
```

## Mobile Build And Deployment

This app is ready to use Expo Application Services.

Install and log in to EAS:

```bash
npm install -g eas-cli
eas login
```

Configure native builds:

```bash
cd apps/mobile
eas build:configure
```

Create Android and iOS builds:

```bash
eas build --platform android
eas build --platform ios
```

Submit builds to app stores:

```bash
eas submit --platform android
eas submit --platform ios
```

## Web Deployment

The web output is generated in `dist/` at the workspace root.

```bash
npm run build:web
```

Deploy `dist/` to a static host such as Vercel, Netlify, Cloudflare Pages, or
GitHub Pages. The container image copies the same `dist/` directory.

## Repository

This app lives in the `evflow-fullstack` monorepo alongside the FastAPI backend (`backend-ev-flow/`). See the repository root README for fullstack setup.
