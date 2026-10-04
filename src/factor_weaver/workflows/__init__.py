"""Workflow subcommands: each exposes add_arguments(sub) and run(cfg, args).

`add_arguments` registers the parser and sets `func` plus the `configs` tuple
of YAML files the workflow needs, e.g. `set_defaults(func=run, configs=("data",))`.
"""
