# Factor Weaver — Agent Guide

**Status: planning stage.** Only documentation exists under `docs/`. No code, no dependencies, no build/test/lint infrastructure.

## Project

Master's thesis: RL framework for portfolio management integrating price, technical, fundamental, and behavioral (attention & sentiment) features. Dynamic top-50 S&P500 universe, actor-critic via PPO, no short-selling, Sharpe maximization under transaction costs.

Expected stack (implied by docs, not yet chosen): Python, PyTorch, Gymnasium, FinRL-family libs.

## Key files

| File | Purpose |
|------|---------|
| `docs/description.md` | Thesis objective, scope, literature list |
| `docs/methodology.md` | Environment setup, model architecture, evaluation plan |
| `docs/data.md` | Variables, sources (EODHD, Alpha Vantage, SEC EDGAR, HuggingFace) |
| `docs/literature.md` | 24 annotated references organized by research point with inline citations |
| `docs/todo.md` | Current pending items (literature gap, data pipeline, sentiment) |

## Conventions

- No code has been written yet. Do not look for entrypoints, tests, or config files that do not exist.
- All decisions are still open (model architecture, data sources, exact training framework). Check `docs/todo.md` for current state.
- When adding code, start with `pyproject.toml`, a dependency manifest, and a linter config before writing implementation.
- The thesis will be written in LaTeX — likely co-located or in a sibling directory later.

## Git

- No remote configured. Single local branch (`main`).
- Commit history is all `docs: ...` prefixed.
