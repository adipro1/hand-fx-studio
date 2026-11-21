"""Loads, pre-processes (#include) and caches GLSL programs."""
from __future__ import annotations

import os
import re

import moderngl
import numpy as np

SHADER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shaders")
_INCLUDE = re.compile(r"^\s*//#include\s+(\w+)\s*$", re.MULTILINE)


class ShaderError(RuntimeError):
    pass


class ShaderManager:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self._cache: dict[tuple[str, str], moderngl.Program] = {}

    @staticmethod
    def load_source(name: str, _seen: set | None = None) -> str:
        with open(os.path.join(SHADER_DIR, name), "r", encoding="utf-8") as fh:
            src = fh.read()
        seen = _seen if _seen is not None else set()

        def repl(m):
            inc = m.group(1)
            if inc in seen:
                return ""
            seen.add(inc)
            return ShaderManager.load_source(inc + ".glsl", seen)

        return _INCLUDE.sub(repl, src)

    def program(self, frag: str, vert: str = "fullscreen.vert") -> moderngl.Program:
        key = (vert, frag)
        prog = self._cache.get(key)
        if prog is None:
            try:
                prog = self.ctx.program(vertex_shader=self.load_source(vert),
                                        fragment_shader=self.load_source(frag))
            except moderngl.Error as exc:
                raise ShaderError(f"Shader compile failed ({vert} + {frag}):\n{exc}") from exc
            self._cache[key] = prog
        return prog

    def compile_all(self) -> None:
        """Compile every effect shader up front so errors surface at start-up."""
        for f in sorted(os.listdir(SHADER_DIR)):
            if f.endswith(".frag") and not f.startswith(("lines", "discs", "tris")):
                self.program(f)
        for name in ("lines", "discs", "tris"):
            self.program(f"{name}.frag", f"{name}.vert")


def set_uniforms(prog: moderngl.Program, values: dict) -> None:
    """Set uniforms present in ``prog``; unknown / optimised-out names are skipped.

    numpy arrays are written raw (int arrays as int32, others as float32) and must
    match the uniform's declared array size.
    """
    for k, v in values.items():
        if k not in prog:
            continue
        u = prog[k]
        if isinstance(v, np.ndarray):
            if v.dtype.kind in "iu":
                u.write(v.astype("i4").tobytes())
            else:
                u.write(v.astype("f4").tobytes())
        elif isinstance(v, bool):
            u.value = int(v)
        else:
            u.value = v


def vec_array(points, size: int, dim: int = 2) -> np.ndarray:
    """Pad/truncate a list of vectors to a fixed-size float32 uniform array."""
    out = np.zeros((size, dim), dtype="f4")
    if points is not None and len(points):
        p = np.asarray(points, dtype="f4").reshape(-1, dim)[:size]
        out[:len(p)] = p
    return out


def int_array(values, size: int) -> np.ndarray:
    out = np.zeros(size, dtype="i4")
    if values is not None and len(values):
        v = np.asarray(values, dtype="i4")[:size]
        out[:len(v)] = v
    return out


def float_array(values, size: int) -> np.ndarray:
    out = np.zeros(size, dtype="f4")
    if values is not None and len(values):
        v = np.asarray(values, dtype="f4")[:size]
        out[:len(v)] = v
    return out
