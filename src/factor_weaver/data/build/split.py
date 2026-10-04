"""Train/test split of the panel by date window."""

import logging

log = logging.getLogger(__name__)


def split_dataset(cfg: dict) -> None:
    """Split the panel into train/test by date window.

    Reads: <panel.out>
    Writes: <split.train_out>, <split.test_out>
    """
    log.warning("split: not implemented yet; no output written")
