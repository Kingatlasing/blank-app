"""Let a local Ollama model design a genuinely custom voxel structure,
beyond anything in the fixed shape library.

Two ways to ask it, in order of how well they tend to actually work:

1. **Write code** (the recommended default): ask a *code* model — qwen2.5-
   coder is built for exactly this — to write a small Python function
   against a curated geometry API (box/sphere/cylinder/cone/merge
   primitives), then run that function in a restricted sandbox. This plays
   to what a code model is actually good at, scales to complex shapes
   without the model needing to emit one token per voxel, and produces
   exact/regular geometry (a sphere is actually round).
2. **Hand-enumerate coordinates**: ask the model to directly list
   `[x, y, z, "#hex"]` entries, one per voxel, no code involved. This is
   what you'd get from a model with no code ability at all — simpler, but
   slow, token-expensive, capped much lower (a local chat model trails off
   or gets sloppy well before "thousands" of coordinates), and the
   geometry it produces is whatever the model eyeballs rather than
   something exactly computed. It's offered because it's a real, simpler
   option some people want — not because it works as well.

The code sandbox is defense-in-depth, not a security boundary you'd trust
against a hostile model: no imports, a builtins allowlist, an AST check
that rejects import statements/dunder access/exec-family names, and a
hard wall-clock limit on execution. It assumes what it actually is — your
own local model, on your own machine, that you chose to run.
"""

from __future__ import annotations

import ast
import concurrent.futures
import math
import re

import requests

from .palette import PALETTE, hex_of

Voxel = tuple[int, int, int, str]

_CHAT_TIMEOUT_S = 120   # local code-gen models can be slow on modest hardware
_EXEC_TIMEOUT_S = 5     # the generated code itself must run fast
_MAX_VOXELS = 20_000    # a generous budget before the app's own chunkiness scaling
_DIRECT_MAX_VOXELS = 6_000  # hand-enumerated: capped much lower, see module docstring

_PALETTE_NAMES = sorted(s.name for s in PALETTE)

_SYSTEM_PROMPT = f"""You are a 3D voxel structure designer for a Minecraft-style builder.
Write a single Python function named `build` that takes no arguments and
returns a list of (x, y, z, color) tuples — one per voxel — describing a
recognizable 3D model of whatever the user asks for. `y` is up. Design a
genuinely custom structure suited to the request — combine and shape the
primitives below creatively; don't just draw one box or sphere.

You may ONLY use these helpers, already in scope. Write no import
statements, no classes, no file or network access:

- box(x0, x1, y0, y1, z0, z1, color) -> list of voxels filling that range
  (each bound is exclusive on the high end, like Python's range)
- hollow_box(x0, x1, y0, y1, z0, z1, color) -> like box, but only the
  outer shell plus a solid bottom layer (use for walls/rooms with a floor)
- sphere(cx, cy, cz, radius, color) -> a filled sphere
- cylinder(cx, cz, y0, y1, radius, color) -> a filled vertical cylinder
  from y0 to y1
- cone(cx, cz, y0, y1, radius0, color) -> a cone tapering from radius0 at
  y0 to a point at y1
- merge(*voxel_lists) -> combines lists; later ones paint over earlier
  ones at the same coordinate
- color(name) -> hex string for a named color. Valid names:
  {", ".join(_PALETTE_NAMES)}
- the `math` module (sin, cos, pi, sqrt, radians, ...) is already available

Keep the whole model within roughly -30..30 on every axis and under
{_MAX_VOXELS} total voxels. Reply with ONLY one Python code block
(```python ... ```) defining `build`. No explanation before or after it."""

_DIRECT_SYSTEM_PROMPT = f"""You are a 3D voxel structure designer for a Minecraft-style builder.
List every voxel of a recognizable 3D model of whatever the user asks
for, one per line, each formatted EXACTLY like: [x, y, z, "#RRGGBB"]
`y` is up. Use plain integers for x/y/z and a 6-digit hex color in quotes.
Keep the whole model within roughly -20..20 on every axis and under
{_DIRECT_MAX_VOXELS} voxels total. Reply with ONLY the voxel list, one
entry per line, no explanation, no markdown fences, no surrounding
brackets or commas between lines — just the entries themselves."""


class LLMBuildError(RuntimeError):
    """Raised for any failure researching/generating/executing the LLM's
    design — the caller is expected to catch this and fall back."""


def _ollama_chat(prompt: str, model: str, host: str, system_prompt: str) -> str:
    try:
        resp = requests.post(
            f"{host.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Design: {prompt}"},
                ],
                "stream": False,
            },
            timeout=_CHAT_TIMEOUT_S,
        )
    except requests.exceptions.ConnectionError as exc:
        raise LLMBuildError(f"Couldn't reach Ollama at {host}. Is `ollama serve` running?") from exc
    except requests.exceptions.Timeout as exc:
        raise LLMBuildError(f"Ollama didn't respond within {_CHAT_TIMEOUT_S}s.") from exc

    if resp.status_code == 404:
        raise LLMBuildError(f"Model '{model}' not found on this Ollama server. Run `ollama pull {model}` first.")
    resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    if not content:
        raise LLMBuildError("Ollama returned an empty response.")
    return content


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    code = (m.group(1) if m else text).strip()
    if "def build" not in code:
        raise LLMBuildError("The model's response didn't define a `build()` function.")
    return code


_FORBIDDEN_NAMES = {
    "exec", "eval", "compile", "open", "__import__", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "input", "breakpoint",
}


def _precheck_code(code: str) -> None:
    """AST-level defense in depth: reject imports, dunder attribute access,
    and exec-family names before we ever run the code."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise LLMBuildError(f"The generated code has a syntax error: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise LLMBuildError("Generated code tried to import a module, which isn't allowed.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise LLMBuildError("Generated code tried to access a dunder attribute, which isn't allowed.")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise LLMBuildError(f"Generated code referenced '{node.id}', which isn't allowed.")


# --- the geometry API the sandboxed code gets to call ---------------------

def _box(x0, x1, y0, y1, z0, z1, c) -> list[Voxel]:
    x0, x1, y0, y1, z0, z1 = (int(v) for v in (x0, x1, y0, y1, z0, z1))
    return [(x, y, z, c) for x in range(x0, x1) for y in range(y0, y1) for z in range(z0, z1)]


def _hollow_box(x0, x1, y0, y1, z0, z1, c) -> list[Voxel]:
    x0, x1, y0, y1, z0, z1 = (int(v) for v in (x0, x1, y0, y1, z0, z1))
    out = []
    for x in range(x0, x1):
        for y in range(y0, y1):
            for z in range(z0, z1):
                if x in (x0, x1 - 1) or y in (y0, y1 - 1) or z in (z0, z1 - 1):
                    out.append((x, y, z, c))
    return out


def _sphere(cx, cy, cz, r, c) -> list[Voxel]:
    cx, cy, cz, r = float(cx), float(cy), float(cz), float(r)
    ir = int(math.ceil(r))
    out = []
    for x in range(int(cx - ir), int(cx + ir) + 1):
        for y in range(int(cy - ir), int(cy + ir) + 1):
            for z in range(int(cz - ir), int(cz + ir) + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2 <= r * r:
                    out.append((x, y, z, c))
    return out


def _cylinder(cx, cz, y0, y1, r, c) -> list[Voxel]:
    cx, cz, r = float(cx), float(cz), float(r)
    y0, y1 = int(y0), int(y1)
    ir = int(math.ceil(r))
    out = []
    for x in range(int(cx - ir), int(cx + ir) + 1):
        for z in range(int(cz - ir), int(cz + ir) + 1):
            if (x - cx) ** 2 + (z - cz) ** 2 <= r * r:
                out.extend((x, y, z, c) for y in range(y0, y1))
    return out


def _cone(cx, cz, y0, y1, r0, c) -> list[Voxel]:
    cx, cz, r0 = float(cx), float(cz), float(r0)
    y0, y1 = int(y0), int(y1)
    out = []
    height = max(1, y1 - y0)
    for y in range(y0, y1):
        r = max(0.0, r0 * (1 - (y - y0) / height))
        ir = int(math.ceil(r))
        for x in range(int(cx - ir), int(cx + ir) + 1):
            for z in range(int(cz - ir), int(cz + ir) + 1):
                if (x - cx) ** 2 + (z - cz) ** 2 <= r * r:
                    out.append((x, y, z, c))
    return out


def _merge(*groups) -> list[Voxel]:
    seen: dict[tuple[int, int, int], str] = {}
    for g in groups:
        for v in g:
            seen[(v[0], v[1], v[2])] = v[3]
    return [(x, y, z, c) for (x, y, z), c in seen.items()]


_SAFE_BUILTINS = {
    "range": range, "len": len, "min": min, "max": max, "abs": abs,
    "round": round, "enumerate": enumerate, "int": int, "float": float,
    "list": list, "tuple": tuple, "sum": sum, "zip": zip, "sorted": sorted,
    "True": True, "False": False, "None": None,
}


def _run_sandboxed(code: str) -> list[Voxel]:
    scope = {
        "box": _box, "hollow_box": _hollow_box, "sphere": _sphere,
        "cylinder": _cylinder, "cone": _cone, "merge": _merge, "color": hex_of,
        "math": math, "__builtins__": _SAFE_BUILTINS,
    }

    def _target():
        exec(compile(code, "<ollama_build>", "exec"), scope)
        build_fn = scope.get("build")
        if not callable(build_fn):
            raise LLMBuildError("No callable `build()` was defined.")
        return build_fn()

    # Deliberately not a `with` block: ThreadPoolExecutor.__exit__ calls
    # shutdown(wait=True), which would block this call — and the whole
    # app — until the runaway thread finishes, i.e. forever. We give up on
    # it after the timeout instead and let it leak; a stuck sandboxed loop
    # is bounded to a single CPU core, whereas hanging every future request
    # behind it is a full app outage.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_target)
    try:
        result = future.result(timeout=_EXEC_TIMEOUT_S)
    except concurrent.futures.TimeoutError as exc:
        pool.shutdown(wait=False)
        raise LLMBuildError(
            f"The generated code didn't finish within {_EXEC_TIMEOUT_S}s (likely stuck in a loop)."
        ) from exc
    except LLMBuildError:
        pool.shutdown(wait=False)
        raise
    except Exception as exc:
        pool.shutdown(wait=False)
        raise LLMBuildError(f"The generated code raised an error: {exc}") from exc
    else:
        pool.shutdown(wait=False)

    if not isinstance(result, list) or not result:
        raise LLMBuildError("build() didn't return a non-empty list of voxels.")

    voxels: list[Voxel] = []
    for item in result:
        if not (isinstance(item, (tuple, list)) and len(item) == 4):
            continue
        x, y, z, c = item
        if not (isinstance(c, str) and c.startswith("#")):
            continue
        try:
            voxels.append((int(x), int(y), int(z), c))
        except (TypeError, ValueError):
            continue
    if not voxels:
        raise LLMBuildError("build() returned data, but none of it was valid (x, y, z, '#hex') voxels.")
    return voxels[:_MAX_VOXELS]


def generate_llm_structure(
    prompt: str, model: str = "qwen2.5-coder", host: str = "http://localhost:11434",
) -> tuple[list[Voxel], str, str]:
    """Returns (voxels, description, generated_code). Raises LLMBuildError
    on any failure — the caller decides whether/how to fall back."""
    raw = _ollama_chat(prompt, model, host, _SYSTEM_PROMPT)
    code = _extract_code(raw)
    _precheck_code(code)
    voxels = _run_sandboxed(code)
    return voxels, f"Designed a custom structure with {model} via Ollama (wrote code for it).", code


# entries like [3, -1, 12, "#B02E26"], tolerant of markdown fences, stray
# commentary, or a truncated final line — we just scan for the pattern
# rather than requiring the whole response to be one valid JSON document
_VOXEL_LINE_RE = re.compile(
    r'\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*"(#[0-9a-fA-F]{6})"\s*\]'
)


def generate_llm_structure_direct(
    prompt: str, model: str = "qwen2.5-coder", host: str = "http://localhost:11434",
) -> tuple[list[Voxel], str]:
    """The simpler, weaker alternative to `generate_llm_structure`: has the
    model hand-enumerate (x, y, z, color) voxels directly instead of
    writing code. Returns (voxels, description). Raises LLMBuildError on
    any failure — the caller decides whether/how to fall back."""
    raw = _ollama_chat(prompt, model, host, _DIRECT_SYSTEM_PROMPT)
    matches = _VOXEL_LINE_RE.findall(raw)
    if not matches:
        raise LLMBuildError(
            "Couldn't find any valid [x, y, z, \"#hex\"] voxel entries in the model's response."
        )
    voxels: list[Voxel] = [(int(x), int(y), int(z), c) for x, y, z, c in matches]
    truncated = len(voxels) > _DIRECT_MAX_VOXELS
    voxels = voxels[:_DIRECT_MAX_VOXELS]
    note = f"Hand-enumerated {len(voxels)} voxel coordinates with {model} via Ollama, one at a time."
    if truncated:
        note += f" (capped at {_DIRECT_MAX_VOXELS} — this method doesn't scale to very large models.)"
    return voxels, note
