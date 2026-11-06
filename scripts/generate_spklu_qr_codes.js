#!/usr/bin/env node

/**
 * Generate scanner-compatible EV-FLOW QR assets from station-list API snapshots.
 *
 * The scanner accepts only the stable station ID as the QR payload. This script
 * deliberately excludes URLs, JSON wrappers, and display labels from the encoded
 * value. It uses the QR implementation already installed with qrcode-terminal.
 */

const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');
const QRCode = require(path.join(
  repoRoot,
  'frontend-evflow-app/node_modules/qrcode-terminal/vendor/QRCode',
));
const QRErrorCorrectLevel = require(path.join(
  repoRoot,
  'frontend-evflow-app/node_modules/qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel',
));

const STATION_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const QUIET_ZONE_MODULES = 4;

function usage() {
  console.error(
    'Usage: node scripts/generate_spklu_qr_codes.js <output-dir> <station-page.json> [station-page.json ...]',
  );
  process.exit(2);
}

function xmlEscape(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function csvCell(value) {
  const text = value == null ? '' : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function qrSvg(payload) {
  const qr = new QRCode(-1, QRErrorCorrectLevel.H);
  qr.addData(payload);
  qr.make();

  const moduleCount = qr.getModuleCount();
  const size = moduleCount + QUIET_ZONE_MODULES * 2;
  const darkModules = [];
  for (let row = 0; row < moduleCount; row += 1) {
    for (let col = 0; col < moduleCount; col += 1) {
      if (qr.isDark(row, col)) {
        darkModules.push(`<rect x="${col + QUIET_ZONE_MODULES}" y="${row + QUIET_ZONE_MODULES}" width="1" height="1"/>`);
      }
    }
  }

  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="512" height="512" role="img" aria-label="EV-FLOW station ${xmlEscape(payload)} QR code" shape-rendering="crispEdges">`,
    '<rect width="100%" height="100%" fill="#fff"/>',
    `<g fill="#000">${darkModules.join('')}</g>`,
    '</svg>',
    '',
  ].join('\n');
}

function readStations(files) {
  const pages = files.map((file) => JSON.parse(fs.readFileSync(file, 'utf8')));
  for (const [index, page] of pages.entries()) {
    if (!Array.isArray(page.items)) {
      throw new Error(`${files[index]} is not an EV-FLOW station-list response`);
    }
  }
  return pages.flatMap((page) => page.items);
}

function main() {
  const [, , outputArg, ...inputFiles] = process.argv;
  if (!outputArg || inputFiles.length === 0) usage();

  const outputDir = path.resolve(outputArg);
  const qrDir = path.join(outputDir, 'svg');
  if (fs.existsSync(outputDir)) {
    throw new Error(`Refusing to overwrite existing output directory: ${outputDir}`);
  }

  const allStations = readStations(inputFiles);
  const stations = allStations
    .filter((station) => station.sources?.includes('pln_spklu'))
    .filter((station) => Array.isArray(station.connectors) && station.connectors.length > 0)
    .sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true }));

  const seen = new Set();
  for (const station of stations) {
    if (!STATION_ID_PATTERN.test(station.id)) {
      throw new Error(`Scanner-invalid station ID: ${JSON.stringify(station.id)}`);
    }
    if (seen.has(station.id)) throw new Error(`Duplicate station ID: ${station.id}`);
    seen.add(station.id);
  }

  fs.mkdirSync(qrDir, { recursive: true });
  for (const station of stations) {
    fs.writeFileSync(path.join(qrDir, `${station.id}.svg`), qrSvg(station.id));
  }

  const generatedAt = new Date().toISOString();
  const manifestHeader = [
    'station_id',
    'station_name',
    'city',
    'province',
    'connector_types',
    'connector_count',
    'qr_payload',
    'qr_file',
  ];
  const manifestRows = stations.map((station) => {
    const connectorCount = station.connectors.reduce(
      (sum, connector) => sum + (Number(connector.count) || 0),
      0,
    );
    return [
      station.id,
      station.name,
      station.city,
      station.province,
      station.connectors.map((connector) => connector.type).join(' | '),
      connectorCount,
      station.id,
      `svg/${station.id}.svg`,
    ].map(csvCell).join(',');
  });
  fs.writeFileSync(
    path.join(outputDir, 'manifest.csv'),
    `${manifestHeader.join(',')}\n${manifestRows.join('\n')}\n`,
  );

  const cards = stations.map((station) => `
    <article class="card">
      <img src="svg/${xmlEscape(station.id)}.svg" alt="QR code for ${xmlEscape(station.id)}">
      <div class="station-id">${xmlEscape(station.id)}</div>
      <div class="station-name">${xmlEscape(station.name || 'Unnamed SPKLU')}</div>
      <div class="location">${xmlEscape([station.city, station.province].filter(Boolean).join(', '))}</div>
    </article>`).join('');
  fs.writeFileSync(
    path.join(outputDir, 'index.html'),
    `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EV-FLOW Production SPKLU QR Codes</title>
  <style>
    :root { font: 14px/1.35 system-ui, sans-serif; color: #111827; }
    body { margin: 24px; }
    header { margin-bottom: 24px; }
    h1 { margin-bottom: 6px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }
    .card { border: 1px solid #d1d5db; border-radius: 12px; padding: 14px; break-inside: avoid; text-align: center; }
    .card img { display: block; width: 100%; max-width: 210px; margin: auto; }
    .station-id { margin-top: 8px; font: 700 13px/1.3 ui-monospace, monospace; overflow-wrap: anywhere; }
    .station-name { margin-top: 5px; font-weight: 600; }
    .location { margin-top: 3px; color: #4b5563; font-size: 12px; }
    @media print {
      @page { size: A4; margin: 10mm; }
      body { margin: 0; }
      header { display: none; }
      .grid { grid-template-columns: repeat(3, 1fr); gap: 5mm; }
      .card { border-radius: 0; padding: 3mm; }
      .card img { max-width: 45mm; }
    }
  </style>
</head>
<body>
  <header>
    <h1>EV-FLOW Production SPKLU QR Codes</h1>
    <div>${stations.length.toLocaleString('en-US')} scanner-validated PLN-backed stations · generated ${xmlEscape(generatedAt)}</div>
  </header>
  <main class="grid">${cards}
  </main>
</body>
</html>
`,
  );

  fs.writeFileSync(
    path.join(outputDir, 'README.md'),
    `# EV-FLOW production SPKLU QR codes

- Generated: ${generatedAt}
- Production API: https://ev-flow.opensoft.id/api/v1/stations
- Included QR codes: ${stations.length}
- Encoded payload: the exact stable \`station.id\` only
- Selection: station contains the \`pln_spklu\` source and at least one connector
- QR error correction: H
- Quiet zone: ${QUIET_ZONE_MODULES} modules

Open \`index.html\` to browse or print labeled cards. Use \`manifest.csv\` for the station metadata and payload-to-file mapping.
`,
  );

  console.log(JSON.stringify({
    fetched: allStations.length,
    generated: stations.length,
    outputDir,
    generatedAt,
  }, null, 2));
}

main();
