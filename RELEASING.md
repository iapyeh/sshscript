# Release workflow

Python 3.11 or newer is required. The development checkout is a flat source tree; its pyproject.toml is a release template, not an editable-install configuration. Do not run pip install . in the development checkout.

Install development tools with `python -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine`. Run `python tools/run_checks.py` from working_branch. Run `python tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE` to build a clean allowlisted source distribution, build its wheel, verify the exact public test/instruction list in the sdist, rerun the credential-free gates from that extracted sdist, check metadata and test the installed wheel. The output directory must not exist. Local preparation includes current files, including uncommitted changes; only committed inputs are available in CI.

Review and commit the intended development changes before merging working_branch into src/main. Follow the project version policy: increment src/_version.py once after a successful integration, commit it, and synchronize that version back to working_branch. Version imports must refer to _version.py; build and upload tools never edit versions.

From git/, run `sh update_from_src.sh` to synchronize the integrated src tree. The explicit allowlist preserves unrelated files; review deletions separately when retiring modules. Review the diff, including newly created files. Run `python tools/run_checks.py` and `python tools/check_release.py --output /tmp/sshscript-release-UNIQUE` in git/. Commit reviewed release files, then verify a clean checkout of that commit before tagging or uploading. CI uses the same checks in both layouts on Linux/macOS and Python 3.11–3.14.

The default `python -m build` operation builds an sdist and then a wheel from that sdist. Successful verification writes verified.json containing artifact SHA-256 hashes. Keep this file with the two distribution files. CI artifacts are for inspection; select one verified candidate for release.

Production publication uses `.github/workflows/release.yml`. Configure the PyPI
Trusted Publisher for owner `iapyeh`, repository `sshscript`, workflow
`release.yml`, and GitHub environment `pypi`. Require approval on that
environment. Pushing an annotated tag that exactly matches
`v<package-version>` rebuilds, tests, hashes, and attests the distributions.
The workflow then creates a draft GitHub Release, publishes to PyPI with a
short-lived OIDC credential, and makes the GitHub Release public only after
PyPI accepts the verified artifacts. The hash manifest is retained with the
release assets; build, OpenSSH integration, OIDC publishing, and public-release
jobs remain separate.

Manual upload remains an emergency-only operation:
`python tools/publish_release.py --artifacts /tmp/sshscript-release-UNIQUE
--repository pypi`. Supply credentials through an external secret manager;
never put credentials in source files. Upload verifies the recorded hashes and
never rebuilds or changes the version. Branch push, tag creation, GitHub Release
publication, and PyPI publication are distinct auditable operations.


## Reproducible validation evidence

SSHScript aims to let engineers and AI reliably execute, understand, and take
over automation. A release therefore retains the public regressions and their
instructions so another user can reproduce the validation of its execution
contracts. Passing development tests alone is not release evidence.

`tools/prepare_release.py` owns the explicit public test allowlist. The root
`prepare_release.py` is a compatibility entry point to that same implementation.
When adding a public regression or supporting fixture/instruction, review it for
private credentials and host information, then update the allowlist,
`MANIFEST.in`, and `.gitignore` together. Every `unittest/test_*.py` discovered
locally must be allowlisted; an unapproved new regression fails preparation
rather than being silently omitted. Private legacy scripts remain excluded.

`tools/run_checks.py` validates that list in both source layouts.
`tools/check_release.py` checks the built sdist's exact public test list and
contents against staging, then runs the normal and optimized suites, dollar
syntax tests, and assert scan from the extracted sdist before retaining verified
artifacts. Build failures, missing/changed tests, or test failures abort the
verification. To reproduce the public gates from a downloaded sdist, extract it,
install the documented test dependencies, and run `python tools/run_checks.py`
from its root.

These credential-free gates can skip real OpenSSH tests. Such skips are not
proof of native SSH/PAM/su/sudo compatibility; the separate OpenSSH jobs and
native-system validation matrix still apply.
