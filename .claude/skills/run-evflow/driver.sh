#!/usr/bin/env bash
# EVFlow local runner + planner API smoke.
#
# The app is two processes that only mean anything together: a FastAPI
# backend and a Vite dev server. Neither has a local database, so the
# backend borrows staging's over an SSH tunnel (see WHY THE TUNNEL below).
#
#   ./driver.sh up      tunnel + API + web, wait until each answers
#   ./driver.sh smoke   drive every planner endpoint, assert real values
#   ./driver.sh status  what is listening and what it is talking to
#   ./driver.sh down    stop all three
#
# WHY THE TUNNEL: the backend needs PostgreSQL *with PostGIS* plus a loaded
# planning_cells grid. Homebrew postgresql@15 on this machine has no PostGIS
# extension available at all, and building the grid locally means reprocessing
# an 854 MB OSM extract. Borrowing staging's database is the only path that
# gets you a working planner in under a minute. Set DATABASE_URL yourself to
# skip the tunnel entirely if you do have a local PostGIS.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUN_DIR="${TMPDIR:-/tmp}/evflow-run"
mkdir -p "$RUN_DIR"

SSH_KEY="${EVFLOW_SSH_KEY:-$HOME/Downloads/project-mon.pem}"
SSH_HOST="${EVFLOW_SSH_HOST:-mvvkur@103.127.99.179}"
DB_PORT="${EVFLOW_DB_PORT:-5433}"
API_PORT="${EVFLOW_API_PORT:-8000}"
WEB_PORT="${EVFLOW_WEB_PORT:-5173}"
DEMO_PASSWORD="${VITE_DEMO_PASSWORD:-evflow-demo-2026}"
# The staging password is a dev-grade default, not a secret worth protecting: it
# guards a database reachable only through an SSH tunnel that this script opens
# with a key file. It is still read from the environment first, so the literal
# stops being the only source and a real deployment can override it without
# editing a tracked file.
#
# api/db.py deliberately has NO password default at all. That asymmetry is on
# purpose: this is a local convenience script, that is the production path.
EVFLOW_DB_USER="${EVFLOW_DB_USER:-evflow}"
EVFLOW_DB_PASSWORD="${EVFLOW_DB_PASSWORD:-evflow}"
EVFLOW_DB_NAME="${EVFLOW_DB_NAME:-evflow_staging}"
DEFAULT_DB="postgresql+psycopg://${EVFLOW_DB_USER}:${EVFLOW_DB_PASSWORD}@localhost:${DB_PORT}/${EVFLOW_DB_NAME}"

API_LOG="$RUN_DIR/api.log"
WEB_LOG="$RUN_DIR/web.log"

green() { printf "  \033[32m%s\033[0m %s\n" "OK" "$*"; }
red()   { printf "  \033[31m%s\033[0m %s\n" "!!" "$*"; }
info()  { printf "  .. %s\n" "$*"; }

# ---------------------------------------------------------------- tunnel

tunnel_up() {
  if [ -n "${DATABASE_URL:-}" ] && [[ "${DATABASE_URL}" != *"localhost:${DB_PORT}"* ]]; then
    info "DATABASE_URL set externally; skipping tunnel"
    return 0
  fi
  # The PORT, not the process. An ssh still running but no longer forwarding
  # passes pgrep and fails every query, and the API then answers
  # {"status":"ok","stations_loaded":0} while the dashboard shows an empty map.
  if (exec 3<>"/dev/tcp/127.0.0.1/${DB_PORT}") 2>/dev/null; then
    exec 3>&-
    green "tunnel already up on :${DB_PORT}"
    return 0
  fi
  # Bound but not forwarding: clear the corpse before binding again, or ssh
  # fails with "address already in use" and up() reports success either way.
  pkill -f "${DB_PORT}:localhost:5432" 2>/dev/null && sleep 1
  [ -f "$SSH_KEY" ] || { red "ssh key not found: $SSH_KEY (set EVFLOW_SSH_KEY)"; return 1; }
  # ServerAliveInterval matters: without it this tunnel dies mid-session and
  # every query starts failing with "connection refused" on a port that is
  # still, confusingly, bound.
  ssh -i "$SSH_KEY" -f -N -L "${DB_PORT}:localhost:5432" \
      -o ExitOnForwardFailure=yes -o ConnectTimeout=45 \
      -o ServerAliveInterval=15 -o ServerAliveCountMax=6 -o TCPKeepAlive=yes \
      "$SSH_HOST" || { red "tunnel failed (office networks block :22 intermittently)"; return 1; }
  sleep 2
  green "tunnel up on :${DB_PORT}"
}

# ------------------------------------------------------------------- api

# uvicorn runs here WITHOUT --reload, so an API left over from an earlier session
# keeps answering /health with the code it was started with. That failure is
# silent and reads exactly like a broken feature: the planner smoke reported
# "no utilisation artifact loaded" for a model that had been sitting on disk the
# whole time, because the process answering had been started before the service
# that loads it existed.
api_stale() {
  local stamp="$RUN_DIR/api.started"
  [ -f "$stamp" ] || return 0   # not started by this driver: assume stale
  [ -n "$(find "$ROOT/backend-ev-flow/api" -name '*.py' -newer "$stamp" -print -quit 2>/dev/null)" ]
}

api_up() {
  if curl -sf -o /dev/null --max-time 4 "http://127.0.0.1:${API_PORT}/health" 2>/dev/null; then
    if api_stale; then
      info "API is serving older code than the tree; restarting it"
      pkill -f "uvicorn api.main" 2>/dev/null
      sleep 1
    else
      green "API already up on :${API_PORT}"
      return 0
    fi
  fi
  cd "$ROOT/backend-ev-flow" || return 1
  [ -f .env ] || { red ".env missing; cp .env.example .env and set JWT_SECRET"; return 1; }
  # --env-file loads .env, but python-dotenv does NOT override variables that
  # are already exported, so the DATABASE_URL below wins over the file's.
  # Stamped before launch, not after: a file edited while uvicorn is booting is
  # not in the process that comes up, and must still count as newer.
  touch "$RUN_DIR/api.started"
  DATABASE_URL="${DATABASE_URL:-$DEFAULT_DB}" \
    nohup python3 -m uvicorn api.main:app --env-file .env \
      --host 127.0.0.1 --port "$API_PORT" >"$API_LOG" 2>&1 &
  for _ in $(seq 1 25); do
    curl -sf -o /dev/null --max-time 4 "http://127.0.0.1:${API_PORT}/health" 2>/dev/null && {
      check_api_sees_data "$(curl -s --max-time 5 "http://127.0.0.1:${API_PORT}/health")" || return 1
      return 0
    }
    sleep 2
  done
  red "API did not come up; tail of $API_LOG:"; tail -12 "$API_LOG"; return 1
}

# ------------------------------------------------------------------- web

web_up() {
  if curl -sf -o /dev/null --max-time 4 "http://localhost:${WEB_PORT}/" 2>/dev/null; then
    green "web already up on :${WEB_PORT}"
    return 0
  fi
  cd "$ROOT/frontend-evflow-app" || return 1
  [ -d node_modules ] || { info "installing node deps (first run only)"; npm ci || return 1; }
  # WITHOUT THIS the app talks to PRODUCTION. baseUrl.shared.ts defaults
  # DEFAULT_EVFLOW_API_BASE_URL to https://ev-flow.opensoft.id, which has no
  # planner endpoints (404) and is DNS-blocked on some office networks.
  # Vite reads .env from ITS OWN project root (apps/web), not the monorepo root,
  # which is why every VITE_ value the app needs is injected here rather than
  # left to frontend-evflow-app/.env. Starting `npm run web` by hand without
  # these gets you a login that fails with "String should have at least 8
  # characters", because VITE_DEMO_PASSWORD arrives empty.
  VITE_EVFLOW_API_BASE_URL="http://127.0.0.1:${API_PORT}" \
  VITE_DEMO_PASSWORD="$DEMO_PASSWORD" \
  VITE_TOMTOM_API_KEY="${VITE_TOMTOM_API_KEY:-$(grep -E '^VITE_TOMTOM_API_KEY=' "$ROOT/frontend-evflow-app/.env" 2>/dev/null | cut -d= -f2-)}" \
    nohup npm run web >"$WEB_LOG" 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf -o /dev/null --max-time 4 "http://localhost:${WEB_PORT}/" 2>/dev/null && {
      green "web up on http://localhost:${WEB_PORT}"
      return 0
    }
    sleep 2
  done
  red "web did not come up; tail of $WEB_LOG:"; tail -12 "$WEB_LOG"; return 1
}

# ----------------------------------------------------------------- smoke

smoke() {
  local base="http://127.0.0.1:${API_PORT}" fail=0
  local tok cell body

  tok=$(curl -s --max-time 20 -X POST "$base/api/v1/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"fleet.operator\",\"password\":\"$DEMO_PASSWORD\"}" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null)
  [ -n "$tok" ] || { red "planner login failed — is the DB the staging one?"; return 1; }
  green "logged in as fleet.operator (the only business_planner account)"

  local A="Authorization: Bearer $tok" J="Content-Type: application/json"
  local W='{"coverage":0.35,"population":0.35,"activity":0.2,"roads":0.1}'

  check() { # name expected_code actual_code
    if [ "$3" = "$2" ]; then printf "     %-38s %s\n" "$1" "$3"
    else printf "     %-38s %s (expected %s)\n" "$1" "$3" "$2"; fail=1; fi
  }

  check "GET  /planner/grid" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -H "$A" "$base/api/v1/planner/grid")"
  check "POST /planner/score" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 -H "$A" -H "$J" -d "$W" "$base/api/v1/planner/score")"
  check "POST /planner/candidates" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 -H "$A" -H "$J" -d "$W" "$base/api/v1/planner/candidates")"
  check "GET  /planner/cells.geojson" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 90 -H "$A" "$base/api/v1/planner/cells.geojson?bbox=106.62,-6.38,106.98,-6.06&metric=score&limit=500")"

  cell=$(curl -s --max-time 60 -H "$A" -H "$J" -d "$W" "$base/api/v1/planner/candidates" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin)["candidates"][0]["cell_id"])' 2>/dev/null)
  [ -n "$cell" ] || { red "no candidate returned; grid may be empty"; return 1; }
  info "top candidate: $cell"

  check "GET  /planner/cells/{id}" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 -H "$A" "$base/api/v1/planner/cells/$cell")"
  check "GET  /planner/benchmark/{id}" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 -H "$A" "$base/api/v1/planner/benchmark/$cell")"
  check "PUT  /planner/saved-sites/{id}" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 -X PUT -H "$A" "$base/api/v1/planner/saved-sites/$cell")"
  check "GET  /planner/saved-sites" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 -H "$A" "$base/api/v1/planner/saved-sites")"
  check "DEL  /planner/saved-sites/{id}" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 40 -X DELETE -H "$A" "$base/api/v1/planner/saved-sites/$cell")"

  # ROI is asserted on values, not just status. A site that does not break even
  # must return a NULL payback rather than the negative number capex/(rev-opex)
  # produces, and buying electricity must lengthen the payback rather than
  # leave it untouched.
  body=$(curl -s --max-time 40 -H "$A" -H "$J" "$base/api/v1/planner/roi" \
    -d "{\"cell_id\":\"$cell\",\"capex_per_connector_idr\":250000000,\"opex_monthly_idr\":15000000,\"utilisation_target\":0.2,\"energy_cost_idr_per_kwh\":1450}")
  python3 - "$body" <<'PY' || fail=1
import json, sys
d = json.loads(sys.argv[1])
pb, rev = d["payback_years"], d["revenue_monthly_idr"]
assert d["breaks_even"] is True and pb and pb > 5, f"expected a slow-but-positive payback, got {pb}"
assert d["energy_cost_monthly_idr"] > 0, "energy purchase cost was not applied"
assert isinstance(d["nearest_station_m"], (int, float, type(None))), "numeric field leaked as a string"
print(f"     {'POST /planner/roi':<38}200  payback {pb:.1f}y, revenue Rp{rev:,}")
PY

  body=$(curl -s --max-time 40 -H "$A" -H "$J" "$base/api/v1/planner/roi" \
    -d "{\"cell_id\":\"$cell\",\"capex_per_connector_idr\":250000000,\"opex_monthly_idr\":40000000,\"utilisation_target\":0.02}")
  python3 - "$body" <<'PY' || fail=1
import json, sys
d = json.loads(sys.argv[1])
assert d["payback_years"] is None and d["breaks_even"] is False, \
    f"a loss-making site must have no payback, got {d['payback_years']}"
assert d["net_at_horizon_idr"] < 0, "the loss must still be reported"
print(f"     {'POST /planner/roi (loss case)':<38}200  payback null, as it must be")
PY

  # The prescriptive model. That a number comes back is not the check: the whole
  # point of this model is that it can rank a cell nobody has built on, so what
  # is asserted is that the ORDER comes from it and that the scenario caveat
  # travels with it. If utilisation_model is null the API loaded no artifact and
  # is quietly answering with the descriptive model alone -- which ranks existing
  # stations first and looks entirely normal.
  body=$(curl -s --max-time 60 -H "$A" "$base/api/v1/planner/predict.area?lat=-6.175&lon=106.827&radius_km=3&top=50")
  python3 - "$body" <<'UTIL' || fail=1
import json, sys
d = json.loads(sys.argv[1])
m = d.get("utilisation_model")
assert m, "utilisation_model is null: no artifact loaded, so this is the descriptive model alone"
u = [p["sessions_per_connector_day"] for p in d["predictions"]]
assert u, "no predictions came back"
assert all(v is not None for v in u), "some cells returned without a utilisation prediction"
assert u == sorted(u, reverse=True), "predictions are not ordered by predicted utilisation"
assert "SCENARIO" in m["label"], "the scenario caveat is missing from the provenance"
print(f"     {'GET  /planner/predict.area':<38}200  top {u[0]:.2f} sessions/conn/day, "
      f"{m['window_days']}d window, dose-response {m['dose_response']:.2f}, "
      f"spec {m['reference_spec']['connectors']:.0f}x{m['reference_spec']['avg_kw']:.0f}kW")
UTIL

  # Rejections. These are the contract, not decoration.
  check "  reject unknown metric" 422 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "$A" "$base/api/v1/planner/cells.geojson?bbox=106.62,-6.38,106.98,-6.06&metric=nope")"
  check "  reject SQL in metric" 422 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "$A" --get --data-urlencode 'metric=population;DROP TABLE planning_cells' --data-urlencode 'bbox=106.62,-6.38,106.98,-6.06' "$base/api/v1/planner/cells.geojson")"
  check "  reject inverted bbox" 422 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "$A" "$base/api/v1/planner/cells.geojson?bbox=106.98,-6.38,106.62,-6.06")"
  check "  reject anonymous caller" 401 \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$base/api/v1/planner/grid")"

  [ "$fail" = 0 ] && green "planner smoke passed" || red "planner smoke FAILED"
  return "$fail"
}

# ---------------------------------------------------------------- status

# The API answers {"status":"ok"} with a dead database. The only tell is
# stations_loaded dropping to 0, and a plain HTTP-200 check sails straight past
# it: the dashboard then loads, logs in, and shows an empty map, while every
# request that touches Postgres returns a 500 the browser reports as CORS.
# Whoever hits that spends a while debugging the wrong layer. Ask for the count.
check_api_sees_data() {
  local health="$1"
  case "$health" in
    *'"stations_loaded":0'*)
      red "API  :${API_PORT} is answering but BLIND to the database — $health"
      red "     the tunnel died. Fix: $0 down && $0 up"
      return 1 ;;
    *) green "API  :${API_PORT} — $health" ;;
  esac
}

status() {
  # The PORT, not the process. An ssh that is still running but no longer
  # forwarding looks identical to a healthy one under pgrep, and that is exactly
  # the state this fell into: pgrep said the tunnel was up while :5433 refused
  # every connection.
  if (exec 3<>"/dev/tcp/127.0.0.1/${DB_PORT}") 2>/dev/null; then
    exec 3>&-; green "tunnel :${DB_PORT} -> staging db"
  else info "tunnel down"; fi
  local health
  health=$(curl -sf --max-time 4 "http://127.0.0.1:${API_PORT}/health" 2>/dev/null)
  if [ -n "$health" ]; then
    check_api_sees_data "$health"
  else info "API down"; fi
  curl -sf -o /dev/null --max-time 4 "http://localhost:${WEB_PORT}/" 2>/dev/null \
    && green "web  http://localhost:${WEB_PORT}" || info "web down"
}

down() {
  pkill -f "uvicorn api.main" 2>/dev/null && info "API stopped"
  pkill -f "vite" 2>/dev/null && info "web stopped"
  pkill -f "${DB_PORT}:localhost:5432" 2>/dev/null && info "tunnel closed"
  sleep 1; green "down"
}

case "${1:-up}" in
  up)     tunnel_up && api_up && web_up && { echo; status; echo; echo "  open http://localhost:${WEB_PORT} and pick 'Fleet Operator'"; } ;;
  smoke)  tunnel_up && api_up && { echo; smoke; } ;;
  status) status ;;
  down)   down ;;
  # Print the resolved connection string, so nothing has to scrape this file
  # with sed to find it. That scraping is what every ad-hoc command in this repo
  # was doing, and it broke the moment the literal became a ${VAR}.
  url)    echo "$DEFAULT_DB" ;;
  *)      echo "usage: $0 {up|smoke|status|down|url}"; exit 2 ;;
esac
