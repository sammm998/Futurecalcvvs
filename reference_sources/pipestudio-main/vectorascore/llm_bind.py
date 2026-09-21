"""Stage 8 (mode "full") - llm_bind: a frontier model decides EVERY landing.

Two providers answer the same questions with the same rules, and the reviewer
picks which one runs: "fable" (Anthropic Claude Fable) or "astra" (OpenAI GPT-6
Astra). Only the request differs - the questions, the schema and everything
built on the answers are shared.

The vector stages are trusted: pipes (stretches + nodes), joining points,
leaders (label -> landing node) and labels. For every landing the model is
asked which stretch at that joining point the label describes - "this side
or that side, seen from the joining point" - with the VVS reading rules as
the instructions and the sheet's own evidence per candidate: heading away
from the node, what waits at the far end (the next label's VG/DN, a wall, the
sheet edge, a bare end), line type, layer system.

Deterministic propagation (a label runs on to the next labelled node and
into unlabelled branches) is applied afterwards on the model's decisions.
"""
import json
import math
import os

import numpy as np


def _j(o):
    return json.dumps(o, ensure_ascii=False, default=lambda x: bool(x) if isinstance(x, np.bool_) else float(x))
from collections import defaultdict

from shapely.geometry import Point, Polygon

from . import vvs
from .associate import _axis_at, _entry_distances, _is_designation, _stretch_system, add_twins, bare_split_labels, label_systems, landing_candidates, propagate, r1_labels, split_form_labels
from .geom import dist

# The providers the review app offers, one button each.
PROVIDERS = {"fable": {"vendor": "anthropic", "name": "Fable", "model": os.environ.get("LLM_MODEL", "claude-fable-5-1")},
             "astra": {"vendor": "openai", "name": "Astra", "model": os.environ.get("OPENAI_MODEL", "gpt-6-astra")}}
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "fable")
MODEL = PROVIDERS["fable"]["model"]
# USD per 1M tokens (input, output) - both vendors' list prices checked 2026-09-06 against
# platform.claude.com/docs/en/about-claude/pricing and OpenAI's own rate card.
PRICES = {"claude-fable-5-1": (10.0, 50.0), "claude-fable-5": (10.0, 50.0), "claude-opus-5": (5.0, 25.0),
          "claude-opus-4-8": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0),
          "gpt-6-astra": (10.0, 50.0), "gpt-5.6-sol": (4.0, 20.0), "gpt-5.6-terra": (2.0, 12.0),
          "gpt-5.6-luna": (0.2, 1.2)}
# A cache hit is 0.1x the input rate everywhere except Fable 5.1 / Mythos 5.1, which are 0.025x.
CACHE_READ = {"claude-fable-5-1": 0.025, "claude-mythos-5-1": 0.025}


def _cost(model, tokens_in, tokens_out, cache_read=0, cache_write=0):
    # A 5-minute cache write is 1.25x the input rate on both vendors (Anthropic's 1h write is 2x -
    # nothing here asks for the 1h TTL).
    pin, pout = PRICES.get(model, PRICES[MODEL])
    plain = tokens_in - cache_read - cache_write
    return (plain * pin + cache_read * pin * CACHE_READ.get(model, 0.1) + cache_write * pin * 1.25
            + tokens_out * pout) / 1e6
EFFORT = os.environ.get("LLM_BIND_EFFORT", os.environ.get("LLM_EFFORT", "medium"))

SYSTEM = """GOAL: find the correct description for EVERY pipe. On a Swedish VVS (plumbing) floor plan each pipe stretch
must end up bound to the one label that describes it (system, running number, dimension). The pipes are the
target, not the labels: a label does NOT have to be used - a label whose leader lands somewhere but which, by the
rules below, describes no stretch at that joining point stays unbound (answer stretch: null).
Never force a label onto a stretch just to use it, and never bind a stretch to a label the rules speak against.
You make the connection at the joining points where the leaders land.
Everything you receive was extracted from the PDF vectors and is reliable: the pipes (stretches between
joining points, with a graph), the joining points, the leaders (which label lands on which joining point)
and the labels (parsed designation: system, running number, dimension DN, optional level VG/CL).

At a joining point where a label lands, two (sometimes more) stretches meet. Decide which one the label
describes - the one on THIS side or on THAT side seen from the joining point. Rules, in this resolution order:

1. THE READING RULE. A drawing is read from outside inward: from where the pipe enters (out of a wall, from
   the sheet edge, from a riser) towards the fixtures. A label is placed at the BEGINNING of the run it
   describes, so it describes the stretch that continues INWARD (away from the entry) - never the one behind
   it. Candidates flagged ends_in_wall / ends_at_sheet_edge, or leading back towards such an end, are the
   entry side.
2. GRAVITY SYSTEMS (S*, D*; not SL) carry invert levels VG. Water runs OUT towards the LOWER VG; reading
   runs UPHILL: the label at VG x describes the stretch that climbs towards the next label with a HIGHER VG.
   Between two consecutive labelled joining points there is exactly one dimension: the one printed at the
   lower VG. Prefer this over everything else where VG is present. Some offices write CL instead of VG on
   gravity labels: on S*/D* systems a CL orders the run exactly like VG. On pressure pipes (KV, VV, VS...)
   CL is a mounting height and carries NO direction information.
3. DIMENSION. Runs taper towards fixtures: between the candidates, the side whose next label has the larger
   DN is upstream; the label belongs to the smaller/downstream side. A label never describes a stretch whose
   far end carries a label of the same system with a LARGER DN.
4. The same label never owns the stretches on BOTH sides of its own joining point. A run crossing several
   labelled joining points carries one label per joining point.
5. Systems VP, VS, KB, KM, FV, FK (line_count 2) are drawn as two parallel pipes with one label; the
   unlabelled parallel twin carries the same label. KV, VV, VVC, S, D: every pipe is labelled individually.
6. A label's layer_system must match the stretch's layer_system when both are known.
7. Stacked designations on one leader that crosses every pipe of a bundle: one row per landing, in sheet
   reading order (left to right for vertical pipes, top to bottom for horizontal ones). A row that has a
   leader of its own is read by that leader alone - never map rows onto parallel pipes by their order.
If nothing decides, choose the side that is NOT the entry side and mark the decision ambiguous; if both sides
are excluded by the rules (e.g. both far ends carry a larger DN, or the label's system matches neither stretch),
answer stretch: null.
Answer with one decision per (label, designation_idx, landing_node): the chosen stretch (or null), and
ambiguous: true when the rules above did not settle it."""

# Fable gets the rules as they are: its wording was tuned against the expert's rounds and its safety
# classifier is sensitive to anything that reads like a request for reasoning (see _ask_anthropic).
# GPT-6 Astra needs the answering contract spelled out - left implicit it drops landings, answers a
# label once instead of once per designation, and names stretches that were not among the candidates.
VENDOR_NOTE = {"anthropic": "", "openai": """HOW TO ANSWER (this is a contract, not a rule of the drawing):
- Answer EVERY question you are given, exactly once per (label, designation_idx, node). A label with
  several designations at one landing gets one decision per designation - never one decision for the label.
- "stretch" must be one of the stretch ids listed under that question's own "candidates", or null.
  Never a stretch id taken from the sheet data, and never one from another question.
- Work the rules in their numbered order and stop at the first one that decides. Set ambiguous: true
  only when none of them did - not as a hedge on a decision the rules made.
- Return only the JSON object of the schema, no commentary."""}


def system_prompt(vendor):
    note = VENDOR_NOTE[vendor]
    return SYSTEM + ("\n\n" + note if note else "")


SCHEMA = {
    "type": "object",
    "properties": {"decisions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "label": {"type": "integer"}, "designation_idx": {"type": "integer"}, "node": {"type": "integer"},
            "stretch": {"type": ["integer", "null"]},
            "ambiguous": {"type": "boolean"}},
        "required": ["label", "designation_idx", "node", "stretch", "ambiguous"],
        "additionalProperties": False}}},
    "required": ["decisions"], "additionalProperties": False}


def _heading(deg):
    d = deg % 360
    names = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]      # y grows downward on the page
    return names[int((d + 22.5) // 45) % 8]


def _dir_from(stretches, sid, node):
    s = stretches[sid]
    pts = s["points"] if s["node_a"] == node else s["points"][::-1]
    a = pts[0]
    for b in pts[1:]:
        if dist(a, b) >= 3.0:
            return _heading(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
    return _heading(math.degrees(math.atan2(pts[-1][1] - a[1], pts[-1][0] - a[0])))


def build_context(A, R, L, B, page):
    nodes = {n["id"]: n for n in A["nodes"]}
    stretches = {s["id"]: s for s in A["stretches"]}
    labels = {l["id"]: l for l in L}
    walls = [Polygon(w["shell"], w["holes"]) for w in B.get("walls", []) if len(w["shell"]) >= 4]
    W, H = page

    def at_wall(pt):
        q = Point(pt)
        return any(w.distance(q) <= 6.0 for w in walls)

    def at_edge(pt):
        return pt[0] < 0.04 * W or pt[0] > 0.96 * W or pt[1] < 0.04 * H or pt[1] > 0.96 * H

    node_labels = defaultdict(list)
    for ld in R["leaders"]:
        for g in ld["landings"]:
            if g["node"] is not None:
                node_labels[g["node"]].append(ld["label"])

    def label_brief(lid):
        l = labels[lid]
        return {"label": lid,
                "designations": [{"idx": i, "raw": d["raw"], "system": d["system"] + (d["number"] or ""),
                                  "dimension": d["dimension"], "line_count": d.get("line_count"), "count": d.get("count", 1)}
                                 for i, d in enumerate(l["designations"])],
                "level": l.get("level") and {"kind": l["level"]["kind"], "value": l["level"]["value"]},
                "layer_system": l.get("layer_system")}

    def far_end_info(sid, node):
        s = stretches[sid]
        far = s["node_b"] if s["node_a"] == node else s["node_a"]
        n = nodes[far]
        p = s["points"][-1] if s["node_a"] == node else s["points"][0]
        info = {"far_node": far, "far_node_kind": n["kind"],
                "labels_at_far_node": [label_brief(x) for x in node_labels.get(far, [])],
                "far_end_in_wall": at_wall(p), "far_end_at_sheet_edge": at_edge(p),
                "continues_beyond_far_node": [c for c in n["stretches"] if c != sid]}
        return info

    r1 = lambda p: [round(p[0], 1), round(p[1], 1)]
    stretch_rows = []
    for s in A["stretches"]:
        if s.get("in_wall") or s.get("entry"):
            continue                                    # never a candidate: out of scope / unbound by rule
        stretch_rows.append({"id": s["id"], "node_a": s["node_a"], "node_b": s["node_b"],
                             "start": r1(s["points"][0]), "end": r1(s["points"][-1]), "length": round(s["length"], 1),
                             "line_type": s["line_type"], "layer_system": _stretch_system(s["layer"])})
    node_rows = [{"id": n["id"], "x": round(n["x"], 1), "y": round(n["y"], 1), "kind": n["kind"], "stretches": n["stretches"],
                  **({"attached_to_stretch": n["on_stretch"]} if n.get("on_stretch") is not None else {})}
                 for n in A["nodes"] if n["kind"] not in ("end",)]
    leader_rows = [{"label": ld["label"], "anchor": r1(ld["anchor"]), "landing_nodes": sorted({g["node"] for g in ld["landings"] if g["node"] is not None})}
                   for ld in R["leaders"] if ld["label"] is not None]
    questions = []
    solid_only = r1_labels(L); short_only = bare_split_labels(L)
    for ld in R["leaders"]:
        l = labels[ld["label"]]
        if not l.get("valid", True) or not l["designations"] or not l.get("usable", True):
            continue                                    # no dimension read: nothing to bind
        lands = sorted({g["node"] for g in ld["landings"] if g["node"] is not None})
        for nid in lands:
            d0 = l["designations"][0]
            cands = landing_candidates(ld["label"], nid, nodes, stretches, solid_only, d0["system"] + (d0["number"] or ""), short_only)
            if len(cands) < 2:
                continue                                # nothing to decide: the rules bind the only candidate
            questions.append({"label": ld["label"], "designations": label_brief(ld["label"])["designations"],
                              "level": label_brief(ld["label"])["level"], "layer_system": l.get("layer_system"),
                              "node": nid, "node_kind": nodes[nid]["kind"], "node_at": r1([nodes[nid]["x"], nodes[nid]["y"]]),
                              "candidates": [{"stretch": c, "heading_from_node": _dir_from(stretches, c, nid),
                                              "length": round(stretches[c]["length"], 1), "line_type": stretches[c]["line_type"],
                                              "layer_system": _stretch_system(stretches[c]["layer"]),
                                              **far_end_info(c, nid)} for c in cands]})
    return {"sheet_size": page, "stretches": stretch_rows, "joining_points": node_rows, "leaders": leader_rows,
            "labels": [label_brief(l["id"]) for l in L if l.get("valid", True) and l["designations"]],
            "questions": questions}


def assemble_fingerprint(A):
    """Identity of the stretch graph a binding was made for: a re-run that changes
    the stretches makes stored decisions meaningless (ids move)."""
    import hashlib
    key = json.dumps([(s["id"], s["node_a"], s["node_b"], round(s["length"], 1)) for s in A["stretches"]])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


NEIGHBOURHOOD = 250.0     # pt: the sheet data sent with a chunk of questions reaches this far around them
CHUNK = 40                # questions per request
PARALLEL = 4              # requests in flight at once


def chunk_questions(questions, size=CHUNK):
    """Questions grouped by where they are on the sheet, so one request's
    neighbourhood stays compact (a column band 400 pt wide, top to bottom)."""
    qs = sorted(questions, key=lambda q: (int(q["node_at"][0] // 400), q["node_at"][1]))
    return [qs[i:i + size] for i in range(0, len(qs), size)]


def local_context(ctx, chunk, reach=NEIGHBOURHOOD):
    """The part of the sheet a chunk of questions can see: every stretch within
    ``reach`` of one of its joining points (or named by a candidate), the joining
    points of those stretches, and the leaders and labels landing on them. The
    facts the rules need about the far ends (next label's VG/DN, wall, edge) are
    already inside each candidate, so the neighbourhood is context, not the
    evidence itself. The whole sheet was 118k tokens a request on a dense plan;
    this is a fifth of it and the model reasons over far less."""
    pts = [tuple(q["node_at"]) for q in chunk]
    keep_s = {c["stretch"] for q in chunk for c in q["candidates"]} | {c2 for q in chunk for c in q["candidates"] for c2 in c["continues_beyond_far_node"]}
    for s in ctx["stretches"]:
        if any(min(dist(s["start"], p), dist(s["end"], p)) <= reach for p in pts):
            keep_s.add(s["id"])
    stretches = [s for s in ctx["stretches"] if s["id"] in keep_s]
    keep_n = {s["node_a"] for s in stretches} | {s["node_b"] for s in stretches} | {q["node"] for q in chunk}
    nodes = [n for n in ctx["joining_points"] if n["id"] in keep_n]
    leaders = [ld for ld in ctx["leaders"] if set(ld["landing_nodes"]) & keep_n]
    keep_l = {ld["label"] for ld in leaders} | {q["label"] for q in chunk}
    labels = [l for l in ctx["labels"] if l["label"] in keep_l]
    return {"sheet_size": ctx["sheet_size"], "stretches": stretches, "joining_points": nodes, "leaders": leaders, "labels": labels}


def _user_message(ctx, chunk):
    return "Sheet data (trusted; the neighbourhood of the landings below):\n" + _j(local_context(ctx, chunk)) + \
        "\n\nDecide these landings (one decision per label/designation/node; for a label with several designations and one landing, give one decision per designation):\n" + _j(chunk)


def _ask_anthropic(client, model, ctx, chunk):
    user = _user_message(ctx, chunk)
    # Fable's safety classifiers may decline a request (stop_reason "refusal"). Asking for a
    # per-decision "rule" or "confidence" field triggered the reasoning_extraction refusal on
    # every call (probed 2026-09-03); a boolean "ambiguous" flag passes. Keep the schema to facts.
    with client.beta.messages.stream(model=model, max_tokens=32000, system=system_prompt("anthropic"),
                                     betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                     output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
                                     messages=[{"role": "user", "content": user}]) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        sd = getattr(resp, "stop_details", None)
        return [{"error": "refusal", "category": getattr(sd, "category", None), "explanation": getattr(sd, "explanation", None)}], None
    served = getattr(resp, "model", model)
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    cr = getattr(resp.usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(resp.usage, "cache_creation_input_tokens", 0) or 0
    return json.loads(text).get("decisions", []), _usage(served, resp.usage.input_tokens, resp.usage.output_tokens, cr, cw)


def _ask_openai(client, model, ctx, chunk):
    # Responses API: the schema hangs off text.format (strict mode needs every property in
    # "required" and additionalProperties false - SCHEMA already satisfies both).
    resp = client.responses.create(
        model=model, max_output_tokens=32000, reasoning={"effort": EFFORT},
        input=[{"role": "system", "content": system_prompt("openai")},
               {"role": "user", "content": _user_message(ctx, chunk)}],
        text={"format": {"type": "json_schema", "name": "landing_decisions", "strict": True, "schema": SCHEMA}})
    u = resp.usage
    det = getattr(u, "input_tokens_details", None)
    cr = getattr(det, "cached_tokens", 0) or 0
    cw = getattr(det, "cache_write_tokens", 0) or 0
    use = _usage(getattr(resp, "model", model), u.input_tokens, u.output_tokens, cr, cw)
    refusal = next((c for it in resp.output for c in getattr(it, "content", None) or []
                    if getattr(c, "type", "") == "refusal"), None)
    if refusal is not None:
        return [{"error": "refusal", "category": "refusal", "explanation": getattr(refusal, "refusal", None)}], use
    if resp.status != "completed":
        # ran out of output tokens mid-answer: no usable JSON, but the tokens were billed
        return [{"error": resp.status, "category": getattr(getattr(resp, "incomplete_details", None), "reason", None),
                 "explanation": None}], use
    return json.loads(resp.output_text or "{}").get("decisions", []), use


def _usage(model, tokens_in, tokens_out, cache_read, cache_write=0):
    return {"in": tokens_in, "out": tokens_out, "cache_read": cache_read, "cache_write": cache_write, "model": model,
            "usd": round(_cost(model, tokens_in, tokens_out, cache_read, cache_write), 4)}


def llm_bind(A, R, L, B, page, max_questions=CHUNK, provider=DEFAULT_PROVIDER):
    import time
    from concurrent.futures import ThreadPoolExecutor
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r} (have {', '.join(PROVIDERS)})")
    pv = PROVIDERS[provider]
    model = pv["model"]
    t0 = time.time()
    if pv["vendor"] == "anthropic":
        import anthropic
        client, ask = anthropic.Anthropic(), _ask_anthropic
    else:
        import openai
        client, ask = openai.OpenAI(), _ask_openai
    ctx = build_context(A, R, L, B, page)
    questions = ctx.pop("questions")
    chunks = chunk_questions(questions, max_questions)
    decisions, usage = [], []
    # the chunks are independent: run them side by side (wall time ÷ PARALLEL)
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        for dec, use in pool.map(lambda ch: ask(client, model, ctx, ch), chunks):
            decisions.extend(dec)
            if use:
                usage.append(use)

    refusals = [d for d in decisions if "error" in d]
    return {"mode": "full", "provider": provider, "provider_name": pv["name"], "model": model,
            "effort": EFFORT, "questions": len(questions), "decisions": decisions,
            "fingerprint": assemble_fingerprint(A),
            "refused": len(refusals), "refusal": refusals[0] if refusals else None,
            "usage": usage, "tokens_in": sum(u["in"] for u in usage), "tokens_out": sum(u["out"] for u in usage),
            "usd": round(sum(u["usd"] for u in usage), 4), "calls": len(usage), "seconds": round(time.time() - t0, 1),
            "bindings": bind_from_decisions(A, R, L, decisions, questions, model)}


def bind_from_decisions(A, R, L, decisions, questions, model=MODEL):
    """The bindings of a model run: Fable's decisions at the landings it was asked
    about, the rules' own bindings at every landing it was not (a single
    candidate is bound by the rules, never asked - and was silently lost between
    2026-09-05 and the expert's evening round: 50 labels without a pipe), the
    rules' twins where their partner survived, then the shared propagation.
    Pure: a stored run is rebuilt from its decisions without a new request."""
    nodes = {n["id"]: n for n in A["nodes"]}
    stretches = {s["id"]: s for s in A["stretches"]}
    labels = {l["id"]: l for l in L}
    asked = {(q["label"], q["node"]) for q in questions}
    decided = {(d["label"], d["node"]) for d in decisions if "error" not in d and d.get("stretch") is not None}   # "none of them" is no decision: the rules' guess stands, low
    bindings, owner = [], {}
    def add(b):
        b = dict(b, id=len(bindings)); b.pop("superseded", None)
        bindings.append(b)
        if b["stretch"] not in owner or (bindings[owner[b["stretch"]]]["confidence"] == "low" and b["confidence"] != "low"):
            owner[b["stretch"]] = b["id"]
    for b in R["bindings"]:
        if b["node"] is not None and b["rule"] not in ("through_mark", "propagated") and not ((b["label"], b["node"]) in asked and (b["label"], b["node"]) in decided):
            add(b)                                      # not asked, or asked in this run but never answered (a leader found since): the rules' binding
    for d in decisions:
        if "error" in d or d["stretch"] is None or d["stretch"] not in stretches:
            continue
        if d["label"] not in labels or d["designation_idx"] >= len(labels[d["label"]]["designations"]):
            continue
        if (d["label"], d["node"]) not in asked:
            continue                                # no longer a question (a rule now binds it): the rule's binding stands
        conf = "low" if d.get("ambiguous") else "high"
        if conf == "low" and any(b["node"] == d["node"] and b["label"] == d["label"] and b["stretch"] == d["stretch"] for b in R["bindings"]):
            conf = "medium"                         # Fable unsure, the rules agree with it: a fair guess (0111 at (1030,851): KV1-X7-20/W's tick)
        add({"stretch": d["stretch"], "label": d["label"], "designation_idx": d["designation_idx"],
             "node": d["node"], "leader": None, "confidence": conf, "rule": "fable", "reason": "decided by " + model + (" (ambiguous)" if conf == "low" else "")})
    # two labels landing at one joining point both told to take the same piece:
    # the label whose rule binding names another piece takes that one instead
    # (expert, 0111 at (443,1185): VS1-S13-15/W's two labels at ring 136 - 17 names
    # the pipe above (64), 86 the pipe below (169))
    rule_at = {(b["label"], b["node"]): b for b in R["bindings"] if b["node"] is not None and b["rule"] not in ("through_mark", "propagated")}
    by_stretch = defaultdict(list)
    for b in bindings:
        if b["rule"] == "fable" and b["confidence"] == "high":
            by_stretch[b["stretch"]].append(b)
    for sid_, bs in by_stretch.items():
        if len({b["label"] for b in bs}) < 2:
            continue
        for b in bs:
            rb = rule_at.get((b["label"], b["node"]))
            if rb and rb["stretch"] != sid_ and rb["stretch"] not in owner:
                b["stretch"] = rb["stretch"]; b["reason"] += f"; moved to stretch {rb['stretch']} - the rules' choice, another label's decision names the same piece"
                owner[rb["stretch"]] = b["id"]
                if owner.get(sid_) == b["id"]:
                    del owner[sid_]
                    other = next((x for x in bs if x is not b), None)
                    if other is not None:
                        owner[sid_] = other["id"]
                break
    leader_nodes = {lg["node"] for ld in R["leaders"] for lg in ld["landings"]
                    if lg["node"] is not None and lg.get("binds", True)
                    and _is_designation(labels[ld["label"]])}
    ladder_nodes = {g["node"] for ld in R["leaders"] for g in ld["landings"] if g.get("ladder") and g.get("node") is not None}
    kw = dict(landing_nodes=leader_nodes, solid_only=r1_labels(L), split_only=split_form_labels(L), entry_dist=_entry_distances(nodes, stretches, ladder_nodes), label_sys=label_systems(L))
    propagate(bindings, owner, nodes, stretches, **kw)
    # the pair's second pipe runs beside propagated pieces: twins after the spread,
    # then spread the twins (the stored rule twins were dropped above when their
    # partner was not a landing piece - 0111 at (795,566), the VP1 return)
    from shapely.geometry import LineString
    from shapely.strtree import STRtree
    for s_ in stretches.values():
        s_["_geom"] = LineString(s_["points"])
    ink_ids = list(stretches); itree = STRtree([stretches[k]["_geom"] for k in ink_ids])
    add_twins(bindings, owner, stretches, labels, itree, ink_ids, twin_gap=R.get("tolerances", {}).get("twin_gap", 20.0), twin_axis=R.get("tolerances", {}).get("twin_axis", 5.0))
    propagate(bindings, owner, nodes, stretches, **kw)
    for s_ in stretches.values():
        s_.pop("_geom", None)
    return bindings



