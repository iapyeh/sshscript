## Summary

<!-- What changes, and what user or maintainer problem does it solve? -->

## Behavior and compatibility

<!-- Describe public API, dollar syntax, CLI, exception, security, or migration impact. -->

## Validation

<!-- List exact commands and results. At minimum, run the credential-free gate. -->

- [ ] `python3 tools/run_checks.py`
- [ ] `python3 tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE`
- [ ] A regression test covers the change, or the reason it cannot is explained.
- [ ] Relevant behavior was checked with and without `python -O`.

## Documentation and release notes

- [ ] README or v3 documentation is updated for user-visible behavior.
- [ ] `CHANGELOG.md` is updated, or this change has no user-visible effect.
- [ ] Module API and dollar-syntax descriptions remain aligned.

## Security and hygiene

- [ ] No credential, private key, token, internal hostname, private path, or production output is included.
- [ ] Host-key, command-injection, privilege, timeout, logging, and cleanup effects were considered.
- [ ] New dependencies or permissions are justified in the summary.

## Related issue

<!-- Use "Closes #123" when appropriate. -->
