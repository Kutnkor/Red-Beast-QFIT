"""Turns service results into the response envelope parts (object, data, actions, sources).

Used by the REST routes and by the chat agent, so both speak the same contract and
the structured part of a chat answer is built from retrieved data, not from model text.
"""
from __future__ import annotations

import json
from typing import Any

from app.models.responses import empty_data

Partial = dict[str, Any]
IRSA = "NASA/IPAC IRSA"
_NOT_CHECKED = "Catalog data only: whether SPHEREx observed this object was not checked."


def _extras(result: dict[str, Any], kind: str, part: Partial) -> Partial:
    """Evidence class, caveats and media references derived from a service result."""
    status = result.get("status", "ok")
    blocked = status in ("ambiguous", "ambiguous_target", "not_found", "target_not_found", "moving_target", "no_data")
    sources = result.get("sources", [])
    evidence = [{"kind": "missing_information" if blocked else kind, "statement": part.get("message", ""),
                 "status": status, "source_names": [s.get("name", "") for s in sources][:4],
                 "source_urls": [s.get("url", "") for s in sources][:4]}]
    uncertainty = list(result.get("possible_reasons", []))
    obj = result.get("object") or {}
    uncertainty += obj.get("notes", [])
    if kind == "catalog_data" and status == "resolved":
        uncertainty.append(_NOT_CHECKED)
    if result.get("truncated_by_archive_limit"):
        uncertainty.append("The archive row limit was reached; more products may exist than are listed.")
    if result.get("periods"):
        uncertainty.append("Gaps between observation periods are times without observations, not evidence of no change.")
    if result.get("samples_note"):
        uncertainty.append(result["samples_note"])
        if any(s.get("ok") for s in result.get("samples", [])):
            evidence.append({"kind": "direct_measurement", "statement": "Single-pixel surface brightness read from "
                             "SPHEREx spectral image cutouts.", "status": "ok", "source_names": [IRSA],
                             "source_urls": [s["cutout_url"] for s in result["samples"] if s.get("ok")][:4]})
    media = []
    for item in result.get("image_products", []):
        verified = item.get("download_check", {}).get("verified")
        media.append({"media_type": "fits_cutout", "url": item.get("cutout_url"), "full_file_url": item.get("access_url"),
                      "preview_url": item.get("preview_url"),
                      "observation_id": item["observation_id"], "detector": item.get("detector"),
                      "time_utc": item.get("t_min_utc"), "collection": item.get("collection"), "source": IRSA,
                      "verified": verified})
    if result.get("image_products") and all(m["verified"] is None for m in media):
        uncertainty.append("Download links were not probed, so file availability is not verified.")
    for item in result.get("spectral_products", []):
        if item.get("product_kind") == "all_sky_cube":
            media.append({"media_type": "fits_cube", "url": item.get("access_url"), "full_file_url": item.get("access_url"),
                          "observation_id": item["observation_id"], "detector": None, "time_utc": item.get("t_min_utc"),
                          "collection": item.get("collection"), "source": IRSA, "verified": None})
    return {"evidence": evidence, "uncertainty": uncertainty, "media": media}


def _evidence(kind: str):
    def decorate(fn):
        def wrapper(result: dict[str, Any], *args: Any, **kwargs: Any) -> Partial:
            part = fn(result, *args, **kwargs)
            part.update(_extras(result, kind, part))
            return part
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorate


def _action(kind: str, **payload: Any) -> dict[str, Any]:
    return {"type": kind, "payload": payload}


def _object_actions(obj: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not obj:
        return []
    focus = {"ra": obj["ra"], "dec": obj["dec"], "frame": obj.get("coordinate_frame", "ICRS")}
    if obj.get("position_time_dependent"):
        focus["epoch_utc"] = obj.get("position_epoch_utc")
    return [_action("display_object", object=obj), _action("focus_map", **focus)]


def _target_actions(result: dict[str, Any]) -> list[dict[str, Any]]:
    status = result.get("status")
    if status == "ambiguous_target":
        return [_action("request_clarification", question=result.get("message"),
                        options=result.get("candidates", []))]
    if status == "target_not_found":
        return [_action("show_error", code="object_not_found", message=result.get("message"))]
    actions = _object_actions(result.get("object"))
    target = result.get("target") or {}
    if not actions and target.get("ra") is not None:
        actions.append(_action("focus_map", ra=target["ra"], dec=target["dec"], frame="ICRS"))
    if status == "moving_target":
        actions.append(_action("show_error", code="moving_target", message=result.get("message")))
    return actions


def _search_meta(result: dict[str, Any], *keys: str) -> dict[str, Any]:
    base = ("status", "target", "total", "returned", "offset", "limit", "has_more", "summary",
            "filters", "collections_searched", "truncated_by_archive_limit", "possible_reasons",
            "candidates")
    return {k: result[k] for k in base + keys if k in result}


@_evidence("catalog_data")
def from_resolve(result: dict[str, Any], intent: str = "resolve_coordinates") -> Partial:
    status, obj = result["status"], result.get("object")
    if status == "resolved":
        actions = _object_actions(obj)
    elif status == "ambiguous":
        actions = [_action("request_clarification", question=result["message"],
                           options=result.get("candidates", []))]
    else:
        actions = [_action("show_error", code="object_not_found", message=result["message"])]
    return {"intent": intent, "message": result["message"], "object": obj,
            "data": empty_data(catalog={"status": status, "candidates": result.get("candidates", [])}),
            "actions": actions, "sources": result.get("sources", [])}


@_evidence("catalog_data")
def from_cone(result: dict[str, Any]) -> Partial:
    center = result["center"]
    kind = f" of type {result['object_type_filter']}" if result.get("object_type_filter") else ""
    return {"intent": "search_objects_by_coordinates",
            "message": f"SIMBAD lists {result['count']} catalog object(s){kind} within "
                       f"{result['radius_deg']:g} deg of RA {center['ra']:.4f}, Dec {center['dec']:.4f}.",
            "object": None,
            "data": empty_data(catalog={k: result[k] for k in ("center", "radius_deg", "object_type_filter",
                                                              "count", "limit", "possibly_truncated",
                                                              "objects", "note") if k in result}),
            "actions": [_action("focus_map", ra=center["ra"], dec=center["dec"], frame="ICRS",
                                radius_deg=result["radius_deg"])],
            "sources": result.get("sources", [])}


@_evidence("archive_metadata")
def from_observations(result: dict[str, Any]) -> Partial:
    actions = _target_actions(result)
    if result.get("status") in ("ok", "no_data"):
        actions.append(_action("display_observations", total=result["total"], returned=result["returned"],
                               target=result["target"],
                               observation_ids=[o["observation_id"] for o in result["observations"]]))
    return {"intent": "search_observations", "message": result["message"], "object": result.get("object"),
            "data": empty_data(spherex_available=result.get("spherex_available"),
                               observations=result.get("observations", []), search=_search_meta(result)),
            "actions": actions, "sources": result.get("sources", [])}


@_evidence("archive_metadata")
def from_observation_detail(result: dict[str, Any]) -> Partial:
    products = result["products"]
    actions = [_action("display_observations", total=len(products), returned=len(products),
                       observation_ids=[p["observation_id"] for p in products])]
    first = products[0]
    if first.get("center_ra") is not None:
        actions.append(_action("focus_map", ra=first["center_ra"], dec=first["center_dec"], frame="ICRS",
                               fov_deg=first.get("fov_deg")))
    return {"intent": "get_observation_metadata", "message": result["message"], "object": None,
            "data": empty_data(spherex_available=True, observations=products),
            "actions": actions, "sources": result.get("sources", [])}


@_evidence("archive_metadata")
def from_images(result: dict[str, Any]) -> Partial:
    actions = _target_actions(result)
    items = result.get("image_products", [])
    if items:
        actions.append(_action("display_image", products=[
            {"observation_id": i["observation_id"], "detector": i["detector"], "t_min_utc": i["t_min_utc"],
             "url": i["access_url"], "cutout_url": i["cutout_url"], "preview_url": i.get("preview_url"),
             "format": i["access_format"],
             "verified": i["download_check"].get("verified")} for i in items]))
    return {"intent": "retrieve_image", "message": result["message"], "object": result.get("object"),
            "data": empty_data(spherex_available=result.get("spherex_available"), image_products=items,
                               search=_search_meta(result, "total_available", "format_note")),
            "actions": actions, "sources": result.get("sources", [])}


@_evidence("archive_metadata")
def from_spectral(result: dict[str, Any]) -> Partial:
    actions = _target_actions(result)
    products = result.get("spectral_products", [])
    if products or result.get("samples"):
        actions.append(_action("display_spectrum",
                               products=[{"observation_id": p["observation_id"], "url": p["access_url"],
                                          "product_kind": p["product_kind"],
                                          "spectral_channels": p.get("spectral_channels")} for p in products],
                               samples=result.get("samples", []), samples_note=result.get("samples_note")))
    return {"intent": "retrieve_spectrum", "message": result["message"], "object": result.get("object"),
            "data": empty_data(spherex_available=result.get("spherex_available", True),
                               spectral_products=products,
                               spectral=_search_meta(result, "spectral_image_coverage", "samples",
                                                     "samples_note", "observation_id")),
            "actions": actions, "sources": result.get("sources", [])}


@_evidence("archive_metadata")
def from_periods(result: dict[str, Any]) -> Partial:
    actions = _target_actions(result)
    if result.get("status") in ("ok", "no_data"):
        actions.append(_action("display_observations", view="periods", total=result["period_count"],
                               target=result["target"], periods=result["periods"]))
    return {"intent": "get_observation_periods", "message": result["message"], "object": result.get("object"),
            "data": empty_data(spherex_available=result.get("spherex_available"),
                               observation_periods=result.get("periods", []),
                               search=_search_meta(result, "period_gap_days", "period_count")),
            "actions": actions, "sources": result.get("sources", [])}


def from_knowledge(result: dict[str, Any]) -> Partial:
    hits = result["hits"]
    sources, seen = [], set()
    for hit in hits:
        for source in hit["sources"]:
            if source["id"] not in seen:
                seen.add(source["id"])
                sources.append(source)
    message = (f"{len(hits)} knowledge base passage(s) found." if hits else
               "The knowledge base has no passage on this question.")
    return {"intent": "knowledge_lookup", "message": message, "object": None,
            "data": empty_data(knowledge={k: result[k] for k in ("query", "language", "index_version", "retriever",
                                                                 "other_language_used", "count", "hits")}),
            "actions": [], "sources": sources,
            "evidence": [{"kind": "knowledge_base", "statement": f"{h['title']} - {h['heading']}", "status": "ok",
                          "chunk_id": h["chunk_id"], "source_names": [s["name"] for s in h["sources"]][:4],
                          "source_urls": [s["url"] for s in h["sources"]][:4]} for h in hits]
            or [{"kind": "missing_information", "statement": message, "status": "no_data",
                 "source_names": [], "source_urls": []}],
            "uncertainty": [f"{h['title']} - {h['heading']}: {h['verification_note']}" for h in hits
                            if h.get("verification_note")]
            + (["The passage was found in another language than the question."] if result.get("other_language_used") else []),
            "media": []}


def from_candidate(result: dict[str, Any]) -> Partial:
    return {"intent": "submit_candidate", "object": None,
            "message": f"Candidate {result['candidate_id']} was recorded with status {result['status']}. "
                       "It is a candidate for human review, not a discovery.",
            "data": empty_data(candidate=result), "actions": [], "sources": [],
            "evidence": [{"kind": "candidate_record", "statement": result["reason"], "status": result["status"],
                          "source_names": [], "source_urls": []}],
            "uncertainty": [result["disclaimer"]], "media": []}


def merge(partials: list[Partial]) -> Partial:
    """Combine the parts produced by several tool calls of one chat turn."""
    merged: Partial = {"object": None, "data": empty_data(), "actions": [], "sources": [], "evidence": [],
                       "uncertainty": [], "media": []}
    for part in partials:
        merged["object"] = part.get("object") or merged["object"]
        for key, value in part.get("data", {}).items():
            if key == "spherex_available":
                if value is not None:
                    merged["data"][key] = value
            elif value or key not in merged["data"]:
                merged["data"][key] = value
        merged["actions"] += part.get("actions", [])
        merged["sources"] += part.get("sources", [])
        merged["evidence"] += part.get("evidence", [])
        merged["media"] += [m for m in part.get("media", []) if m not in merged["media"]]
        merged["uncertainty"] += [u for u in part.get("uncertainty", []) if u not in merged["uncertainty"]]
    seen, actions = set(), []
    last_focus = max((i for i, a in enumerate(merged["actions"]) if a["type"] == "focus_map"), default=-1)
    for index, action in enumerate(merged["actions"]):
        key = json.dumps(action, sort_keys=True, default=str)
        if key in seen or (action["type"] == "focus_map" and index != last_focus):
            continue
        seen.add(key)
        actions.append(action)
    merged["actions"] = actions
    if merged["data"]["spherex_available"] is not None:    # the archive was checked in this same turn
        merged["uncertainty"] = [u for u in merged["uncertainty"] if u != _NOT_CHECKED]
    urls, sources = set(), []
    for source in merged["sources"]:
        if source.get("url") not in urls:
            urls.add(source.get("url"))
            sources.append(source)
    merged["sources"] = sources
    return merged
