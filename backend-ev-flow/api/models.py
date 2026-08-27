"""Pydantic request and response models. These drive the OpenAPI (Swagger) schema."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from api.services import service_area

# Route-type vocabulary. Declared here (not in the ranker) so the request model
# can validate against it without importing a service that imports this module.
ROUTE_TYPE_FASTEST = "fastest"
ROUTE_TYPE_SHORTEST = "shortest"
SUPPORTED_ROUTE_TYPES = (ROUTE_TYPE_FASTEST, ROUTE_TYPE_SHORTEST)


class Source(str, Enum):
    pln_spklu = "pln_spklu"
    open_charge_map = "open_charge_map"
    osm = "osm"


class Connector(BaseModel):
    type: str = Field(..., description="Connector standard (inferred from power).", examples=["CCS2"])
    count: int = Field(..., description="Number of this connector at the station.", examples=[2])
    speed_tier: Optional[str] = Field(None, examples=["ultra_fast"])
    power_kw: Optional[float] = Field(None, examples=[200.0])
    type_inferred: bool = Field(True, description="True when the type is inferred from power, not source data.")


class StationConnector(BaseModel):
    """One physical connector (a real row, promoted from the stations JSONB)."""
    id: str = Field(..., description="Connector id (uuid).")
    station_id: str = Field(..., examples=["pln_spklu-1"])
    type: str = Field(..., examples=["CCS2"])
    power_kw: Optional[float] = Field(None, examples=[150.0])
    speed_tier: Optional[str] = Field(None, examples=["fast"])
    type_inferred: bool = Field(False, description="True when the type is inferred from power, not source data.")
    status: str = Field(..., description="available / in_use / out_of_service.", examples=["available"])
    updated_at: datetime


class StationAvailability(BaseModel):
    """Connector availability counts for one station."""
    station_id: str = Field(..., examples=["pln_spklu-1"])
    total: int = Field(..., examples=[4])
    available: int = Field(..., examples=[3])
    in_use: int = Field(..., examples=[1])
    out_of_service: int = Field(..., examples=[0])


class ConnectorStatusUpdate(BaseModel):
    status: str = Field(..., description="New connector status.",
                        examples=["available", "in_use", "out_of_service"])


class Station(BaseModel):
    id: str = Field(..., description="Stable unique id, '<source>-<n>'.", examples=["pln_spklu-1"])
    name: Optional[str] = Field(None, examples=["SPKLU PLN UID JAKARTA RAYA"])
    sources: list[Source] = Field(
        default_factory=list,
        description="Datasets this station appears in (deduplicated).",
        examples=[["pln_spklu", "open_charge_map"]])
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.18039])
    longitude: float = Field(..., ge=-180, le=180, examples=[106.833191])
    address: Optional[str] = Field(None, examples=["Jl. M.I. Ridwan Rais No.1, Gambir"])
    province: Optional[str] = Field(None, examples=["DKI Jakarta"])
    city: Optional[str] = Field(None, examples=["Kota ADM Jakarta Pusat"])
    operator: Optional[str] = Field(None, examples=["PLN"])
    power_kw: Optional[float] = Field(None, description="Peak power (kW).", examples=[22.0])
    charge_type: Optional[str] = Field(None, description="slow / medium / fast where known.", examples=["medium"])
    speed_tier: Optional[str] = Field(
        None, description="Speed bucket from power: slow / medium / fast / ultra_fast.", examples=["medium"])
    connectors: list[Connector] = Field(
        default_factory=list,
        description="Per-connector breakdown: type (inferred), real count/power/speed.")
    total_connectors: Optional[int] = Field(
        None, description="Physical connectors at this station, every status included.",
        examples=[8])
    available_connectors: Optional[int] = Field(
        None,
        description="Connectors free to plug into right now. Together with total_connectors "
                    "this is what colours a station pin on the map: 0 free means the driver "
                    "cannot charge here at all, which is a different answer from 'busy'.",
        examples=[3])
    connector_types: list[str] = Field(
        default_factory=list,
        description="Connector standards present, e.g. ['CCS2'] or ['AC Type 2']. Currently inferred.",
        examples=[["AC Type 2"]])
    connector_inferred: Optional[bool] = Field(
        None, description="True when connector_types are inferred from power, not from source data.",
        examples=[True])
    status: Optional[str] = Field(None, description="Operational status if reported.", examples=["operational"])
    date_verified: Optional[str] = Field(None, description="ISO timestamp last verified (OCM).")
    distance_km: Optional[float] = Field(None, description="Set only on /nearby results.", examples=[1.42])
    in_service_area: bool = Field(
        True,
        description="False when this station lies OUTSIDE the configured route service area, "
                    "i.e. POST /api/v1/route-plans would reject it as an origin or "
                    "destination. Computed from the station's own coordinates, so discovery "
                    "(/api/v1/stations, /api/v1/stations/nearby, /api/v1/geocoding/search) and "
                    "planning can never disagree. The station dataset is national while a "
                    "deployment's service area may be narrower.")

    @model_validator(mode="after")
    def _set_in_service_area(self) -> "Station":
        object.__setattr__(self, "in_service_area",
                           service_area.contains(self.latitude, self.longitude))
        return self


class StationList(BaseModel):
    total: int = Field(..., description="Total matching records (before pagination).", examples=[1142])
    limit: int = Field(..., examples=[100])
    offset: int = Field(..., examples=[0])
    items: list[Station]


class SourceCount(BaseModel):
    source: Source
    count: int


class NameCount(BaseModel):
    name: str = Field(..., examples=["DKI Jakarta"])
    count: int = Field(..., examples=[731])


class SpeedTier(BaseModel):
    """One charging-speed bucket with its power range + station count."""
    id: str = Field(..., examples=["fast"])
    label: str = Field(..., examples=["Fast"])
    min_kw: float = Field(..., description="Lower power bound (kW), inclusive.", examples=[50.0])
    max_kw: Optional[float] = Field(None, description="Upper power bound (kW); null for ultra_fast.", examples=[150.0])
    count: int = Field(..., description="Stations in this tier.", examples=[789])


class Stats(BaseModel):
    total: int = Field(..., examples=[3569])
    by_source: list[SourceCount]
    by_province: list[NameCount]
    by_charge_type: list[NameCount]
    with_power_kw: int = Field(..., description="Records that have a known power rating.")
    power_kw_min: Optional[float] = None
    power_kw_max: Optional[float] = None
    power_kw_mean: Optional[float] = None


class GeoJSONFeatureCollection(BaseModel):
    """RFC 7946 FeatureCollection. Drop straight into Leaflet or Mapbox."""
    type: str = Field("FeatureCollection", examples=["FeatureCollection"])
    features: list[dict[str, Any]]


class Health(BaseModel):
    """Liveness, and the two things that silently look like liveness.

    `status` was always "ok" as long as the process answered. Twice that hid a
    real outage. An SSH tunnel dropping leaves the API up with stations_loaded
    at 0, and the map renders empty behind a healthy-looking probe -- that shape
    cost nine rounds of debugging in one week. Separately, the deployed image
    carries no model artifact at all, so every planner ML endpoint answers 503
    while /health still says ok.

    So status is now "degraded" when the process is up but cannot do its job,
    and the two subsystems that can fail independently are reported separately.
    A caller that only reads status still gets a truthful answer.
    """
    status: str = Field(..., examples=["ok"],
                        description="'ok' only when the database and the models are both "
                                    "usable; 'degraded' when the process is up and one of "
                                    "them is not.")
    stations_loaded: int = Field(..., examples=[3569])
    version: str = Field(..., examples=["1.0.0"])
    models: dict[str, str] = Field(
        default_factory=dict,
        description="Per model: 'loaded', 'missing', or the reason it could not be read. "
                    "Missing is not fatal for the rest of the API, which is why it is "
                    "reported rather than raised.",
        examples=[{"siting": "loaded", "utilisation": "missing"}])


# ---- routing (Epic 2.0: shortest path via Dijkstra) -------------------------
class RouteGeometry(BaseModel):
    """GeoJSON LineString. Pass it to L.geoJSON() to draw the path on the map."""
    type: str = Field("LineString", examples=["LineString"])
    coordinates: list[list[float]] = Field(
        ..., description="Ordered [longitude, latitude] pairs (WGS84)."
    )


class RoutePoint(BaseModel):
    lat: float = Field(..., examples=[-6.2088])
    lon: float = Field(..., examples=[106.8456])
    snapped_node: str = Field(..., description="Nearest road-graph node the point was snapped to.")
    snap_distance_km: float = Field(..., description="Distance from the input point to the snapped node.")
    station_id: Optional[str] = Field(None, description="Set on the destination when routing to a station.")


class Route(BaseModel):
    """Shortest driving path between two points (Dijkstra over the road graph)."""
    weight: str = Field(..., description="Cost minimised: 'length' (metres) or 'travel_time' (seconds).",
                        examples=["length"])
    distance_m: float = Field(..., description="Total path length in metres.", examples=[4230.5])
    duration_s: float = Field(..., description="Estimated drive time in seconds.", examples=[540.2])
    origin: RoutePoint
    destination: RoutePoint
    node_count: int = Field(..., description="Number of road nodes in the path.", examples=[87])
    geometry: RouteGeometry


class NearestStationRoute(BaseModel):
    """Nearest charging station reachable by road + the route to it (Epic 2.0)."""
    station: Station = Field(..., description="The closest reachable station; its distance_km mirrors the road distance.")
    route: Route
    candidates_considered: int = Field(..., description="How many stations were reachable by road and ranked.",
                                       examples=[1142])
    within_range: bool = Field(True, description="False if the nearest station is beyond the EV's remaining range.")
    range_used_km: Optional[float] = Field(
        None, description="Remaining range (km) used for the within_range check: either the explicit "
                          "max_range_km, or derived from ev_model_id plus current_soc.", examples=[85.0])


# ---- EV model catalogue (Kaggle Indonesia-EV-2026; seed of Epic 6.0) --------
class EVModel(BaseModel):
    id: str = Field(..., examples=["wuling-air-ev"])
    brand: Optional[str] = Field(None, examples=["Wuling"])
    name: str = Field(..., examples=["Wuling Air EV"])
    make: Optional[str] = Field(None, examples=["Wuling"])
    model: Optional[str] = Field(None, examples=["Air EV"])
    battery_kwh: Optional[float] = Field(None, description="Usable battery capacity (kWh).", examples=[26.7])
    battery_kwh_min: Optional[float] = Field(None, examples=[26.7])
    battery_kwh_max: Optional[float] = Field(None, examples=[26.7])
    range_km: Optional[float] = Field(
        None, description="Manufacturer range (km); the lower bound where a range is given.", examples=[200.0])
    range_km_min: Optional[float] = Field(None, examples=[200.0])
    range_km_max: Optional[float] = Field(None, examples=[300.0])
    efficiency_wh_per_km: Optional[float] = Field(None, description="Efficiency (Wh/km).", examples=[133.5])
    efficiency_source: Optional[str] = Field(None, examples=["derived_local_specs"])
    max_dc_charge_kw: Optional[float] = Field(None, description="Max DC fast charge power (kW).", examples=[50.0])
    fast_charge_port: Optional[str] = Field(None, examples=["CCS2"])
    price_range: Optional[str] = Field(None, examples=["Rp 214 - 307,5 Juta"])
    charging_time_minutes: Optional[float] = Field(None, description="Charging time in minutes.", examples=[510.0])
    source_url: Optional[str] = Field(None)
    match_method: Optional[str] = Field(None, examples=["normalized_fuzzy_match"])
    match_confidence: Optional[float] = Field(None, examples=[0.85])


class EVModelList(BaseModel):
    total: int = Field(..., examples=[60])
    limit: int = Field(..., examples=[100])
    offset: int = Field(..., examples=[0])
    items: list[EVModel]



# ---- wallet / top-up (Epic 3.0: Xendit integration) -------------------------
class TopupRequest(BaseModel):
    amount_idr: int = Field(..., ge=10000, description="Top-up amount in IDR (Xendit min 10000).", examples=[50000])


class TopupCreated(BaseModel):
    topup_id: str
    amount_idr: int
    status: str = Field(..., examples=["pending"])
    invoice_url: str = Field(..., description="Open this hosted Xendit page to pay.")


class WalletBalance(BaseModel):
    balance_idr: int = Field(..., examples=[200000])
    currency: str = Field("IDR", examples=["IDR"])
    updated_at: datetime


class Topup(BaseModel):
    id: str
    external_id: str
    xendit_invoice_id: Optional[str] = None
    amount_idr: int
    status: str = Field(..., examples=["paid"])
    invoice_url: Optional[str] = None
    created_at: datetime
    paid_at: Optional[datetime] = None


# ---- charging sessions (Epic 4.0: real wallet debit + settlement) -----------
class ChargingQuoteRequest(BaseModel):
    energy_kwh: float = Field(..., gt=0, le=150, description="Requested energy in kWh.", examples=[20])


class ChargingQuote(BaseModel):
    energy_kwh: float
    base_rate_idr: int = Field(..., examples=[2466])
    admin_fee_idr: int = Field(..., examples=[2500])
    energy_cost_idr: int = Field(..., examples=[49320])
    total_due_idr: int = Field(..., description="Deposit charged at session start.", examples=[51820])
    currency: str = "IDR"


class StartSessionRequest(BaseModel):
    station_id: str = Field(..., examples=["pln_spklu-1"])
    energy_kwh: float = Field(..., gt=0, le=150, examples=[20])
    station_name: Optional[str] = Field(None, examples=["SPKLU PLN UID JAKARTA RAYA"])
    connector_type: Optional[str] = Field(None, examples=["CCS2"])
    power_kw: Optional[float] = Field(None, examples=[150])


class SettleRequest(BaseModel):
    delivered_kwh: float = Field(..., ge=0, le=500, description="Energy actually delivered (kWh).", examples=[16.5])


class ChargingSession(BaseModel):
    id: str
    station_id: str
    station_name: Optional[str] = None
    connector_type: Optional[str] = None
    power_kw: Optional[float] = None
    energy_kwh: float
    base_rate_idr: int
    admin_fee_idr: int
    deposit_idr: int
    delivered_kwh: Optional[float] = None
    actual_cost_idr: Optional[int] = None
    refund_idr: Optional[int] = None
    status: str = Field(..., examples=["active", "completed"])
    connector_id: Optional[str] = Field(
        None, description="Physical connector claimed for this session; null if none was available.")
    created_at: datetime
    completed_at: Optional[datetime] = None
    wallet_balance_idr: int = Field(..., description="Wallet balance after this operation.", examples=[198180])


# ---- authentication / accounts (Epic 5.0) ------------------------------------
def _validated_password(value: str) -> str:
    """Reject a password bcrypt cannot hash, at the boundary, in BYTES.

    A `max_length` on the field would count CHARACTERS; bcrypt's 72 limit counts
    UTF-8 BYTES. 72 accented characters passed a character check and then raised
    inside bcrypt, which surfaced as an unhandled 500 on the public,
    unauthenticated POST /api/v1/auth/register. Raising here instead makes it a
    422 that names the offending field.
    """
    from api import security

    problem = security.password_length_problem(value)
    if problem:
        raise ValueError(problem)
    return value


# `max_length` below is a published, client-usable hint only. It is NOT the real
# limit: JSON Schema cannot express "72 UTF-8 bytes", and 72 characters is always
# >= 72 bytes' worth, so it can only ever reject input the byte check rejects too.
# The authoritative check is _validated_password.
PASSWORD_MAX_CHARS_HINT = 72
_PASSWORD_BYTE_LIMIT_NOTE = (
    "Capped at 72 UTF-8 BYTES (bcrypt's limit), not 72 characters: accented and "
    "non-Latin characters cost more than one byte each, so a 40-character "
    "password can still be too long.")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, examples=["budi"])
    password: str = Field(..., min_length=8, max_length=PASSWORD_MAX_CHARS_HINT,
                          examples=["s3cret123"], description=_PASSWORD_BYTE_LIMIT_NOTE)
    email: Optional[str] = Field(None, examples=["budi@example.com"])
    full_name: Optional[str] = Field(None, examples=["Budi Santoso"])
    ev_model_id: Optional[str] = Field(None, examples=["hyundai-ioniq-5"])
    main_connector_type: Optional[str] = Field(None, examples=["CCS2"])
    location_consent: bool = False

    _check_password = field_validator("password")(_validated_password)


class LoginRequest(BaseModel):
    username: str
    # DELIBERATELY no length cap. Accounts created before the byte cap existed
    # may hold a hash of only the first 72 bytes of a longer password (older
    # bcrypt truncated silently); refusing the full password here would lock
    # those users out for good. security.verify_password truncates instead, so
    # such a login still succeeds and can never 500.
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., examples=["budi@example.com"])


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., examples=["k3y-from-the-emailed-link"])
    # bcrypt only uses the first 72 BYTES. max_length is kept as the published
    # client hint it always was; the real cap is the byte check below.
    new_password: str = Field(..., min_length=8, max_length=PASSWORD_MAX_CHARS_HINT,
                              examples=["n3ws3cret123"], description=_PASSWORD_BYTE_LIMIT_NOTE)

    _check_new_password = field_validator("new_password")(_validated_password)


class ResetPasswordResponse(BaseModel):
    message: str


class ProfileUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3)
    ev_model_id: Optional[str] = None
    main_connector_type: Optional[str] = None
    location_consent: Optional[bool] = None


class UserPublic(BaseModel):
    id: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    account_type: str = "ev_user"
    ev_model_id: Optional[str] = None
    main_connector_type: Optional[str] = None
    location_consent: bool = False
    profile_completed: bool = False
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ---- help desk / support ----------------------------------------------------
# Bounds are the point of these constants: this endpoint is reachable without a
# token and every accepted request costs one outbound email. Big enough for a
# real bug report with a pasted stack trace, small enough that nobody can push a
# megabyte through our SMTP relay one POST at a time.
SUPPORT_SUBJECT_MAX_CHARS = 200
SUPPORT_MESSAGE_MAX_CHARS = 5000
SUPPORT_REPLY_TO_MAX_CHARS = 254   # RFC 5321 cap on a forward-path address


def _validated_email_header_value(value: Optional[str]) -> Optional[str]:
    """Reject a value that would be smuggled into an email header.

    `subject` and `reply_to` are written into MIME headers. A carriage return or
    newline in either is the classic SMTP header-injection primitive: it ends the
    header and starts one the caller chose (Bcc:, say). Rejecting at the boundary
    is cheaper and clearer than sanitising downstream, and api/mailer.py refuses
    the same thing again as a belt.
    """
    if value is None:
        return None
    if any(ch in value for ch in ("\r", "\n")):
        raise ValueError("line breaks are not allowed here")
    return value


def _validated_reply_to(value: Optional[str]) -> Optional[str]:
    """A usable reply address, or None. Deliberately not a full RFC 5322 parser.

    The address is only ever handed back to a human in the support inbox, so the
    check that matters is the header-injection one above; beyond that we only
    insist it looks like an address at all, so an obvious typo is caught while
    the request is still in front of the user.
    """
    value = _validated_email_header_value(value)
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    local, _, domain = trimmed.partition("@")
    if not local or not domain or "." not in domain:
        raise ValueError("enter a valid email address")
    return trimmed


class SupportTicketRequest(BaseModel):
    """One Help Desk message, delivered to the support inbox by email."""
    subject: str = Field(..., min_length=3, max_length=SUPPORT_SUBJECT_MAX_CHARS,
                         description="What the ticket is about. Becomes the email subject line.",
                         examples=["Charging session stuck at 'starting'"])
    message: str = Field(..., min_length=10, max_length=SUPPORT_MESSAGE_MAX_CHARS,
                         description="The problem in full: what you did, what happened, "
                                     "and any station or session id involved.",
                         examples=["I started a session at pln_spklu-1 twenty minutes ago and "
                                   "the app still shows 'starting'. My wallet was debited."])
    reply_to: Optional[str] = Field(None, max_length=SUPPORT_REPLY_TO_MAX_CHARS,
                                    description="Where support should reply. Optional, but "
                                                "without it an anonymous ticket cannot be "
                                                "answered at all.",
                                    examples=["budi@example.com"])

    _check_subject = field_validator("subject")(_validated_email_header_value)
    _check_reply_to = field_validator("reply_to")(_validated_reply_to)


class SupportTicketResponse(BaseModel):
    """Confirmation that the ticket was handed to the mail server."""
    ticket_id: str = Field(..., description="Quote this when following up.",
                           examples=["4f9c2b1e7a0d4c8e"])
    message: str = Field(..., examples=["Your message has been sent to the EVFlow help desk."])


# ---- Epic 2.0 Route Planning & Geocoding Schemas ----------------------------
class RouteLocationInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.2088])
    longitude: float = Field(..., ge=-180, le=180, examples=[106.8456])
    label: Optional[str] = Field(None, examples=["Current Location"])


class RoutePreferencesInput(BaseModel):
    route_type: str = Field(
        ROUTE_TYPE_FASTEST,
        description="'fastest' balances detour against charging power; 'shortest' weights "
                    "detour distance harder. Applied to stop ranking and echoed in "
                    "assumptions.route_type (AC 2.2.4). Kept a free-form string rather than "
                    "an enum: this field shipped untyped, the web client declares it "
                    "`route_type?: string`, and turning an already-accepted request into a "
                    "422 would break it. An unrecognised value falls back to 'fastest' and "
                    "the value ACTUALLY applied comes back in assumptions.route_type, so a "
                    "client can detect the fallback without guessing.",
        examples=list(SUPPORTED_ROUTE_TYPES))
    maximum_detour_km: float = Field(8.0, ge=1.0, le=50.0, examples=[8.0])
    prefer_fast_charging: bool = Field(
        True,
        description="True rewards high available charging power when ranking stops; False "
                    "ranks on detour distance alone (AC 2.2.4).")

    @field_validator("route_type", mode="before")
    @classmethod
    def _known_route_type(cls, v: Any) -> str:
        """Accept the known values; degrade anything else to the default."""
        if not isinstance(v, str):
            return ROUTE_TYPE_FASTEST
        normalised = v.strip().lower()
        return normalised if normalised in SUPPORTED_ROUTE_TYPES else ROUTE_TYPE_FASTEST


class ManualVehicleInput(BaseModel):
    """A range entered by hand, for a driver with no saved vehicle profile (AC 2.2.3)."""
    usable_range_km: float = Field(
        ..., gt=0, le=2000,
        description="Remaining/usable range at 100% battery, in km.", examples=[350.0])
    battery_kwh: Optional[float] = Field(
        None, gt=0, le=500,
        description="Usable pack size. When omitted, one consistent with the entered range "
                    "and the configured default efficiency is assumed.", examples=[58.0])
    name: Optional[str] = Field(None, examples=["My EV"])
    max_dc_charge_kw: Optional[float] = Field(None, gt=0, le=1000, examples=[150.0])
    connector_type: Optional[str] = Field(None, examples=["CCS2"])


def _require_service_area(point: "RouteLocationInput") -> "RouteLocationInput":
    """AC 2.2.1 / AC 2.2.2: reject a point outside the configured route service area.

    Raised as a Pydantic ValueError so FastAPI answers 422 with
    ``detail[].loc == ["body", "origin"|"destination"|"current_position"]`` and
    the endpoint body never runs -- no route is generated.
    """
    if not service_area.contains(point.latitude, point.longitude):
        raise ValueError(service_area.rejection_message())
    return point


class RoutePlanRequest(BaseModel):
    origin: RouteLocationInput
    destination: RouteLocationInput
    current_soc_pct: float = Field(..., ge=0, le=100, examples=[72.0])
    ev_model_id: Optional[str] = Field(
        None,
        description="Plan for this catalogue vehicle instead of the saved profile (AC 2.2.3). "
                    "404 when unknown. Overridden by `vehicle`.",
        examples=["hyundai-ioniq-5"])
    vehicle: Optional[ManualVehicleInput] = Field(
        None,
        description="Manually entered vehicle range (AC 2.2.3). Takes precedence over "
                    "ev_model_id and over the saved profile, so a driver with no profile "
                    "can still simulate a trip.")
    minimum_arrival_soc_pct: Optional[float] = Field(
        None, ge=0, le=50, examples=[20.0],
        description="Minimum arrival battery. Defaults to the server reserve (20%, AC 2.1.3). "
                    "The enforced value may be raised so the reserve is worth at least "
                    "ROUTE_MIN_RESERVE_KM km; see assumptions.effective_reserve_soc_pct.")
    preferences: Optional[RoutePreferencesInput] = Field(default_factory=RoutePreferencesInput)
    waypoint_station_id: Optional[str] = Field(None, description="Optional station ID to force as a route waypoint.")
    max_candidate_stops: int = Field(
        5, ge=1, le=25,
        description="How many ranked alternative stops to return alongside the recommended one.")

    @field_validator("origin", "destination")
    @classmethod
    def _within_service_area(cls, v: RouteLocationInput) -> RouteLocationInput:
        return _require_service_area(v)


class VehicleSummary(BaseModel):
    id: str = Field(..., examples=["hyundai-ioniq-5"])
    name: str = Field(..., examples=["Hyundai Ioniq 5 Standard Range"])
    battery_kwh: float = Field(..., examples=[58.0])
    efficiency_wh_per_km: float = Field(..., examples=[160.0])
    efficiency_source: str = Field(..., examples=["dataset"])


class TripSummary(BaseModel):
    distance_km: float = Field(..., examples=[148.0])
    duration_minutes: float = Field(..., examples=[190.0])
    estimated_energy_kwh: float = Field(..., examples=[31.2])
    estimated_arrival_soc_pct: float = Field(..., examples=[12.0])
    minimum_arrival_soc_pct: float = Field(
        ..., description="The reserve actually enforced (effective, after the km floor).",
        examples=[20.0])
    requested_minimum_arrival_soc_pct: Optional[float] = Field(
        None, description="What the client asked for, before the km floor was applied.",
        examples=[20.0])
    effective_reserve_km: Optional[float] = Field(
        None, description="The enforced reserve expressed in km of range.", examples=[42.0])
    direct_arrival_soc_pct: Optional[float] = Field(
        None, description="Arrival SoC with NO charging stop, for the warning UI.", examples=[8.0])
    soc_margin_pct: Optional[float] = Field(
        None, description="Projected arrival SoC minus the enforced reserve.", examples=[3.0])
    computed_at: Optional[datetime] = Field(
        None,
        description="Server clock when this plan was computed (UTC). The reference point for "
                    "estimated_arrival_at, so two clients reading the same plan agree (AC 2.4.1).")
    estimated_arrival_at: Optional[datetime] = Field(
        None,
        description="Estimated arrival TIME (UTC) = computed_at + duration_minutes, charging "
                    "time included (AC 2.4.1).")

    @field_serializer("computed_at", "estimated_arrival_at")
    def serialize_route_time(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None


class RouteStep(BaseModel):
    """One turn-by-turn instruction (AC 2.4.1 'next instruction').

    Every field has a default so a provider that omits one still serialises, and
    so the legacy untyped `steps: []` payload keeps validating unchanged.
    """
    instruction: str = Field("", examples=["turn slight left"])
    name: str = Field("", description="Road name, may be empty.",
                      examples=["Jalan Medan Merdeka Utara"])
    distance_m: float = Field(0.0, examples=[782.5])
    duration_s: float = Field(0.0, examples=[45.6])
    location: list[float] = Field(default_factory=list,
                                  description="[longitude, latitude] where the manoeuvre starts.")
    leg_index: int = Field(
        0,
        description="Which leg this step belongs to. 0 is origin -> first waypoint, so the "
                    "charging stop is the boundary between leg 0 and leg 1.", examples=[0])


class RoutePlanGeometryAndSteps(BaseModel):
    type: str = Field("Feature", examples=["Feature"])
    geometry: RouteGeometry
    steps: list[RouteStep] = Field(default_factory=list)


class RecommendedStop(BaseModel):
    station: Station
    distance_from_origin_km: float = Field(..., examples=[82.0])
    distance_to_destination_km: Optional[float] = Field(None, examples=[66.0])
    detour_km: float = Field(..., examples=[2.1])
    distance_basis: str = Field(
        "straight_line",
        description="Measure every distance above shares: 'road' (routing provider) or "
                    "'straight_line'. Detour never mixes the two.",
        examples=["road", "straight_line"])
    arrival_soc_pct: float = Field(..., examples=[18.0])
    recommended_target_soc_pct: float = Field(
        ..., description="Charge target: 80% by default, raised only as far as the remaining leg needs.",
        examples=[80.0])
    required_target_soc_pct: Optional[float] = Field(
        None, description="Minimum SoC on departure that still finishes the trip with the reserve intact.",
        examples=[46.0])
    projected_destination_soc_pct: Optional[float] = Field(
        None, description="Projected SoC at the destination after charging here.", examples=[24.0])
    completes_trip: bool = Field(
        True, description="True when this stop provably gets the driver to the destination above the reserve. "
                          "Only a driver-forced waypoint can come back False.")
    blocking_reasons: list[str] = Field(
        default_factory=list,
        description="Why a driver-forced waypoint is not viable: 'unreachable', "
                    "'no_free_compatible_connector', 'cannot_complete_trip'. Always empty for a "
                    "stop the system recommended itself.",
        examples=[["unreachable"]])
    reserve_intact_on_arrival: bool = Field(
        True,
        description="True when the driver still holds the reserve on arriving HERE. False only in the "
                    "degraded case where no station at all is reachable with the reserve intact.")
    energy_to_add_kwh: float = Field(..., examples=[20.0])
    estimated_charging_minutes: float = Field(..., examples=[25.0])
    effective_charging_power_kw: float = Field(..., examples=[50.0])
    connector_compatible: bool = Field(True)
    matched_connector_type: Optional[str] = Field(
        None, description="The free connector type the vehicle will use here.", examples=["CCS2"])
    connector_match_inferred: bool = Field(
        False, description="True when the match relies on the assumed universal AC Type 2 inlet.")
    vehicle_connector_types: list[str] = Field(
        default_factory=list, description="Connector standards this vehicle was assumed to accept.",
        examples=[["CCS2", "AC Type 2"]])
    available_connector_count: int = Field(
        0, description="Free connectors of a type this vehicle can use (live `connectors` table).",
        examples=[2])
    available_connector_types: list[str] = Field(
        default_factory=list, description="All connector types with at least one free plug right now.")
    available_by_type: dict[str, int] = Field(
        default_factory=dict, description="Free connector count per type.", examples=[{"CCS2": 2}])
    total_connector_count: int = Field(0, description="All connector rows at this station.", examples=[4])
    best_available_power_kw: Optional[float] = Field(
        None, description="Highest power among the free connectors.", examples=[150.0])
    availability: str = Field("unknown", examples=["available_now", "unavailable", "unknown"])
    data_confidence: str = Field("medium", examples=["high", "medium", "low"])
    rank_score: float = Field(
        0.0, description="Deterministic rank score (detour km penalised, available power rewarded); lower is better.",
        examples=[1.4])
    detour_budget_km: Optional[float] = Field(
        None, description="The maximum_detour_km this stop was ranked against.", examples=[8.0])
    detour_within_budget: bool = Field(
        True,
        description="False when the ROAD detour finally reported exceeds detour_budget_km. "
                    "Only possible when nothing inside the budget was viable, or for a "
                    "driver-forced waypoint (AC 2.2.4).")


class ServiceAreaSummary(BaseModel):
    """The route service area the request was validated against (AC 2.2.1)."""
    name: str = Field(..., examples=["Indonesia (national SPKLU coverage)"])
    south: float = Field(..., examples=[-11.2])
    west: float = Field(..., examples=[94.6])
    north: float = Field(..., examples=[6.3])
    east: float = Field(..., examples=[141.3])
    enforced: bool = Field(True)


class RoutePlanAssumptions(BaseModel):
    reserve_soc_pct: float = Field(20.0, description="The reserve actually enforced.")
    requested_reserve_soc_pct: Optional[float] = Field(None)
    effective_reserve_km: Optional[float] = Field(None, examples=[42.0])
    minimum_reserve_km: Optional[float] = Field(None, examples=[15.0])
    distance_basis: str = Field("straight_line", examples=["road", "straight_line"])
    vehicle_connector_types: list[str] = Field(default_factory=list, examples=[["CCS2", "AC Type 2"]])
    connector_source: str = Field("default", examples=["ev_model", "user_profile", "default"])
    weather_applied: bool = Field(False)
    traffic_applied: bool = Field(False)
    connector_data_inferred: bool = Field(True)
    energy_model_version: str = Field("spec-v1")
    service_area: Optional[ServiceAreaSummary] = Field(
        None, description="The area origin/destination were validated against (AC 2.2.1).")
    route_type: Optional[str] = Field(
        None, description="The route_type preference actually applied.", examples=["fastest"])
    prefer_fast_charging: Optional[bool] = Field(
        None, description="The prefer_fast_charging preference actually applied (AC 2.2.4).")
    maximum_detour_km: Optional[float] = Field(
        None, description="The detour budget actually applied.", examples=[8.0])
    rank_detour_weight: Optional[float] = Field(
        None, description="Weight the applied preferences gave to detour km.", examples=[1.0])
    rank_power_weight_km_per_kw: Optional[float] = Field(
        None, description="Weight the applied preferences gave to available charging power.",
        examples=[0.25])
    routing_provider: Optional[str] = Field(
        None, description="Which provider produced the geometry: 'osrm', 'local_dijkstra' or "
                          "'haversine_fallback' (AC 2.4.1).", examples=["osrm"])
    turn_by_turn_available: bool = Field(
        False,
        description="False when the routing provider degraded and route.steps is a single "
                    "synthetic placeholder rather than real navigation instructions (AC 2.4.1).")


class RouteWarning(BaseModel):
    """AC 2.1.1 in-app warning payload."""
    triggered: bool = Field(..., examples=[True])
    code: str = Field(..., examples=["battery_below_reserve", "battery_margin_tight", "no_suitable_station"])
    severity: str = Field("warning", examples=["info", "warning", "critical"])
    message: str = Field(..., examples=["Battery will drop below your 20% reserve before you arrive."])
    projected_arrival_soc_pct: float = Field(..., examples=[8.0])
    reserve_soc_pct: float = Field(..., examples=[20.0])
    shortfall_soc_pct: float = Field(0.0, description="How far below the reserve the projection lands.", examples=[12.0])
    can_dismiss: bool = Field(True, description="AC 2.1.1 lets the driver dismiss and continue.")
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="Machine-readable remedies the client can render as buttons and localise, "
                    "instead of string-matching `message`. Vocabulary: "
                    "'choose_another_route', 'adjust_preferences', 'charge_before_departure' "
                    "(AC 2.2.6), 'return_to_service_area' (advisory only).",
        examples=[["choose_another_route", "adjust_preferences", "charge_before_departure"]])


class RoutePlanResponse(BaseModel):
    route_plan_id: str = Field(..., examples=["ephemeral-12345"])
    route_status: str = Field(
        "direct_route_available",
        description="'direct_route_available' (AC 2.1.2 green state, charging_stops is empty), "
                    "'charging_required' (AC 2.1.3), or 'no_suitable_station'.",
        examples=["direct_route_available", "charging_required", "no_suitable_station"])
    margin_is_tight: bool = Field(
        False,
        description="Arrival is above the reserve but within the tight margin. Still a DIRECT route "
                    "with no charging stops -- AC 2.1.2 continues to hold.")
    directly_reachable: bool = Field(..., examples=[False])
    vehicle: VehicleSummary
    summary: TripSummary
    route: RoutePlanGeometryAndSteps
    recommended_stop: Optional[RecommendedStop] = Field(
        None,
        description="The stop the SYSTEM recommends. Mirrors charging_stops[0] and is ALWAYS null "
                    "when route_status == 'direct_route_available' (AC 2.1.2). A stop the driver "
                    "forced via waypoint_station_id on an otherwise-direct route appears in "
                    "user_requested_stop instead.")
    charging_stops: list[RecommendedStop] = Field(
        default_factory=list,
        description="Ordered charging stops for this plan. ALWAYS empty when "
                    "route_status == 'direct_route_available' (AC 2.1.2).")
    user_requested_stop: Optional[RecommendedStop] = Field(
        None,
        description="The waypoint_station_id the driver asked for, honoured on a route that did not "
                    "need a charging stop. Never a system recommendation; check completes_trip and "
                    "blocking_reasons before relying on it.")
    alternative_stops: list[RecommendedStop] = Field(
        default_factory=list, description="Other viable stations the driver can pick instead.")
    warning: Optional[RouteWarning] = None
    assumptions: RoutePlanAssumptions = Field(default_factory=RoutePlanAssumptions)


# ---- AC 2.1.1: re-evaluating an ACTIVE route -------------------------------
class ActiveRouteEvaluationRequest(BaseModel):
    current_position: RouteLocationInput = Field(..., description="Where the driver is right now.")
    destination: RouteLocationInput
    current_soc_pct: Optional[float] = Field(
        None, ge=0, le=100,
        description="Legacy caller-supplied current SoC. Navigation clients should send "
                    "navigation_start_soc_pct and cumulative_distance_travelled_km instead.",
        examples=[26.0])
    navigation_start_soc_pct: Optional[float] = Field(None, ge=0, le=100, examples=[72.0])
    cumulative_distance_travelled_km: float = Field(0.0, ge=0, examples=[12.4])
    measured_current_soc_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Optional trusted vehicle telemetry reading.")
    minimum_arrival_soc_pct: Optional[float] = Field(None, ge=0, le=50, examples=[20.0])
    route_plan_id: Optional[str] = Field(None, description="Plan being driven, echoed back.")
    maximum_detour_km: float = Field(15.0, ge=1.0, le=50.0)
    max_candidate_stops: int = Field(5, ge=1, le=25)
    active_waypoint_station_id: Optional[str] = Field(
        None, description="Accepted charging stop that the remaining road route must preserve.")
    ev_model_id: Optional[str] = Field(
        None, description="Catalogue vehicle to evaluate against instead of the saved profile "
                          "(AC 2.2.3).", examples=["hyundai-ioniq-5"])
    vehicle: Optional[ManualVehicleInput] = Field(
        None, description="Manually entered vehicle range (AC 2.2.3). Takes precedence over "
                          "ev_model_id and over the saved profile.")

    # NOTE: deliberately NO service-area validator here, unlike RoutePlanRequest.
    # The planning-time boundary (AC 2.2.2) must not become a mid-journey kill
    # switch: AC 2.1.1 and AC 2.4.2 exist precisely to keep warning a driver who
    # is already travelling, and a driver on an active route may legitimately be
    # outside the box. The condition is reported on the RESPONSE instead --
    # out_of_service_area / out_of_service_area_fields / advisories.


class ActiveRouteEvaluationResponse(BaseModel):
    """What the in-app warning sheet needs (AC 2.1.1).

    'Add as a stop' and 'Dismiss' are client actions; the backend supplies the
    projection, the warning flag and the nearby stations to choose from.
    """
    route_plan_id: Optional[str] = None
    route_status: str = Field(..., examples=["direct_route_available", "charging_required", "no_suitable_station"])
    margin_is_tight: bool = Field(False)
    warning: Optional[RouteWarning] = None
    remaining_distance_km: float = Field(..., examples=[86.0])
    remaining_duration_minutes: float = Field(..., examples=[95.0])
    estimated_energy_kwh: float = Field(..., examples=[18.4])
    projected_arrival_soc_pct: float = Field(..., examples=[8.0])
    estimated_current_soc_pct: float = Field(..., examples=[61.2])
    current_soc_source: str = Field(..., examples=["distance_estimate", "vehicle_telemetry"])
    remaining_energy_kwh: float = Field(..., examples=[35.5])
    energy_model_version: str = Field("spec-v2")
    energy_assumptions: dict = Field(default_factory=dict)
    raw_projected_arrival_soc_pct: float = Field(..., examples=[8.2])
    reserve_soc_pct: float = Field(..., examples=[20.0])
    effective_reserve_km: Optional[float] = Field(None, examples=[42.0])
    distance_basis: str = Field("straight_line", examples=["road", "straight_line"])
    vehicle: VehicleSummary
    candidate_stops: list[RecommendedStop] = Field(
        default_factory=list,
        description="Nearby stations the driver could add as a stop, best first.")
    computed_at: Optional[datetime] = Field(
        None, description="Server clock when this evaluation ran (UTC) (AC 2.4.1).")
    estimated_arrival_at: Optional[datetime] = Field(
        None, description="Estimated arrival TIME (UTC) = computed_at + "
                          "remaining_duration_minutes (AC 2.4.1).")
    service_area: Optional[ServiceAreaSummary] = Field(
        None, description="The configured route service area this evaluation was measured "
                          "against (AC 2.2.1).")
    out_of_service_area: bool = Field(
        False,
        description="True when current_position and/or destination lies outside the "
                    "configured route service area. ADVISORY ONLY: unlike "
                    "POST /api/v1/route-plans, this endpoint keeps evaluating, because a "
                    "driver already on an active route must keep receiving battery warnings "
                    "(AC 2.1.1 / AC 2.4.2). Station coverage and ETA are unreliable while "
                    "this is true.")
    out_of_service_area_fields: list[str] = Field(
        default_factory=list,
        description="Which request fields fell outside: any of 'current_position', "
                    "'destination'. Empty when out_of_service_area is false.",
        examples=[["current_position"]])
    advisories: list[RouteWarning] = Field(
        default_factory=list,
        description="Non-blocking notices that do not displace `warning` (which stays "
                    "reserved for the battery projection). Carries the "
                    "'out_of_service_area' notice and the 'routing_degraded' notice "
                    "(road routing was unavailable, so distance/ETA are a straight-line "
                    "approximation -- see assumptions.routing_provider). Both can be "
                    "present alongside a triggered battery `warning`.")
    assumptions: RoutePlanAssumptions = Field(
        default_factory=RoutePlanAssumptions,
        description="Same shape POST /api/v1/route-plans returns, so a client can read "
                    "routing_provider / turn_by_turn_available / distance_basis the same "
                    "way on both endpoints. Additive: no pre-existing field changed.")

    @field_serializer("computed_at", "estimated_arrival_at")
    def serialize_route_time(self, value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None


DISTANCE_FROM_ORIGIN = "origin"
DISTANCE_FROM_REFERENCE_POINT = "reference_point"


class GeocodingItem(BaseModel):
    id: str = Field(..., examples=["place-1"])
    label: str = Field(..., examples=["Bandung"])
    subtitle: str = Field(..., examples=["West Java · via Tol Cipularang"])
    latitude: float = Field(..., ge=-90, le=90, examples=[-6.9175])
    longitude: float = Field(..., ge=-180, le=180, examples=[107.6191])
    distance_km: Optional[float] = Field(
        None,
        description="Distance from the caller's OWN position, and null when the caller sent "
                    "none. This meaning is deliberately unchanged: a client that renders it as "
                    "'distance from you' stays correct, and never silently shows a distance "
                    "measured from somewhere the user has never been.",
        examples=[148.0])
    distance_from_reference_km: Optional[float] = Field(
        None,
        description="AC 2.2.7 estimate for the no-GPS-fix case, measured from the configured "
                    "reference point named in distance_reference_label. Populated only when "
                    "distance_km is null, so a client must label it ('~X km from Jakarta') "
                    "rather than present it as the user's own distance.",
        examples=[148.0])
    distance_from: str = Field(
        DISTANCE_FROM_ORIGIN,
        description="Which of the two distance fields is populated: 'origin' -> distance_km, "
                    "'reference_point' -> distance_from_reference_km (AC 2.2.7).",
        examples=["origin", "reference_point"])
    distance_reference_label: Optional[str] = Field(
        None,
        description="Name of the reference point when distance_from == 'reference_point', so "
                    "the picker can say '~X km from Jakarta'.", examples=["Jakarta"])

    @model_validator(mode="after")
    def _reference_distance_never_poses_as_the_users_own(self):
        """Keep distance_km meaning exactly what it meant before AC 2.2.7 landed.

        The fallback estimate is real and useful, but it is measured from a fixed
        reference point, not from the driver. Serving it in distance_km would make
        an unmodified client display a confident, wrong 'distance from you'. So it
        moves to its own field and distance_km goes back to null.
        """
        if self.distance_from == DISTANCE_FROM_REFERENCE_POINT and self.distance_km is not None:
            self.distance_from_reference_km = self.distance_km
            self.distance_km = None
        return self
    type: str = Field(..., description="'place' or 'station'", examples=["place"])
    station: Optional[Station] = None
    attribution: str = Field("OpenStreetMap contributors, PLN SPKLU")
    in_service_area: bool = Field(
        True,
        description="False when picking this suggestion as an origin or destination would be "
                    "REJECTED by POST /api/v1/route-plans with a 422 (AC 2.2.2). The picker "
                    "must label or disable such an entry rather than offering it as routable; "
                    "pass ?in_service_area_only=true to have the server drop them instead. "
                    "Computed from the suggestion's own coordinates against the same "
                    "configured area the planner uses, so the two can never disagree.")

    @model_validator(mode="after")
    def _set_in_service_area(self) -> "GeocodingItem":
        object.__setattr__(self, "in_service_area",
                           service_area.contains(self.latitude, self.longitude))
        return self


class GeocodingSearchResponse(BaseModel):
    query: str
    items: list[GeocodingItem]
    distance_from: str = Field(
        DISTANCE_FROM_ORIGIN,
        description="Applies to every item: 'origin' or 'reference_point' (AC 2.2.7).",
        examples=["origin", "reference_point"])
    distance_reference_label: Optional[str] = Field(None, examples=["Jakarta"])
    service_area: Optional[ServiceAreaSummary] = Field(
        None,
        description="The configured route service area every item's `in_service_area` was "
                    "computed against -- the SAME area POST /api/v1/route-plans enforces, so "
                    "the picker can explain why a suggestion is not routable (AC 2.2.1).")
    filtered_out_of_service_area: int = Field(
        0,
        description="How many otherwise-matching suggestions were dropped because "
                    "in_service_area_only=true. Always 0 when the flag is off.",
        examples=[0])


# <Aidil> 2026-07-29
class StationConnectorStatus(BaseModel):
    """Live counts for one group of interchangeable connectors at a station.

    A group is one (type, speed_tier, power_kw) combination, so power_kw is part of the
    group's identity: two groups can share type and speed_tier and differ only in power.
    """
    type: str = Field(..., description="Connector standard/type.", examples=["CCS2"])
    speed_tier: Optional[str] = Field(
        None, description="Connector speed tier: slow / medium / fast / ultra_fast.", examples=["fast"])
    power_kw: Optional[float] = Field(
        None,
        description="Rated power (kW) every connector in this group delivers. Two groups with the same "
                    "type and speed_tier are told apart by this value, so show it. Null when the source "
                    "data never reported a power for these connectors.",
        examples=[50.0])
    available: int = Field(
        ..., description="Connectors in this group free to plug into right now.", examples=[2])
    total: int = Field(
        ...,
        description="Connectors in this group, every status included. "
                    "Always equals available + in_use + out_of_service.",
        examples=[5])
    in_use: int = Field(
        ..., description="Connectors in this group busy with an active charging session.", examples=[2])
    out_of_service: int = Field(
        ...,
        description="Connectors in this group that are broken or offline. Present them as unusable, never "
                    "as busy: they are not going to free up, so do not fold them into an occupied count "
                    "derived from total - available.",
        examples=[1])
    waiting_time: Optional[float] = Field(
        ...,
        description="Minutes until a connector in this group is expected to free up. 0 = at least one is "
                    "free right now. A positive number = none free, and this is the estimate from the "
                    "active session finishing soonest. Null = UNKNOWN: none free and no estimate can be "
                    "computed (no active session on record, missing power, ...). Null must never be "
                    "rendered as '~0 minutes' -- say the wait is unknown.",
        examples=[0, 12.4, None])

class StationStatusResponse(BaseModel):
    station_id: str = Field(..., description="ID of the station.", examples=["pln_spklu-1"])
    station_status: int = Field(
        ...,
        description="Whole-station availability flag: 1 = at least one connector is free to plug into "
                    "right now, 0 = none is (all connectors in use or out of service, or the station has "
                    "no connectors on record).",
        examples=[1])
    available: int = Field(
        ..., description="Connectors free to plug into right now across the whole station.", examples=[3])
    total: int = Field(
        ...,
        description="Connectors at the station, every status included. "
                    "Always equals available + in_use + out_of_service.",
        examples=[8])
    in_use: int = Field(
        ..., description="Connectors at the station busy with an active charging session.", examples=[4])
    out_of_service: int = Field(
        ...,
        description="Connectors at the station that are broken or offline. Exposed so the client stops "
                    "inferring occupancy as total - available, which reported a broken charger as busy.",
        examples=[1])
    waiting_time: Optional[float] = Field(
        ...,
        description="Minutes until any connector at the station is expected to free up. 0 = at least one "
                    "is free right now. A positive number = none free, and this is the soonest estimate "
                    "across the station. Null = UNKNOWN: none free and no estimate can be computed. Null "
                    "must never be rendered as '~0 minutes' -- say the wait is unknown.",
        examples=[0, 12.4, None])
    connectors: list[StationConnectorStatus] = Field(
        ...,
        description="Per-group breakdown of the same counts, one entry per "
                    "(type, speed_tier, power_kw) combination.")

class StationOccupancyHour(BaseModel):
    hour_of_day: int = Field(
        ..., description="Hour of day, 0 to 23, in Asia/Jakarta (UTC+7). Local rather than UTC "
                         "because the reader is a driver deciding when to go, and the two differ "
                         "by seven hours here.",
        examples=[14])
    avg_occupancy: float = Field(
        ..., description="Average share of the station's connectors busy in this hour, percent (0-100).",
        examples=[45.5])
    occupancy_level: str = Field(
        ...,
        description="How busy this hour is, classified server-side from avg_occupancy at the 20 / 50 / 80 "
                    "percent thresholds: 'LOW', 'MODERATE', 'BUSY', 'PEAK'. Display this rather than "
                    "re-deriving the buckets, so client labels cannot drift from the backend's.",
        examples=["MODERATE"])

class StationOccupancyDay(BaseModel):
    day_of_week: int = Field(
        ..., description="Day of week, 1=Monday to 7=Sunday, in Asia/Jakarta. The day rolls over on "
                         "the local boundary, so a session at 02:00 Monday in Jakarta is Monday here "
                         "even though UTC still calls it Sunday.",
        examples=[1])
    day_name: str = Field(..., description="Day name.", examples=["Monday"])
    hours: list[StationOccupancyHour]

class StationOccupancyResponse(BaseModel):
    station_id: str = Field(..., description="ID of the station.", examples=["pln_spklu-6"])
    days: list[StationOccupancyDay]
# </Aidil> 2026-07-29


# --- Planner surface (Epic 4 / Epic 5) ---------------------------------------
# Weights arrive from the dashboard, so they are request input and validated as
# such. `ge=0` blocks a negative weight at the schema boundary; a negative weight
# inverts a feature's meaning and would recommend places BECAUSE they are already
# well served. The all-zero case cannot be expressed as a field rule and is
# rejected in api/services/site_scoring.py.
class SiteWeightsInput(BaseModel):
    coverage: float = Field(0.35, ge=0, le=100,
                            description="How much an area being far from any existing station counts.")
    population: float = Field(0.35, ge=0, le=100, description="How much resident population counts.")
    activity: float = Field(0.20, ge=0, le=100,
                            description="How much surrounding activity counts (17 point-of-interest categories).")
    roads: float = Field(0.10, ge=0, le=100, description="How much road connectivity counts.")


class PlannerCellScore(BaseModel):
    cell_id: str = Field(..., examples=["JBDTBK_13989"])
    kota: Optional[str] = Field(None, examples=["Kota Jakarta Selatan"])
    score: float = Field(..., description="0..1 under the submitted weights. Not comparable across weight sets.",
                         examples=[0.8421])
    latitude: float
    longitude: float
    population: float = Field(..., description="WorldPop 2026 constrained. A projection, not a census count.")
    poi_total: int
    road_nodes: int
    station_count: int
    connector_count: int
    nearest_station_m: Optional[float] = Field(None, description="Metres from the cell centre to the nearest station.")
    stations_2km: int


class PlannerCandidate(BaseModel):
    cluster_id: int
    cell_id: str
    kota: Optional[str] = None
    score: float
    latitude: float
    longitude: float
    population: float
    poi_total: int
    station_count: int
    nearest_station_m: Optional[float] = None
    stations_2km: int
    cluster_size: int = Field(..., description="How many qualifying cells this suggestion stands for.")

    #: Present only under basis="suitability". The three fields are kept apart on
    #: purpose: `score` is what ranked the pin, and these say what it was made of,
    #: so "the model chose this" can be checked rather than taken on trust.
    suitability_band: Optional[str] = None
    sessions_per_connector_day: Optional[float] = Field(
        None, description="SCENARIO, not a forecast: predicted from simulated sessions.")
    supply_discount: Optional[float] = Field(
        None, description="1/(1+effective stations within 2 km). 1.0 means nothing nearby.")


class PlannerProvenance(BaseModel):
    """What the numbers rest on. Carried in every response, not only in the UI.

    Two of these inputs are not measurements: population is a projection, and any
    figure derived from charging sessions currently comes from a simulation. A
    consumer that shows one without the other is presenting invented data as fact.
    """
    population_source: str = "WorldPop 2026 constrained, release R2025A (projection, not a census count)"
    features_source: str = "OpenStreetMap via Geofabrik Java extract, snapshot 2026-08-14 (ODbL)"
    #: This said "no charging-session data is used" until suitability shipped, at
    #: which point it became false for every response carrying a band. Both halves
    #: are stated because both are served: a consumer that reads only the first
    #: sentence would present a simulation as observed demand.
    demand_basis: str = (
        "The four-criteria score uses coverage and surroundings only, with no "
        "charging-session data. Any suitability, band or sessions-per-connector "
        "figure is predicted from SIMULATED sessions: a scenario that recovers an "
        "assumption about demand, not a forecast and not observed usage.")
    cell_size_m: int = 500


class PlannerScoreResponse(BaseModel):
    weights_applied: dict[str, float] = Field(..., description="Rescaled to sum to 1.")
    cells_considered: int
    cells: list[PlannerCellScore]
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerCandidatesResponse(BaseModel):
    weights_applied: dict[str, float]
    candidates: list[PlannerCandidate]
    basis: str = Field(
        "weighted",
        description="Which number ranked these. 'weighted' is the adjustable four-criteria "
                    "score; 'suitability' is the model-and-supply number the heatmap paints. "
                    "A request for 'suitability' answers 'weighted' when the model is "
                    "unavailable, so read this rather than assuming what was asked for.")
    excluded_areas: list[str] = Field(
        ..., description="Areas held out of the candidate pool, e.g. sea-separated cells unreachable by road.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerSavedSiteStatus(BaseModel):
    cell_id: str
    saved: bool


class PlannerSavedSite(BaseModel):
    cell_id: str
    kota: Optional[str] = None
    latitude: float
    longitude: float
    score: Optional[float] = None
    poi_total: int
    nearest_station_m: Optional[float] = None
    road_nodes: int
    lu_residential_share: float
    saved_at: datetime


class PlannerSavedSitesResponse(BaseModel):
    items: list[PlannerSavedSite]
    total: int


class PlannerCellDetail(BaseModel):
    cell_id: str
    kota: Optional[str] = None
    latitude: float
    longitude: float
    score: Optional[float] = Field(
        None, description="Null when the cell is outside the scored set; see in_scored_set.")
    rank_overall: Optional[int] = Field(
        None, description="1 is the highest scoring cell under the default weights. Null when unranked.")
    cells_total: int = Field(..., description="Size of the set the rank is taken within.")
    in_scored_set: bool = Field(
        True, description="False for a cell the filter excludes, which is shown but not ranked.")
    overlap_frac: Optional[float] = Field(
        None, description="Share of the cell inside the administrative outline. Edge cells are partial.")
    population: float
    poi: dict[str, int] = Field(..., description="Counts for the 17 point-of-interest categories, plus a total.")
    land_use: dict[str, float] = Field(
        ..., description="Share of the cell each class covers, 0..1 per class. These are "
                         "independent coverages, not a partition: OpenStreetMap maps "
                         "overlapping polygons of different classes over the same ground, "
                         "so the four can sum above 1 (657 of 28,176 cells do, up to 2.19). "
                         "The remainder of a cell is unmapped, not necessarily empty.")
    road_nodes: int
    road_length_m: float
    station_count: int
    connector_count: int
    nearest_station_m: Optional[float] = None
    stations_2km: int
    provenance: PlannerProvenance = PlannerProvenance()

    #: The same number the heatmap paints, so "Located in a Red Demand Zone" on
    #: the card and the colour under the cursor are one claim rather than two
    #: expressions that happened to agree. Absent when no scale could be built --
    #: a card with no band is correct, a card with a plausible wrong band is not.
    suitability: Optional[float] = None
    suitability_band: Optional[str] = None
    sessions_per_connector_day: Optional[float] = Field(
        None, description="SCENARIO, not a forecast: predicted from simulated sessions.")
    supply_discount: Optional[float] = None
    suitability_scale: Optional[dict[str, float]] = Field(
        None, description="The regional distribution this cell was read against.")

class PlannerPoisGeoJSON(BaseModel):
    """RFC 7946 FeatureCollection of POI points, for the map's marker layer.

    These are the same features the grid's poi_* columns count, so a marker and
    the activity figure beside it never describe different things.

    Coordinates are GeoJSON order, longitude before latitude. Leaflet's marker
    constructor takes latitude first, so a Leaflet client has to swap them.
    """
    type: str = Field("FeatureCollection", examples=["FeatureCollection"])
    features: list[dict[str, Any]]
    categories: list[str] = Field(..., description="Which categories this response covers.")
    mode: str = Field(
        ..., description="'points' when every POI in the viewport is returned individually; "
                         "'clustered' when there were too many to draw and they have been "
                         "grouped on a grid instead. In clustered mode each feature carries a "
                         "`count`, and those counts sum to the viewport total: the layer is "
                         "aggregated, never truncated. Zooming in returns it to 'points'.")
    pois_returned: int = Field(
        ..., description="Features in this response. In clustered mode this is the number of "
                         "GROUPS, not of POIs; read pois_in_viewport for the POI total.")
    pois_in_viewport: dict[str, int] = Field(
        ..., description="Per-category POI totals for the viewport, independent of mode. "
                         "This is the honest denominator for anything shown on the map.")
    truncated: bool = Field(
        ..., description="True only if the limit still bit after clustering, which needs an "
                         "extraordinarily dense viewport. Normal zoomed-out views cluster "
                         "instead of truncating.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerModelInfo(BaseModel):
    """What model produced a prediction, and how far it can be trusted.

    Carried in every prediction response. `loco_auc` is the number worth
    quoting; `random_split_auc` is reported beside it precisely because it is
    higher and misleading, and omitting it invites someone to rediscover the
    flattering figure and use it.
    """
    trained_at: str
    n_samples: int
    n_positive: int
    loco_auc: float = Field(
        ..., description="Leave-one-area-out AUC. The honest figure: it holds out a whole "
                         "kota, which is the question a planner actually asks.")
    random_split_auc: float = Field(
        ..., description="Inflated. Neighbouring cells land on both sides of a random split, "
                         "so the model recalls nearby answers rather than generalising.")
    label: str
    sklearn_version: str
    n_features: int


#: The classes the map draws, in the priority order that resolved them. Kept
#: beside the schema rather than in the endpoint so the response model, the
#: validation and the OpenAPI description cannot list different sets.
LANDUSE_CLASSES = ("retail", "commercial", "industrial", "residential")


class PlannerLandUseFeature(BaseModel):
    """One land-use polygon, as drawn.

    Not a cell and not a share. planning_cells carries lu_*_share -- how much of
    a 500 m square each class covers -- which is a model feature and a poor map:
    a city block and the road beside it come out the same colour. This is the
    shape the share was measured from.
    """
    landuse: str = Field(
        ..., description=f"One of: {', '.join(LANDUSE_CLASSES)}. Classes never overlap: "
                         "every square metre belongs to exactly one, the most specific that "
                         "claims it, so drawing order cannot change what is seen.")
    geojson: str = Field(
        ..., description="Polygon geometry as a GeoJSON string, WGS84. A string rather than "
                         "a parsed object: it is passed straight to the map, and parsing it "
                         "twice on the way through buys nothing.")
    area_m2: float = Field(..., description="Ground area in square metres.")


class PlannerLandUseResponse(BaseModel):
    """Land-use polygons for a viewport, with what the limit left out.

    `polygons_in_viewport` is counted before the limit for the same reason the
    cell layers report theirs: a client that cannot tell a complete layer from a
    truncated one will present a partial map as the whole picture, and land use
    is the layer where that is least visible -- missing polygons look like
    unclassified ground, which is a real and common state here.
    """
    features: list[PlannerLandUseFeature]
    polygons_returned: int
    polygons_in_viewport: int
    truncated: bool = Field(
        ..., description="True when the viewport held more polygons than the limit returned. "
                         "The smallest are dropped first, never a geographic slice.")
    classes: list[str] = Field(..., description="Classes present in this response.")
    coverage_note: str = Field(
        ..., description="How much of the ground is classified at all. OSM land use in "
                         "Jabodetabek is patchy, and blank ground means 'not mapped', not "
                         "'nothing there'. Stated in the response because a map cannot show "
                         "the difference.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerUtilisationInfo(BaseModel):
    """Provenance for the prescriptive model, which answers a different question.

    PlannerModelInfo above describes the DESCRIPTIVE model: it scores how much a
    cell resembles the ones that already hold a station, and its 500 highest
    cells are 100% cells that already do. This one predicts how busy a connector
    at a place would be, which is the only one of the two that can rank a cell
    nobody has built on.

    Every field here exists because the number it qualifies would be read as a
    measurement otherwise. It is not one. The sessions it learned from are
    simulation output, and that simulation distributes demand by a formula we
    wrote: 0.53*rank(population) + 0.30*rank(poi_total) + 0.17*rank(road_nodes).
    The model recovers that assumption rather than discovering demand.
    """
    trained_at: str
    n_samples: int
    loco_r2: float = Field(
        ..., description="Leave-one-area-out R2 on the training target, hardware variation "
                         "included. Do NOT read it as place-ranking skill: 57% of the "
                         "model's importance is charger power, which is held constant when "
                         "cells are compared. The spread across the grid is the figure that "
                         "speaks to ranking, and it is 1.66x against the simulation's 1.64x.")
    random_split_r2: float = Field(
        ..., description="Inflated, and reported for the same reason as the siting model's: "
                         "neighbouring cells land on both sides of a random split.")
    label: str
    target_units: str
    sklearn_version: str
    n_features: int
    reference_spec: dict[str, float] = Field(
        ..., description="The hardware every cell is scored at, so differences between cells "
                         "are location and nothing else. Sessions per connector depend "
                         "heavily on charger power; comparing cells at different specs "
                         "compares the chargers, not the places.")
    window_start: str
    window_end: str
    window_days: int = Field(
        ..., description="Complete local days of demand-weighted simulation behind this fit. "
                         "Short windows are noisy; the window grows nightly and the model "
                         "should be retrained as it does.")
    dose_response: float = Field(
        ..., description="Measured ratio of sessions per connector between the top and bottom "
                         "demand-factor quartile in that window. This is the evidence the "
                         "weighting actually reached the sessions the model learned from; "
                         "around 1.0 would mean it did not.")
    counting_noise_pct: Optional[float] = Field(
        None, description="Poisson noise on a typical cell's rate, 1/sqrt(sessions). It "
                          "attenuates the score rather than inflating it, so it makes a "
                          "positive result conservative, not suspect.")


class PlannerPrediction(BaseModel):
    cell_id: str
    kota: Optional[str] = None
    probability: float = Field(
        ..., description="P(this cell contains a station) under the trained model.")
    has_station: bool = Field(
        False, description="Whether this cell ALREADY holds a station. Measured on the full "
                           "grid, the model's 500 highest-probability cells are 100% cells "
                           "that already have one, so a client that cannot tell the two apart "
                           "will present existing sites as candidates.")
    suitability: Optional[float] = Field(
        None, ge=0, le=1,
        description="How suitable this cell is, 0..1, as a percentile of the whole scored "
                    "region. A blend of the model's demand prediction and a penalty for "
                    "existing supply nearby, weighted 50/50 over their ranks. Multiplying "
                    "the two was measured and rejected: demand and supply are negatively "
                    "correlated here, so the product ranked at -0.036 against the model. "
                    "Null when no utilisation artifact is loaded.")
    suitability_band: Optional[str] = Field(
        None, description="'red' (top decile of the region), 'yellow' (above the median) or "
                          "'green'. Bands are quantiles of the live distribution, not fixed "
                          "values, so a retrain moves them rather than leaving a stale "
                          "threshold. Read red as 'top 10% of Jabodetabek', never as 'high "
                          "demand' -- a quantile band cannot say a place is good in absolute "
                          "terms, only that it is the best available here.")
    supply_discount: Optional[float] = Field(
        None, description="1/(1+competing stations within 2 km), counting a station in the "
                          "same car park as more than one at the rim. Returned separately so "
                          "the blend is auditable rather than a single opaque number.")
    stations_2km: Optional[int] = Field(
        None, description="Stations within 2 km. Counts STATIONS, not connectors: ten "
                          "single-connector sites and one ten-connector site are the same "
                          "number here, which is a known limit of the supply term.")
    sessions_per_connector_day: Optional[float] = Field(
        None, description="Prescriptive model: simulated sessions a connector here would "
                          "turn over per day, at the reference spec in "
                          "PlannerUtilisationInfo. A SCENARIO recovered from the "
                          "simulation's demand assumption, not a forecast. Null when no "
                          "utilisation artifact is loaded, and a client that gets null must "
                          "say so rather than fall back to the resemblance figure, which "
                          "answers a different question.")


class PlannerPredictResponse(BaseModel):
    """Model predictions, with the caveat that has to travel with them.

    The model learns where stations ARE. Measured 2026-08-26, 1,038 of the 1,192
    stations inside the scored grid are operated by PLN, 87%, so a high
    probability means "this looks like somewhere the dominant operator builds",
    which is not the same claim as "this is a good site". Read it next to the
    weighted score rather than instead of it.
    """
    predictions: list[PlannerPrediction]
    model: PlannerModelInfo
    utilisation_model: Optional[PlannerUtilisationInfo] = Field(
        None, description="Provenance for sessions_per_connector_day. Null when no "
                          "utilisation artifact is loaded, in which case every prediction's "
                          "utilisation field is null too.")
    interpretation: str = Field(
        ..., description="What a high probability does and does not mean.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerAreaDistribution(BaseModel):
    """How the model's probabilities fall across an area, split by what is already there.

    THERE IS NO SINGLE AREA PROBABILITY, AND NO "ABOVE 0.5" COUNT.

    Both were in an earlier version of this response and both were wrong.

    A single area score is wrong because the model was fitted on 500 m cells:
    summing a 10 x 10 km selection into one feature vector puts 17 of its 33
    additive features past anything in the training set -- road_length_m by 48x --
    where a random forest
    can only repeat its most extreme leaves. It answered 0.605 where the true
    per-cell mean was 0.040.

    An "above 0.5" count is wrong for a sharper reason. Measured across all
    27,219 cells: the model's top 500 are 100% cells that ALREADY have a station,
    and of the 26,334 cells with none, the highest probability is 0.305 and not
    one crosses 0.5. So "cells above 0.5" was, in practice, a count of existing
    stations being offered as candidates.

    What replaces it is the split below. The model is descriptive: it learned
    where stations ARE, not where they should go. Read the empty-cell figures as
    "how much does this resemble the places that get built on", and read
    cells_with_station as the context that makes that number mean anything.
    """
    cells_in_area: int = Field(
        ..., description="Cells the area really holds, before any limit is applied.")
    cells_predicted: int = Field(
        ..., description="Cells actually scored. Lower than cells_in_area when truncated.")
    truncated: bool = Field(
        ..., description="True when the area held more cells than the request could return. "
                         "The quietest cells are dropped first, never a geographic slice.")
    cells_with_station: int = Field(
        ..., description="Cells here that already hold a station. Not candidates.")
    cells_without_station: int = Field(
        ..., description="Cells here with no station. The only ones that could be built on.")
    mean_probability: Optional[float] = Field(
        None, description="Mean resemblance among cells WITHOUT a station. Null when every cell here already has one.")
    median_probability: Optional[float] = Field(
        None, description="Median resemblance among cells WITHOUT a station. Null when every cell here already has one.")
    max_probability: Optional[float] = Field(
        None, description="Highest resemblance among cells WITHOUT a station here. Read it "
                          "against resemblance_ceiling, never against 0.5 or 1.0. "
                          "Null when every cell here already has one.")
    resemblance_ceiling: Optional[float] = Field(
        None, description="The highest resemblance ANY unbuilt cell in the region reaches, "
                          "computed from the loaded model rather than written down. This is "
                          "what turns a bare 0.29 into '94% of the best anything unbuilt "
                          "scores'. Null when it could not be derived, and a client that gets "
                          "null must omit the comparison rather than fall back to a guess.")
    resemblance_ceiling_cells: Optional[int] = Field(
        None, description="How many unbuilt cells the ceiling was taken over, so the figure "
                          "is auditable rather than asserted.")
    mean_sessions_per_connector_day: Optional[float] = Field(
        None, description="Mean predicted sessions per connector per day among cells WITHOUT "
                          "a station, at the reference spec. Summarised over unbuilt cells "
                          "only, for the same reason the resemblance figures are: mixing in "
                          "cells that already hold a station describes the network that "
                          "exists rather than the opportunity being assessed.")
    median_sessions_per_connector_day: Optional[float] = Field(
        None, description="Median of the same. Prefer it to the mean when the area is small.")
    suitability_scale: Optional[dict[str, float]] = Field(
        None, description="The regional distribution these cells were read against: "
                          "red_floor, yellow_floor and cells_scored. Returned so a legend "
                          "prints the same numbers the shading used and the two cannot "
                          "drift. Null when no scale could be built, in which case a client "
                          "must omit the band claim rather than assume green.")
    cells_red: Optional[int] = Field(None, description="Unbuilt cells in the top decile here.")
    cells_yellow: Optional[int] = None
    cells_green: Optional[int] = None
    max_sessions_per_connector_day: Optional[float] = Field(
        None, description="Highest predicted utilisation among unbuilt cells here. Read it "
                          "against the grid-wide spread of about 1.66x between the 5th and "
                          "95th percentile: this model separates places by well under an "
                          "order of magnitude, and a client that renders it on a scale "
                          "implying more will overstate the difference between two cells.")


class PlannerPredictAreaResponse(BaseModel):
    """On-demand model predictions for an area the planner chose on the map.

    Computed at request time rather than read from a precomputed layer: the
    whole grid takes about 110 ms to score, so there is nothing to gain by
    freezing it in advance and a stale layer to lose.

    Predictions stay at the 500 m resolution the model was trained at. See
    PlannerAreaDistribution for why the area is not scored as a single unit.
    """
    distribution: PlannerAreaDistribution
    predictions: list[PlannerPrediction] = Field(
        ..., description="Per-cell predictions. Ordered by predicted utilisation, highest "
                         "first, because that is the question a planner asks and the only "
                         "one of the two models that can answer it for an unbuilt cell. "
                         "Falls back to resemblance order when no utilisation artifact is "
                         "loaded; utilisation_model is null when it does.")
    model: PlannerModelInfo
    utilisation_model: Optional[PlannerUtilisationInfo] = Field(
        None, description="Provenance for sessions_per_connector_day and for the ordering.")
    interpretation: str = Field(
        ..., description="What a high probability does and does not mean.")
    provenance: PlannerProvenance = PlannerProvenance()


class SiteRoiInput(BaseModel):
    """What a payback projection needs, split by who is entitled to know it.

    Capex and opex have no defaults on purpose. They are the planner's own cost
    structure, they dominate the result, and inventing them would make the
    endpoint answer a question nobody asked. Demand has no default for the same
    reason, and is required as either a daily session count or a utilisation
    target, never both.
    """
    cell_id: str
    capex_per_connector_idr: int = Field(
        ..., ge=0, examples=[250_000_000],
        description="Your installed cost per connector. No default: this is your number, not ours.")
    opex_monthly_idr: int = Field(
        ..., ge=0, examples=[15_000_000],
        description="Rent, demand charge, maintenance and staffing per month.")
    sessions_per_day: Optional[float] = Field(
        None, ge=0, description="Assumed demand. Supply this or utilisation_target, not both.")
    utilisation_target: Optional[float] = Field(
        None, ge=0, le=1,
        description="Assumed share of connector hours that are busy, 0 to 1. "
                    "Converted to sessions per day using the hardware you specify.")
    connectors: int = Field(2, ge=1, le=50)
    power_kw: float = Field(60.0, gt=0, le=1000)
    energy_per_session_kwh: float = Field(
        30.0, gt=0, le=500,
        description="Completed sessions in this database average 34.8 kWh, though "
                    "all but eight of them are simulated.")
    tariff_idr_per_kwh: Optional[int] = Field(
        None, gt=0, description="Defaults to the tariff the charging flow actually bills at.")
    admin_fee_idr: Optional[int] = Field(None, ge=0, description="Defaults to the billed admin fee.")
    energy_cost_idr_per_kwh: int = Field(
        0, ge=0, examples=[1450],
        description="What you pay for a kWh before reselling it. The tariff above is the "
                    "driver's price and you keep only the spread. Leave at 0 only if your "
                    "opex figure already contains the electricity bill.")
    horizon_years: int = Field(10, ge=1, le=40)

    @model_validator(mode="after")
    def _exactly_one_demand_input(self) -> "SiteRoiInput":
        given = [self.sessions_per_day is not None, self.utilisation_target is not None]
        if sum(given) != 1:
            raise ValueError(
                "supply exactly one of sessions_per_day or utilisation_target; "
                "two demand figures that disagree cannot both drive the projection")
        return self


class SiteRoiResponse(BaseModel):
    """A projection, with every input labelled by where it came from.

    payback_months and payback_years are null when the site does not break even.
    That is not a missing value: a site whose revenue never covers its running
    costs has no payback period, and capex divided by a negative margin would
    return a negative number that reads like a fast return.
    """
    cell_id: str
    kota: Optional[str] = None
    score: Optional[float] = None
    population: float
    poi_total: int
    station_count: int
    nearest_station_m: Optional[float] = None
    stations_2km: int

    sessions_per_day: float
    sessions_per_month: float
    energy_per_month_kwh: float
    capacity_sessions_per_day: float = Field(
        ..., description="Ceiling the hardware allows with no idle time at all. Real sites sit far beneath it.")
    utilisation: float
    revenue_monthly_idr: int = Field(..., description="Gross, before the energy is paid for.")
    energy_cost_idr_per_kwh: int
    energy_cost_monthly_idr: int
    opex_monthly_idr: int
    gross_margin_monthly_idr: int = Field(
        ..., description="Revenue less energy purchase cost less opex.")
    capex_total_idr: int
    payback_months: Optional[float] = None
    payback_years: Optional[float] = None
    net_at_horizon_idr: int
    breaks_even: bool
    horizon_years: int

    inputs: dict[str, Any] = Field(..., description="Every value the arithmetic used, after defaults.")
    input_sources: dict[str, str] = Field(
        ..., description="Where each input came from: planner, default, or charging tariff configuration.")
    demand_basis: str = Field(
        ..., description="What the demand figure rests on. Read this before quoting the payback.")
    cost_basis: str = Field(
        ..., description="How the electricity bill is being treated in this projection.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerCellsGeoJSON(BaseModel):
    """RFC 7946 FeatureCollection of grid cells, plus what it took to build it.

    Each feature is one 500 m cell polygon. `value` in the properties is the
    number the layer is coloured by, already selected by `metric`, so the client
    colours by one field and never has to know which column it came from.

    Coordinates are GeoJSON order, longitude before latitude. Leaflet's polygon
    constructor takes latitude first, so a Leaflet client has to swap them.
    """
    type: str = Field("FeatureCollection", examples=["FeatureCollection"])
    features: list[dict[str, Any]]
    metric: str = Field(..., description="Which layer the `value` property carries.")
    weights_applied: dict[str, float] = Field(
        ..., description="Rescaled to sum to 1. Only affects metric=score.")
    cells_returned: int
    cells_in_viewport: int = Field(
        ..., description="How many cells the viewport covers before the row limit.")
    truncated: bool = Field(
        ..., description="True when the limit cut the response. The cells kept are "
                         "the highest scoring ones, so a truncated map is missing its "
                         "quiet areas rather than an arbitrary slice.")
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerNearbyStation(BaseModel):
    id: str
    name: Optional[str] = None
    latitude: float = Field(
        ..., description="Needed to draw the link on a map, not only to list the distance.")
    longitude: float
    operator: Optional[str] = None
    power_kw: Optional[float] = None
    speed_tier: Optional[str] = None
    distance_m: float
    available_connectors: int
    total_connectors: int


class PlannerBenchmarkResponse(BaseModel):
    cell_id: str
    radius_km: float
    stations: list[PlannerNearbyStation]
    provenance: PlannerProvenance = PlannerProvenance()


class PlannerGridSummary(BaseModel):
    cells: int
    cells_with_station: int
    cells_populated: int
    stations: int
    connectors: int
    population_total: float
    areas: int
    built_at: Optional[datetime] = None
    provenance: PlannerProvenance = PlannerProvenance()
