# Contributing

DriftGuard welcomes focused changes that improve deterministic AI/agent regression admission, measurement validity, provenance, or behavioral-drift governance.

Before adding a new abstraction, show the concrete failure mode it closes.

A good change usually includes:

- a minimal reproducible failure or hostile test;
- the narrowest implementation that closes it;
- explicit behavior for missing/ambiguous evidence;
- a claim ceiling stating what the change still does not prove;
- tests on both ordinary and adversarial paths.

Please avoid turning DriftGuard into an LLM provider SDK or a full eval runner. Its product boundary is deliberately downstream of evaluation.

Run:

```bash
python -m pip install -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
git diff --check
```

For security-sensitive findings, follow [SECURITY.md](SECURITY.md) instead of filing a public issue.
