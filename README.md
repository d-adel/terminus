# Terminus

An open qualification system for simulation software. A scheme states what software must achieve and on which cases. Terminus runs the cases, measures the results, and decides whether the software conforms, recording every step as signed, content-addressed evidence that anyone can recheck. Python 3.12, MIT licence.

## Model

| Object | What it is |
| --- | --- |
| Measurand | a defined quantity with a unit, for example a relative error against a reference |
| Case | one problem to realize: inputs, purpose (`verification` or `validation`), observables |
| Scheme | requirements: a measurand, a predicate with a limit, the cases, and a decision rule |
| Artifact, Adapter | the software at an exact commit, and the code that realizes cases with it |
| Realization, Observations | how faithfully a case was realized (`exact`, `approximate`, `unsupported`), and what was observed |
| Measurement result | a value with an uncertainty, produced by a named procedure from observations |
| Claim, Determination | a scheme requirement applied to an artifact, and the evaluated status: `SUPPORTED`, `FAILED`, `NOT_ESTABLISHED` or `OUT_OF_SCOPE` |

- **Decision rule:** a guard band. A measurement conforms only when value + uncertainty is within the limit, and fails only when value − uncertainty is outside it. Anything between is not established.
- **Composite claims:** `all_of` combines requirements.
- **Objects** are canonical JSON (RFC 8785), addressed by SHA-256. Each one is signed by its publisher as an in-toto statement. The object model is LinkML: `src/terminus/model/model.yaml`.
- **Measurement procedures** come from a pack, a git repository of cases, measurands, schemes and Python procedures. Their source is stored with the evidence and run in an isolated interpreter.

## Commands

| Command | Does |
| --- | --- |
| `terminus keygen` | create a publisher signing key |
| `terminus publish FILE` | sign and store a measurand, case or scheme |
| `terminus run` | run a scheme's cases for an artifact through a lab, then measure and evaluate |
| `terminus ingest`, `measure`, `evaluate` | the same stages, one at a time |
| `terminus show`, `diff` | read a determination, and compare two |
| `terminus export ROOT DIR` | write a determination's complete evidence closure, with W3C PROV |
| `terminus recheck DIR` | verify an export: digests, signatures, closure, the re-evaluated determination and, with `--trust`, the re-run measurements |

Global options: `--store`, `--keys`, `--publisher`.

## Install and test

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Design basis

`sources/` records the standards and practice Terminus follows, and what was read of each:
- conformity assessment (ISO/IEC 17000, 17025; ILAC-G8 decision rules)
- model credibility (ASME V&V 40, NASA-STD-7009, Oberkampf and Trucano)
- argument structure (GSN)
- evidence (in-toto, SLSA, W3C PROV)
- measurement vocabulary (VIM, GUM)
