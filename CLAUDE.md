# Project Rules

## add-tests

> Apply this rule when you judge it to be relevant.

Add new test cases for new code IF there is already a test suite for that
language

## build-all

> **Always follow this rule.**

After changing code in chrome-extension, run:
```bash
python chrome-extension/build_extension.py
```

After changing code in android, do a release build in the normal way.

Afer changing code affecing both clients, run:
```bash
scripts/build_all.sh
```

## read-architecture-docs

> Apply this rule when you judge it to be relevant.

Read the architecture documentation in the docs/ directory

- ARCHITECTURE.md

## run-tests-first

> Apply this rule when you judge it to be relevant.

Before embarking on a non-trivial code change that may require running tests per
other rules, do a test run to establish a baseline. Maybe the tests were already
failing before you even start making code changes.

## run-tests

> Apply this rule when you judge it to be relevant.

After non-trivial python code changes, run tests to ensure functionality. Get
the tests to pass before calling a task complete.
