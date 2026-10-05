"""Workflow model selection: registry dispatch and name validation."""

import argparse
import logging

import pytest

from factor_weaver import models
from factor_weaver.workflows import evaluate, train


def test_train_rejects_unknown_model():
    with pytest.raises(SystemExit, match="not trainable"):
        train.run({}, argparse.Namespace(model="mystery"))


def test_eval_rejects_unknown_model():
    with pytest.raises(SystemExit, match="unknown model"):
        evaluate.select(argparse.Namespace(models=["mystery"]))


def test_eval_selects_all_registered_by_default():
    assert evaluate.select(argparse.Namespace(models=[])) == list(models.REGISTRY)


def test_rl_without_checkpoint_errors_when_explicit_and_skips_when_implicit(caplog):
    args = argparse.Namespace(models=["rl"], checkpoint=None, start=None, end=None)
    with pytest.raises(SystemExit, match="needs a checkpoint"):
        evaluate.run({"rl": {}}, args)
    args.models = []
    with caplog.at_level(logging.WARNING):
        evaluate.run({"rl": {}}, args)
    assert "skipping rl" in caplog.text
