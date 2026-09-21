"""The agent that works against a finished reading.

The division the whole thing rests on: the model decides what to ask, the engine decides what the answer is.
Every number the agent says comes out of a tool call into the measuring pipeline's own artifacts, so an answer in
the chat and an answer in the takeoff table cannot disagree. The model never sees geometry it could invent from -
it sees the names of tools and the results they return.

A turn is bounded: at most a handful of tool rounds. Some tools propose a change rather than report a fact,
and a proposal is still only words: it says which correction it would write and what the reading says that would
cost, and nothing is recorded until a person accepts it. Accepting runs the same call again on the server and
writes what comes out, so the metres in the log are the reading's, never the model's.
"""
from __future__ import annotations

import json
from typing import Any

MAX_ROUNDS = 6
MAX_RESULT_CHARS = 6000


# What a result carries for the interface but not for the answer: identifiers to light up, source objects,
# geometry. Sending them to the model buries the numbers it was asked for - a takeoff of six systems came back
# with two hundred pipe ids around it, and the model called the same tool nine times without ever answering.
FOR_THE_SCREEN = ("ror_id", "pipe_ids", "kallobjekt", "source_path_ids", "segments", "geometry",
                  "graph_nodes", "stodjande_ankare", "bevis", "ställen", "points")
LIST_CAP = 40


def _trim(obj: Any) -> Any:
    """The same result with what only the screen needs taken out, so the answer is what the model sees."""
    if isinstance(obj, dict):
        out = {k: _trim(v) for k, v in obj.items() if k not in FOR_THE_SCREEN}
        return out
    if isinstance(obj, list):
        head = [_trim(v) for v in obj[:LIST_CAP]]
        return head + [f"…({len(obj) - LIST_CAP} till)"] if len(obj) > LIST_CAP else head
    return obj


def _clip(obj: Any) -> str:
    s = json.dumps(_trim(obj), ensure_ascii=False)
    return s if len(s) <= MAX_RESULT_CHARS else s[:MAX_RESULT_CHARS] + " …(avkortat)"


ROLES = ("user", "assistant", "system", "developer")


def _history(items: list[dict] | None) -> list[dict]:
    """Vad som sagts tidigare, i den form modellen tar emot.

    Historiken kommer utifrån - en webbsida skickar den - och får aldrig gå vidare som den är. En rad utan roll
    blev en roll modellen inte känner igen, och hela turen föll med ett 502 innan frågan ens ställdes. Här läses
    bara det som går att läsa: en roll av de fyra som finns (agentens egen heter assistant), en text som är text,
    och rader som inte säger något hoppas över i stället för att fälla svaret.
    """
    out: list[dict] = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        role = str(it.get("role") or it.get("roll") or "").strip().lower()
        role = {"agent": "assistant", "svar": "assistant", "fraga": "user", "fråga": "user"}.get(role, role)
        if role not in ROLES:
            role = "user"
        text = it.get("content")
        if not isinstance(text, str):
            text = it.get("text")
        text = (text or "").strip() if isinstance(text, str) else ""
        if not text:
            continue
        out.append({"role": role, "content": text})
    return out[-20:]


def run_turn(model, ask, question: str, selection: dict | None = None,
             history: list[dict] | None = None, tools=None) -> dict:
    """One question, answered through the tools. Returns the words, the calls made and what to light up.

    `tools` is the registry the model may call - the drawing's by default, the project's for the project agent.
    The loop is the same either way: the model chooses, the registry answers, nothing else can.
    """
    from vvs_engine.agent import tools as _drawing_tools
    T = tools or _drawing_tools

    lines = [question.strip()]
    if selection:
        ids = selection.get("pipe_ids") or []
        box = selection.get("bbox")
        page = selection.get("page")
        bits = []
        if ids:
            bits.append(f"markerade rör: {', '.join(ids[:40])}")
        if box:
            bits.append(f"markerat område: [{', '.join(str(round(float(v), 1)) for v in box)}]")
        if page is not None:
            bits.append(f"sida: {page}")
        if bits:
            lines.append("\n[Användarens markering] " + "; ".join(bits))

    items: list[dict] = _history(history)
    items.append({"role": "user", "content": "\n".join(lines)})

    used: list[dict] = []
    prev: str | None = None
    for _ in range(MAX_ROUNDS):
        out = ask(items, T.schemas(), prev)
        prev = out.get("id")
        calls = out.get("calls") or []
        if not calls:
            return {"svar": out.get("text") or "", "verktyg": used, "markera": _highlights(used)}
        # only what is new goes back: the model keeps its own place in the conversation through the chain
        items = []
        for c in calls:
            try:
                args = json.loads(c.get("arguments") or "{}")
            except Exception:
                args = {}
            result = T.run(c.get("name") or "", model, args)
            used.append({"namn": c.get("name"), "argument": args, "resultat": result})
            items.append({"type": "function_call_output", "call_id": c.get("call_id"),
                          "output": _clip(result)})
    called = ", ".join(dict.fromkeys(u["namn"] for u in used))
    return {"svar": f"Jag hämtade svaret ({called}) men kom inte fram till en formulering inom "
                    f"{MAX_ROUNDS} steg. Siffrorna finns under verktygsanropen nedan.",
            "verktyg": used, "markera": _highlights(used)}


def _highlights(used: list[dict]) -> dict:
    """Everything the answer rests on, so a claim on screen can be pointed at on the sheet."""
    pipe_ids: list[str] = []
    boxes: list[list[float]] = []
    # Every list a tool can return that names a run or a place on the sheet. A tool that finds twenty-eight size
    # frontiers and lights up nothing is an answer you cannot point at, which is the one thing this must not be.
    LISTS = ("ror", "stracker", "vag", "granser", "andar", "stallen", "beteckningar", "fall")
    for u in used:
        r = u.get("resultat") or {}
        for key in LISTS:
            for row in (r.get(key) or []):
                if not isinstance(row, dict):
                    continue
                if row.get("pipe_id"):
                    pipe_ids.append(row["pipe_id"])
                pipe_ids.extend(i for i in (row.get("pipe_ids") or []) if isinstance(i, str))
                if row.get("bbox"):
                    boxes.append(row["bbox"])
        if r.get("pipe_id"):
            pipe_ids.append(r["pipe_id"])
        pipe_ids.extend(i for i in (r.get("pipe_ids") or []) if isinstance(i, str))
    seen: set[str] = set()
    ids = [i for i in pipe_ids if not (i in seen or seen.add(i))]
    return {"ror_id": ids[:400], "rutor": boxes[:400]}
