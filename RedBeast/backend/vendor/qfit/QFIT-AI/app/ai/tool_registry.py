"""Tool registry: the only bridge between the language model and real data.

Each tool has a purpose, a typed and validated argument model, a handler that calls
the service layer, structured output and uniform error handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.requests import Release, TargetFields, TargetKind
from app.services import response_builder as rb
from app.utils.errors import QFitError
from app.utils.logging import get_logger

log = get_logger("tools")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchObjectArgs(_Args):
    name: str = Field(..., min_length=1, max_length=100, description="Object name or partial name")
    max_results: int = Field(5, ge=1, le=20)


class ResolveArgs(_Args):
    name: str = Field(..., min_length=1, max_length=100, description="Object name in catalog form (English or a designation), e.g. 'Andromeda Galaxy', 'M31', '3I/ATLAS'; never translated")
    target_kind: TargetKind = Field("auto", description="'solar_system' for planets, comets, asteroids; 'deep_sky' otherwise; 'auto' to detect")
    epoch_utc: str | None = Field(None, description="ISO-8601 time for a Solar System position (default: now)")


class SearchObservationsArgs(TargetFields):
    radius_deg: float = Field(0.003, gt=0, le=2, description="Search radius in degrees. Images are 3.5 deg wide, so a small radius already finds every image covering the position.")
    detector: int | None = Field(None, ge=1, le=6, description="SPHEREx detector band 1-6")
    release: Release = "all"
    start_utc: str | None = Field(None, description="Only observations after this ISO-8601 date")
    end_utc: str | None = Field(None, description="Only observations before this ISO-8601 date")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class ObservationMetadataArgs(_Args):
    observation_id: str = Field(..., min_length=3, max_length=120, description="Q-FIT observation id, e.g. 'spherex_qr3:2026W21_1A_0491_2:D4', as returned by a search")


class ImageArgs(TargetFields):
    cutout_size_deg: float = Field(0.1, gt=0, le=3.5, description="Side of the cutout in degrees")
    detector: int | None = Field(None, ge=1, le=6)
    release: Release = "all"
    limit: int = Field(6, ge=1, le=24)
    verify: bool = Field(False, description="Probe the archive to confirm the files are downloadable")


class SpectralArgs(TargetFields):
    release: Release = "all"
    extract_samples: bool = Field(False, description="Also download cutouts and read the raw pixel value and wavelength at the target. Slow (about 20-45 s per sample from IRSA): only when the user asks for pixel values or brightness readings")
    max_samples: int = Field(3, ge=1, le=6, description="Number of exposures to sample; each costs tens of seconds")


class ConeArgs(_Args):
    ra: float = Field(..., ge=0, le=360, description="Right ascension, ICRS, decimal degrees")
    dec: float = Field(..., ge=-90, le=90, description="Declination, ICRS, decimal degrees")
    radius_deg: float = Field(0.1, gt=0, le=2)
    object_type: str | None = Field(None, max_length=30, description="SIMBAD type code or name, e.g. 'brown dwarf', 'G', 'QSO'")
    limit: int = Field(20, ge=1, le=100)


class PeriodsArgs(TargetFields):
    radius_deg: float = Field(0.003, gt=0, le=2)
    gap_days: float = Field(20, gt=0, le=365, description="Exposures closer than this are one period")
    release: Release = "all"


class KnowledgeArgs(_Args):
    query: str = Field(..., min_length=2, max_length=300, description="The concept or question to look up, in the user's words")
    language: Literal["tr", "en"] | None = Field(None, description="Language of the passages; default: the language of the query")
    topic: str | None = Field(None, max_length=40, description="Optional topic filter, e.g. 'brown_dwarfs', 'spherex_data', 'hr_diagram'")


class CandidateArgs(_Args):
    object_name: str | None = Field(None, max_length=100, description="Name of the object, if it has one")
    ra: float = Field(..., ge=0, le=360, description="Right ascension, ICRS, decimal degrees, taken from retrieved data")
    dec: float = Field(..., ge=-90, le=90, description="Declination, ICRS, decimal degrees, taken from retrieved data")
    reason: str = Field(..., min_length=10, max_length=1000, description="What was noticed and why a person should look at it")
    observation_ids: list[str] = Field(default_factory=list, max_length=50, description="Observation ids returned by a SPHEREx tool")
    title: str | None = Field(None, max_length=120)


class ClarifyArgs(_Args):
    question: str = Field(..., min_length=3, max_length=400)
    options: list[str] = Field(default_factory=list, max_length=10)


Handler = Callable[[Any], Awaitable[dict[str, Any]]]
Presenter = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Handler
    presenter: Presenter          # result -> envelope parts (object/data/actions/sources)
    source: Literal["catalog", "spherex_archive", "knowledge_base", "citizen_science", "control"]

    def json_schema(self) -> dict[str, Any]:
        return _simplify(self.args_model.model_json_schema())

    def declaration(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.json_schema()}


def _simplify(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten the pydantic schema to the plain subset every LLM tool API accepts."""
    props = {}
    for name, spec in schema.get("properties", {}).items():
        spec = dict(spec)
        if "anyOf" in spec:  # Optional[X] -> X
            options = [o for o in spec.pop("anyOf") if o.get("type") != "null"]
            spec = {**options[0], **spec}
        for drop in ("title", "default", "exclusiveMinimum", "exclusiveMaximum"):
            spec.pop(drop, None)
        props[name] = spec
    return {"type": "object", "properties": props, "required": schema.get("required", [])}


def clean_arguments(raw: dict[str, Any]) -> dict[str, Any]:
    """Remove the placeholder values models put in optional arguments they have no value for.

    Measured on 2026-11-14: every OpenAI model tested sent e.g. {"object_name": "M31", "ra": 0,
    "dec": 0, "start_utc": ""}. Taken literally, (0, 0) is a real sky position, so the archive was
    searched there instead of at M31: a wrong answer, and a slow one. Rules:
      - empty strings and nulls mean "not given";
      - ra = dec = 0 together with an object name means "not given" (the name is the target).
    A request for the actual position RA 0, Dec 0 comes without a name and is kept."""
    args = {k: v for k, v in raw.items() if v is not None and not (isinstance(v, str) and not v.strip())}
    if args.get("object_name") and args.get("ra") == 0 and args.get("dec") == 0:
        args.pop("ra")
        args.pop("dec")
        log.info("placeholder coordinates dropped", extra={"object_name": args["object_name"]})
    return args


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def declarations(self) -> list[dict[str, Any]]:
        return [t.declaration() for t in self._tools.values()]

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "data_source": t.source,
                 "parameters": t.json_schema()} for t in self._tools.values()]

    async def execute(self, name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
        """Validate and run a tool. Always returns {"ok": bool, ...}; never raises."""
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": {"code": "unknown_tool", "message": f"No tool named '{name}'."}}
        try:
            args = tool.args_model.model_validate(clean_arguments(raw_args or {}))
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}"
                                 for e in exc.errors()[:5])
            return {"ok": False, "error": {"code": "invalid_arguments", "message": problems}}
        try:
            return {"ok": True, "result": await tool.handler(args)}
        except QFitError as exc:
            return {"ok": False, "error": exc.to_dict()}
        except Exception as exc:  # never leak internals to the model or the client
            log.exception("tool crashed", extra={"tool": name})
            return {"ok": False, "error": {"code": "internal_error", "retryable": False,
                                           "message": f"The tool failed unexpectedly ({type(exc).__name__})."}}


AI_ACTOR = "qfit-assistant"


def build_registry(search, observations, retrieval, *, knowledge=None, candidates=None) -> ToolRegistry:
    """Wire the tools to the service layer. The knowledge and candidate tools are only
    registered when those components are given."""
    registry = ToolRegistry()

    async def search_object(a: SearchObjectArgs):
        return (await search.search_objects(a.name, a.max_results)).model_dump()

    async def resolve(a: ResolveArgs):
        return (await search.resolve(a.name, a.target_kind, a.epoch_utc)).model_dump()

    async def search_obs(a: SearchObservationsArgs):
        return await observations.search_observations(**a.model_dump())

    async def obs_metadata(a: ObservationMetadataArgs):
        return await observations.get_observation(a.observation_id)

    async def images(a: ImageArgs):
        return await retrieval.image_products(**a.model_dump())

    async def spectral(a: SpectralArgs):
        return await retrieval.spectral_products(**a.model_dump())

    async def cone(a: ConeArgs):
        return await search.objects_near(a.ra, a.dec, a.radius_deg, a.object_type, a.limit)

    async def periods(a: PeriodsArgs):
        return await observations.observation_periods(**a.model_dump())

    async def clarify(a: ClarifyArgs):
        return {"question": a.question, "options": a.options}

    async def search_knowledge(a: KnowledgeArgs):
        return knowledge.search(a.query, language=a.language, topic=a.topic)

    async def submit_candidate(a: CandidateArgs):
        return await candidates.create(origin="ai", created_by=AI_ACTOR, title=a.title, reason=a.reason,
                                       target={"object_name": a.object_name, "ra": a.ra, "dec": a.dec},
                                       observation_ids=a.observation_ids)

    def present_clarify(result: dict[str, Any]) -> dict[str, Any]:
        return {"intent": "clarification_needed", "message": result["question"], "object": None, "data": {},
                "actions": [{"type": "request_clarification", "payload": result}], "sources": []}

    for tool in (
        Tool("search_celestial_object",
             "Look up an astronomical object by name in catalogs (SIMBAD; JPL Horizons for Solar System "
             "bodies) and list the matching candidates. Catalog data only: does not check SPHEREx.",
             SearchObjectArgs, search_object, lambda r: rb.from_resolve(r, "search_object"), "catalog"),
        Tool("resolve_object_coordinates",
             "Resolve an object name to ICRS coordinates in decimal degrees. Deep-sky objects use SIMBAD; "
             "planets, comets and asteroids use JPL Horizons and are valid only for the given epoch. "
             "Catalog data only: does not check SPHEREx.",
             ResolveArgs, resolve, rb.from_resolve, "catalog"),
        Tool("search_spherex_observations",
             "Search the NASA/IPAC IRSA archive for SPHEREx spectral images covering a sky position "
             "(object_name, or ra and dec). Returns verified archive records with dates, detector bands, "
             "wavelength ranges and download URLs, or an explicit no-data result.",
             SearchObservationsArgs, search_obs, rb.from_observations, "spherex_archive"),
        Tool("get_spherex_observation_metadata",
             "Get the archive metadata of one SPHEREx observation by its observation_id.",
             ObservationMetadataArgs, obs_metadata, rb.from_observation_detail, "spherex_archive"),
        Tool("retrieve_spherex_image",
             "Get real SPHEREx image products for a sky position: full FITS download URLs from IRSA plus "
             "cutout-service URLs centred on the target.",
             ImageArgs, images, rb.from_images, "spherex_archive"),
        Tool("retrieve_spherex_spectral_data",
             "Find SPHEREx spectral data for a sky position: the 102-channel All-Sky Cube tile and the "
             "coverage of the six detector bands by spectral images. Optionally reads per-exposure pixel "
             "samples (wavelength and surface brightness).",
             SpectralArgs, spectral, rb.from_spectral, "spherex_archive"),
        Tool("search_objects_by_coordinates",
             "List catalog objects (SIMBAD) within a radius of a sky position, optionally of one object "
             "type such as brown dwarfs. Catalog data only: does not check SPHEREx.",
             ConeArgs, cone, rb.from_cone, "catalog"),
        Tool("get_available_observation_periods",
             "List the time periods in which SPHEREx observed a sky position, by grouping the archive's "
             "exposures by date.",
             PeriodsArgs, periods, rb.from_periods, "spherex_archive"),
        Tool("request_clarification",
             "Ask the user a question when the request is ambiguous or lacks a target. Ends the turn.",
             ClarifyArgs, clarify, present_clarify, "control"),
    ):
        registry.register(tool)
    if knowledge is not None:
        registry.register(Tool(
            "search_knowledge_base",
            "Search Q-FIT's verified knowledge base (SPHEREx mission and data products, spectroscopy, "
            "brown dwarfs, the H-R diagram, time coverage, citizen science, evidence policy). Each passage "
            "comes with its sources. Use it for conceptual questions; it holds no observations.",
            KnowledgeArgs, search_knowledge, rb.from_knowledge, "knowledge_base"))
    if candidates is not None:
        registry.register(Tool(
            "submit_candidate_for_review",
            "Record a position as a candidate for human review, ONLY when the user asks for it. The record "
            "gets the status ai_generated_candidate: it is not a discovery and nothing is confirmed. Use "
            "coordinates and observation ids from tool results only.",
            CandidateArgs, submit_candidate, rb.from_candidate, "citizen_science"))
    return registry
