"""
Turn a description into a rideable outline: Claude proposes, measurement disposes.

A user types 一隻貓 or "a sailboat" and gets a shape. The model is the only part
that can invent an outline; it is not the part that decides whether the outline
is any good. Everything this project has learned about what breaks is a check
here, and a proposal that fails one goes back to the model with the reason.

The checks are the record of actual failures:

  SELF-INTERSECTION. Three of the twelve hand-drawn shapes crossed themselves -
  the umbrella twice, the quaver's stem through its head, the key's ring through
  its shaft. Every one was a body-with-an-appendage drawn as separate runs of
  points. A closed outline has exactly one non-crossing path, and looking at the
  picture is what caught it, so the machine has to look now.

  HOLES ARE IMPOSSIBLE. A key needs its hole, a ring needs its centre; a single
  closed curve cannot have one. The model is told to solve this the way the cat
  solved it - pick a subject whose silhouette carries the identity - rather than
  emitting two contours.

  DETAIL COSTS DISTANCE. n_min x street_scale x detour is the floor, and the
  detour itself grows with size (POC 25). A gorgeous outline needing 200 km is
  not a shape this product has. The leaf's full venation died here.

  IDENTITY MUST BE IN THE OUTLINE (POC 20). No portraits, no faces, nothing
  whose identity is tone. This one cannot be checked mechanically, so it is
  pushed into the prompt and into the examples.

What is NOT checked: whether anyone will recognise the result. POC 29 measured
that per shape and found nothing predicts it from geometry, so a generated shape
carries the pooled threshold and the service says it is unmeasured.

WHICH MODEL draws the outline is a swappable back end, because none of the
above depends on it. Two are wired:

  copilot   the GitHub Copilot SDK (`pip install github-copilot-sdk`), which
            works off a GitHub account with Copilot - including Copilot Free -
            and downloads its own runtime. This is the DEFAULT.
  anthropic the Anthropic SDK, needing ANTHROPIC_API_KEY or an `ant auth
            login` profile.

Note for anyone tempted: pointing this at the private endpoint behind the
Copilot IDE extensions is against GitHub's terms, which license Copilot for use
in Copilot products. The SDK below is the supported route and needs no scraped
token. GitHub Models, which used to be the free option, was retired on
2026-07-30.

Without credentials `propose` raises and the caller falls back to the built-in
library.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

DEFAULT_BACKEND = "copilot"
ANTHROPIC_MODEL = "claude-opus-5"
COPILOT_TIMEOUT_S = 180.0
MAX_POINTS = 160
MIN_POINTS = 6
# A shape nobody will ride is not a shape we have. 120 km is already a long day.
MAX_FLOOR_KM = 120.0
ATTEMPTS = 3

SYSTEM = """\
You design closed outlines that a cyclist will ride on real streets, so the \
route traces the shape on a map.

Return ONE closed polygon: an ordered list of [x, y] vertices. The last point \
joins back to the first - do not repeat it. y is up. Any scale; it gets \
normalised.

Hard constraints, each from a real failure:

1. The path must NOT cross itself anywhere. A shape with a handle, a stem, a \
tail or a limb has to be drawn as one continuous boundary that goes out along \
one side of the appendage and back along the other. Do not draw the body and \
then the appendage as separate strokes.

2. There is exactly one contour. No holes, no separate pieces. A key's hole, a \
ring's centre, a letter's counter cannot be represented. If the subject needs a \
hole to be itself, say so instead of emitting a broken outline.

3. The identity must live in the SILHOUETTE. A route is a single line with no \
shading, no colour and no interior detail except lines the route can walk out \
along and back. Faces, portraits and anything recognised by its tone will not \
work.

4. Detail costs distance. Every fine feature raises the minimum ride. Use the \
fewest vertices that carry the identity - typically 12 to 60. A 200-vertex \
masterpiece is unrideable.

Return JSON only: {"name": "<short_ascii_name>", "label": "<短中文名>", \
"points": [[x, y], ...], "note": "<one sentence on what carries the identity>"}

If the subject cannot work as a silhouette, return \
{"error": "<why, in one sentence>"} instead."""


@dataclass
class Check:
    ok: bool
    problems: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _segments_cross(p1, p2, p3, p4) -> bool:
    """Proper crossing of two open segments; touching at an endpoint is fine."""
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    # STRICT straddling: all four orientations non-zero, opposite in pairs.
    # Two weaker rules were tried and both rejected correct shapes. Counting
    # collinear overlap banned the out-and-back that draws an interior line at
    # all - the leaf's midrib, every multi_contour connector. Counting
    # `d1 != d2` alone treats a zero orientation as different from a non-zero
    # one, so a vertex lying exactly ON another segment reads as a crossing:
    # the leaf's tip is visited by the blade, the stem and the midrib, and that
    # produced ten phantom crossings in a shape that is perfectly sound.
    # Touching is legal here; only genuinely passing through is not.
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def self_intersections(points: np.ndarray) -> list:
    """Indices of segment pairs that cross. Adjacent pairs are skipped."""
    n = len(points)
    hits = []
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            c, d = points[j], points[(j + 1) % n]
            if _segments_cross(a, b, c, d):
                hits.append((i, j))
    return hits


def check(points, mode: str = "bike", street_scale_m: float | None = None) -> Check:
    """Everything the project knows about what makes an outline unusable."""
    problems = []
    try:
        pts = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return Check(False, ["points are not numbers"])
    if pts.ndim != 2 or pts.shape[1] != 2:
        return Check(False, ["points must be a list of [x, y] pairs"])
    if not np.isfinite(pts).all():
        return Check(False, ["points contain NaN or infinity"])
    # Drop repeated consecutive vertices, including a last point that repeats
    # the first. The convention is that the outline closes implicitly, and a
    # duplicate makes a zero-length segment that the crossing test reports as
    # an intersection with everything - four of the twelve hand-drawn shapes
    # tripped it, all of them fine to look at. Harmless to render, so it is
    # cleaned rather than refused.
    keep = [0] + [i for i in range(1, len(pts))
                  if not np.allclose(pts[i], pts[i - 1])]
    pts = pts[keep]
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < MIN_POINTS:
        problems.append(f"only {len(pts)} vertices; needs at least {MIN_POINTS}")
    if len(pts) > MAX_POINTS:
        problems.append(f"{len(pts)} vertices is more detail than a route can "
                        f"carry; keep it under {MAX_POINTS}")
    span = pts.max(axis=0) - pts.min(axis=0)
    if min(span) <= 0:
        problems.append("the outline is flat - it has no area")
        return Check(False, problems)
    if max(span) / min(span) > 8:
        problems.append(f"aspect ratio {max(span) / min(span):.0f}:1 is too "
                        f"extreme to place on a street network")
    if problems:
        return Check(False, problems)

    crossings = self_intersections(pts)
    if crossings:
        where = ", ".join(f"segment {i}-{i + 1} crosses {j}-{j + 1}"
                          for i, j in crossings[:4])
        problems.append(f"the outline crosses itself ({len(crossings)} places): "
                        f"{where}. Redraw it as one continuous boundary.")

    metrics = {"vertices": int(len(pts)), "crossings": len(crossings)}
    if not problems:
        # Only ask the expensive question once the cheap ones pass.
        import route_feasibility as rf
        import shape_library as sl
        # A unique name per candidate. rf.n_min is memoised ON THE NAME, so
        # reusing one returned the first candidate's answer for every shape
        # after it - cat, Taiwan and a plane all came back n_min 36. The
        # numbers were wrong and looked plausible, which is the whole problem.
        name = f"_candidate_{abs(hash(pts.tobytes())):x}"
        sl.register(name, pts)
        try:
            n_min = rf.n_min(name)
            floor = rf.min_distance_km(name, mode, street_scale_m)
        finally:
            sl.SHAPES.pop(name, None)
        metrics.update({"n_min": int(n_min), "min_km": round(float(floor), 1)})
        if floor > MAX_FLOOR_KM:
            problems.append(
                f"too much fine detail: this needs a {floor:.0f} km ride "
                f"(n_min {n_min}). Simplify until it fits in {MAX_FLOOR_KM:.0f} km "
                f"- remove small features, not overall size.")
    return Check(not problems, problems, metrics)


def _ask_anthropic(system: str, messages: list, client=None) -> str:
    import anthropic
    client = client or anthropic.Anthropic()
    response = client.messages.create(
        model=ANTHROPIC_MODEL, max_tokens=8000, system=system,
        thinking={"type": "adaptive"}, output_config={"effort": "medium"},
        messages=messages)
    return "".join(b.text for b in response.content if b.type == "text")


def _ask_copilot(system: str, messages: list, client=None) -> str:
    """One turn through the Copilot SDK.

    The SDK drives an agent, not a bare completion, so the session is stripped
    down to a plain text turn: no tools, no config discovery, no skills. The
    system prompt is installed in "replace" mode because the default appends to
    the SDK's own coding-assistant guardrails, which have nothing to say about
    drawing outlines and crowd out the instructions that do.

    Conversation is re-sent as one prompt rather than as turns: the retry loop
    here is short and the alternative is holding a live session open across
    validations.
    """
    import asyncio

    import copilot

    parts = []
    for m in messages:
        parts.append(("USER:\n" if m["role"] == "user" else "YOUR PREVIOUS REPLY:\n")
                     + m["content"])
    prompt = "\n\n".join(parts)

    async def run() -> str:
        cl = copilot.CopilotClient(log_level="error")
        await cl.start()
        try:
            status = await cl.get_auth_status()
            if not getattr(status, "isAuthenticated", False):
                raise RuntimeError(
                    "Copilot is not authenticated. Run `copilot` once and sign "
                    "in, or set GH_TOKEN / GITHUB_TOKEN to a token on an "
                    "account with Copilot.")
            session = await cl.create_session(
                available_tools=[],
                system_message={"mode": "replace", "content": system},
                enable_config_discovery=False,
                enable_skills=False,
                skip_custom_instructions=True,
            )
            event = await session.send_and_wait(prompt, timeout=COPILOT_TIMEOUT_S)
            # assistant.message carries AssistantMessageData.content - read off
            # the SDK's own generated types rather than guessed.
            data = getattr(event, "data", None)
            text = getattr(data, "content", None)
            if not isinstance(text, str):
                raise RuntimeError(
                    f"unexpected Copilot event {getattr(event, 'type', '?')}; "
                    f"no text content")
            return text
        finally:
            try:
                await cl.stop()
            except Exception:      # noqa: BLE001 - shutdown must not mask the real error
                pass

    return asyncio.run(run())


BACKENDS = {"copilot": _ask_copilot, "anthropic": _ask_anthropic}


def propose(description: str, mode: str = "bike",
            street_scale_m: float | None = None, client=None,
            backend: str = DEFAULT_BACKEND) -> dict:
    """Ask Claude for an outline, and keep asking until it passes the checks.

    Failures go back as text rather than being silently repaired: the model
    that drew a crossing knows how to redraw it, and a repair here would be
    this file inventing shape design, which is the model's job.
    """
    ask = BACKENDS.get(backend)
    if ask is None:
        raise ValueError(f"unknown backend {backend!r}; have {sorted(BACKENDS)}")
    messages = [{"role": "user", "content": f"Design an outline for: {description}"}]
    last = None
    for attempt in range(ATTEMPTS):
        text = ask(SYSTEM, messages, client)
        try:
            data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": "That was not JSON. Return only the JSON object."}]
            continue
        if "error" in data:
            return {"status": "unsuitable", "reason": data["error"]}
        verdict = check(data.get("points", []), mode, street_scale_m)
        last = {"data": data, "check": verdict}
        if verdict.ok:
            return {"status": "ok", "name": data.get("name", "custom"),
                    "label": data.get("label", description[:12]),
                    "note": data.get("note", ""), "points": data["points"],
                    "metrics": verdict.metrics, "attempts": attempt + 1}
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "That outline fails these checks:\n- "
             + "\n- ".join(verdict.problems) + "\nRedraw it and return only JSON."},
        ]
    return {"status": "failed",
            "reason": "; ".join(last["check"].problems) if last else "no valid proposal",
            "attempts": ATTEMPTS}
