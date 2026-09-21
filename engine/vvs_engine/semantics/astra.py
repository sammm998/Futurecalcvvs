"""A second reader for cases the drawing leaves genuinely open - bounded, verified, and never load-bearing.

The engine answers from the sheet's own geometry. Where it can defend an answer it does not ask anyone, and
where it cannot it says AMBIGUOUS. That is the whole design and this module does not change it. What it adds is
narrow: for a case the engine itself has already declared ambiguous, and where the drawing offers a short list
of real candidates, a language model may say which of THOSE it reads - and its answer is then checked against
the same list before anything happens.

Four properties, each enforced here rather than asked for:

  * **Bounded.** A question carries the candidates the engine found. `verify` refuses any answer that is not one
    of them, character for character. A model cannot name a designation, a family or a run that the reading did
    not already put forward, so it cannot invent a pipe, a leader, a DN, a coordinate or a metre.
  * **Only where the engine gave up.** `settle` never sees a confirmed case. Nothing it returns can overturn a
    reading the engine could defend; it can only turn AMBIGUOUS into one of the answers already on the table.
  * **Optional and offline by default.** Without an `ask` callable this module answers nothing, so the engine is
    deterministic, runs with no network, and produces the same takeoff it always did. Determinism tests and the
    contamination firewall are unaffected because nothing here is reached unless a caller passes a transport.
  * **Its own answer is evidence, not authority.** Every settled case records that a model chose it, from which
    candidates, and why, so a reader can see it and disagree.

Nothing in this module opens a file, a drawing or a reference takeoff. It is given text the caller
already holds, and it hands back a choice among strings the caller supplied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Question:
    """One open case, with the only answers that may be given to it."""
    case_id: str
    kind: str                       # attachment | designation | legend | leader | glyph | fitting
    evidence: str                   # what the reading found, in words the caller composed
    candidates: tuple[str, ...]     # the admissible answers; anything else is refused

    def as_prompt(self) -> str:
        lines = [
            "Ett fall som den geometriska läsningen inte kunde avgöra. Välj EN av kandidaterna, eller svara",
            "OKLART om bevisen inte räcker. Hitta aldrig på ett svar som inte står i listan.",
            "",
            f"typ: {self.kind}",
            "bevis:",
            self.evidence,
            "",
            "kandidater:",
        ]
        lines += [f"  {i + 1}. {c}" for i, c in enumerate(self.candidates)]
        lines += ["", "Svara med exakt en kandidat ordagrant, eller ordet OKLART. Motivera på en rad efter."]
        return "\n".join(lines)


@dataclass
class Answer:
    case_id: str
    choice: str | None              # one of the question's candidates, or None: still ambiguous
    why: str = ""
    raw: str = ""
    refused: str = ""               # why an answer was thrown away, when it was

    def as_dict(self) -> dict[str, Any]:
        return {"case": self.case_id, "choice": self.choice, "why": self.why[:300],
                "refused": self.refused, "source": "language_model_among_the_drawings_own_candidates"}


def verify(q: Question, raw: str) -> Answer:
    """The only door an answer comes through. An answer that is not one of the candidates is not an answer.

    Matching is exact after trimming, and case-insensitive only because a designation is written in one case on
    a drawing and quoted in another in prose. A reply naming two candidates is refused rather than resolved: a
    case a second reader cannot narrow to one is exactly the case that should stay ambiguous.
    """
    text = (raw or "").strip()
    if not text:
        return Answer(q.case_id, None, raw=raw, refused="tomt svar")
    head = text.splitlines()[0].strip().rstrip(".")
    why = " ".join(text.splitlines()[1:]).strip()[:300]
    if head.upper().startswith("OKLART") or "OKLART" in text.upper().split():
        return Answer(q.case_id, None, why=why or head, raw=raw)

    lowered = {c.lower(): c for c in q.candidates}
    hit = lowered.get(head.lower())
    if hit is None:
        # a reply that quotes a candidate inside a sentence is still usable, but only if it names exactly one
        named = [c for c in q.candidates if c.lower() in text.lower()]
        if len(named) != 1:
            return Answer(q.case_id, None, why=why, raw=raw,
                          refused=("svaret nämner flera kandidater" if len(named) > 1
                                   else "svaret är ingen av kandidaterna"))
        hit = named[0]
    return Answer(q.case_id, hit, why=why or head, raw=raw)


def settle(questions: list[Question], ask: Callable[[Question], str] | None = None) -> list[Answer]:
    """Ask, verify, and return only what survived verification.

    With no `ask` this returns nothing at all, which is the default the engine runs under: the reading stands on
    its own geometry and every ambiguous case stays ambiguous.
    """
    if ask is None or not questions:
        return []
    out: list[Answer] = []
    for q in questions:
        if not q.candidates:
            continue                # nothing to choose between: not a question anyone may answer
        try:
            raw = ask(q)
        except Exception as e:      # a second reader that cannot be reached changes nothing
            out.append(Answer(q.case_id, None, refused=f"{type(e).__name__}"))
            continue
        out.append(verify(q, raw))
    return out


@dataclass
class Settlement:
    """What a round of second reading did, kept beside the reading rather than folded into it."""
    answers: list[Answer] = field(default_factory=list)

    @property
    def settled(self) -> dict[str, str]:
        return {a.case_id: a.choice for a in self.answers if a.choice}

    def as_dict(self) -> dict[str, Any]:
        return {"asked": len(self.answers),
                "settled": len(self.settled),
                "refused": sum(1 for a in self.answers if a.refused),
                "left_ambiguous": sum(1 for a in self.answers if not a.choice and not a.refused),
                "answers": [a.as_dict() for a in self.answers]}


# ------------------------------------------------------------------------------------------------------------
# turning the reading's own open cases into bounded questions, and verified answers back into the reading
# ------------------------------------------------------------------------------------------------------------

ASKABLE = ("several_vector_families_at_leader_no_token_discrimination",
           "system_conflict", "multi_row_equal_counts_no_discrimination",
           "multi_row_label_shares_one_run", "multi_row_no_compatible_layer_group")

# En stapel etiketter över ett knippe parallella rör. Här är kandidaterna inte pennor utan *stråk* - de ligger
# i samma penna, på samma lager, och skiljer sig bara i läge. Läsningen har redan försökt para ihop dem efter
# bladets egen radordning och misslyckats; det som står kvar är den mest ordrika sortens tvetydighet vi har,
# och den enda där en läsare har något att titta på som läsningen inte redan vägt.
BUNDLE_ASKABLE = "multi_row_bundle_awaiting_elimination"
RUN = "stråk"                       # kandidatens namn: RUN + mellanslag + ordningsnummer, räknat från 1


def questions_for(anchors: list) -> list[Question]:
    """One question per open attachment case, carrying only families the leader actually touched.

    The candidates are not every family on the sheet: they are the ones this leader's own end landed on. A case
    whose leader touched one family or none is not a choice and is not asked - if the reading could not place a
    label that reached nothing, no amount of reading the evidence again will place it.
    """
    out: list[Question] = []
    for a in anchors:
        if a.state != "AMBIGUOUS_PIPE_ATTACHMENT":
            continue
        if not any(a.reason.startswith(r) for r in ASKABLE):
            continue
        fams = sorted({c.family for c in a.contacts})
        if len(fams) < 2:
            continue
        ev = "\n".join([
            f"beteckning: {a.designation_display or a.designation}",
            f"system enligt etiketten: {a.system_token or '-'}   DN: {a.dn if a.dn is not None else '-'}",
            f"varför läsningen stannade: {a.reason}",
            f"ledarlinjens familj: {(a.evidence or {}).get('leader_family', '-')}",
            f"ledarlinjen slutar i punkten {[round(v, 1) for v in a.endpoint]} och rör dessa familjer:",
        ] + [f"  - {f}  ({sum(1 for c in a.contacts if c.family == f)} kontaktpunkt(er), "
             f"kontakttyp {sorted({c.kind for c in a.contacts if c.family == f})})" for f in fams])
        out.append(Question(case_id=a.anchor_id, kind="attachment", evidence=ev, candidates=tuple(fams)))
    out.extend(q for q in (_bundle_question(a) for a in anchors) if q is not None)
    out.sort(key=lambda q: (q.kind, q.case_id))
    return out


def _bundle_question(a) -> "Question | None":
    """Vilket av knippets stråk den här etiketten i stapeln namnger, beskrivet i läge och inget annat.

    Konventionen - att stapelns rader följer stråkens ordning tvärs knippet - prövas redan av läsningen, och de
    fall som kommer hit är de där den inte räckte. Därför står den inte i frågan: det som står är var etiketten
    sitter i stapeln och var varje stråk går. Säger geometrin ingenting som skiljer stråken åt är OKLART rätt
    svar, och frågan säger det.
    """
    if a.state != "AMBIGUOUS_PIPE_ATTACHMENT" or not (a.reason or "").startswith(BUNDLE_ASKABLE):
        return None
    b = ((a.evidence or {}).get("bundle") or {})
    runs = b.get("runs") or []
    if len(runs) < 2 or b.get("all_rows_agree"):
        return None
    where = {(c.pid, c.seg_index): c.point for c in a.contacts}
    lines = [
        f"beteckning: {a.designation_display or a.designation}",
        f"system enligt etiketten: {a.system_token or '-'}   DN: {a.dn if a.dn is not None else '-'}",
        f"etiketten är rad {int(b.get('pos', 0)) + 1} av {int(b.get('n', len(runs)))} i en stapel över ett knippe",
        f"varför läsningen stannade: {a.reason}",
        f"ledarlinjens familj: {(a.evidence or {}).get('leader_family', '-')}",
        f"ledarlinjen slutar i punkten {[round(v, 1) for v in a.endpoint]}",
        "stråken i knippet, i den ordning de ligger:",
    ]
    for i, r in enumerate(runs):
        pts = [where.get((pid, seg)) for pid, seg in r]
        pts = [p for p in pts if p]
        span = (f"från {[round(v, 1) for v in pts[0]]} till {[round(v, 1) for v in pts[-1]]}" if pts
                else "utan kontaktpunkt vid ledaren")
        lines.append(f"  {RUN} {i + 1}: {len(r)} bit(ar), {span}")
    lines.append("Svara OKLART om läget inte skiljer stråken åt.")
    return Question(case_id=a.anchor_id, kind="bundle", evidence="\n".join(lines),
                    candidates=tuple(f"{RUN} {i + 1}" for i in range(len(runs))))


def apply_answers(anchors: list, answers: list[Answer]) -> list[dict]:
    """Fold verified answers back in, checking each one against the reading a second time.

    `verify` already refused anything that was not a candidate. This checks again at the point of use, because
    the guarantee that matters is not that the answer looked right when it arrived but that the geometry it
    names is geometry this anchor actually touched. An answer that survives both turns the case from ambiguous
    into confirmed, with its contacts narrowed to the family it chose and its origin written into the evidence.
    """
    by_id = {a.anchor_id: a for a in anchors}
    applied: list[dict] = []
    for ans in answers:
        if not ans.choice:
            continue
        a = by_id.get(ans.case_id)
        if a is None or a.state != "AMBIGUOUS_PIPE_ATTACHMENT":
            continue
        if ans.choice.startswith(RUN + " "):
            applied.extend(_apply_bundle(a, ans))
            continue
        keep = [c for c in a.contacts if c.family == ans.choice]
        if not keep:
            continue                # the chosen family is not one this leader touched: refuse at the door too
        a.contacts = keep
        a.candidate_families = [ans.choice]
        a.state = "VERIFIED_PIPE_ATTACHMENT"
        a.reason = "settled_by_second_reader_among_the_drawings_own_candidates"
        a.evidence = dict(a.evidence or {}, second_reader={"chose": ans.choice, "why": ans.why[:200]})
        applied.append({"anchor": a.anchor_id, "chose": ans.choice, "why": ans.why[:200]})
    return applied


def _apply_bundle(a, ans) -> list[dict]:
    """Ett valt stråk smalnar av ankaret till just det stråkets kontakter - och bara om de finns kvar här."""
    runs = ((a.evidence or {}).get("bundle") or {}).get("runs") or []
    try:
        i = int(ans.choice.split()[-1]) - 1
    except ValueError:
        return []
    if not (0 <= i < len(runs)):
        return []
    want = {(pid, seg) for pid, seg in runs[i]}
    keep = [c for c in a.contacts if (c.pid, c.seg_index) in want]
    if not keep:
        return []                   # stråket är inget den här ledaren rörde: neka vid dörren också
    a.contacts = keep
    a.candidate_families = sorted({c.family for c in keep})
    a.state = "VERIFIED_PIPE_ATTACHMENT"
    a.reason = "settled_by_second_reader_among_the_drawings_own_candidates"
    a.evidence = dict(a.evidence or {}, second_reader={"chose": ans.choice, "why": ans.why[:200]})
    return [{"anchor": a.anchor_id, "chose": ans.choice, "why": ans.why[:200]}]
