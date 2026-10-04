"""Pipeline ordering, dependency closure and caching checks (synthetic steps)."""

import pytest

from factor_weaver.data import pipeline


def _step(name, phase, calls, ins=(), outs=(), per_item=False):
    def run(cfg):
        calls.append(name)

    return pipeline.Step(name, run, phase, ins=ins, outs=outs, per_item=per_item)


def test_run_executes_manifest_order_and_pulls_missing_prerequisites(monkeypatch, tmp_path):
    calls = []
    steps = (
        _step("a", "build", calls, outs=("a.out",)),
        _step("b", "build", calls, ins=("a.out",), outs=("b.out",)),
        _step("c", "build", calls, ins=("b.out",), outs=("c.out",)),
    )
    monkeypatch.setattr(pipeline, "STEPS", steps)
    cfg = {"a": {"out": tmp_path / "a"}, "b": {"out": tmp_path / "b"}, "c": {"out": tmp_path / "c"}}
    assert pipeline.run(cfg, ["c", "a"]) == ["a", "b", "c"]
    assert calls == ["a", "b", "c"]


def test_fetch_step_with_output_skipped_unless_refreshed(monkeypatch, tmp_path):
    calls = []
    out = tmp_path / "x.parquet"
    out.touch()
    monkeypatch.setattr(pipeline, "STEPS", (_step("x", "fetch", calls, outs=("x.out",)),))
    cfg = {"x": {"out": out}}
    assert pipeline.run(cfg) == []
    assert calls == []
    assert pipeline.run(cfg, refresh=True) == ["x"]
    assert calls == ["x"]


def test_per_item_fetch_step_always_runs(monkeypatch, tmp_path):
    calls = []
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(
        pipeline, "STEPS", (_step("p", "fetch", calls, outs=("p.out",), per_item=True),)
    )
    cfg = {"p": {"out": cache}}
    assert pipeline.run(cfg) == ["p"]
    assert calls == ["p"]


def test_fetch_phase_pulls_build_prerequisite(monkeypatch, tmp_path):
    calls = []
    steps = (
        _step("base", "build", calls, outs=("base.out",)),
        _step("net", "fetch", calls, ins=("base.out",), outs=("net.out",)),
    )
    monkeypatch.setattr(pipeline, "STEPS", steps)
    cfg = {"base": {"out": tmp_path / "base"}, "net": {"out": tmp_path / "net"}}
    assert pipeline.run(cfg, phase="fetch") == ["base", "net"]
    assert calls == ["base", "net"]


def test_unknown_step_is_rejected(monkeypatch):
    monkeypatch.setattr(pipeline, "STEPS", (_step("x", "build", [], outs=("x.out",)),))
    with pytest.raises(SystemExit, match="unknown build step"):
        pipeline.run({"x": {"out": "nope"}}, ["y"], phase="build")
