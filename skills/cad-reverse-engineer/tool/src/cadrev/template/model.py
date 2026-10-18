"""Parametric model. Reads every dimension from p (params.yaml); holds no dimension literals."""

from build123d import *  # noqa: F403


def build(p):
    parts = {}
    datums = {}
    assembly = {}
    return {"parts": parts, "datums": datums, "assembly": assembly}
