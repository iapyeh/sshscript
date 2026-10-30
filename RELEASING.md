# Release workflow

Python 3.11 or newer is required. The development checkout is a flat source tree; its pyproject.toml is a release template, not an editable-install configuration. Do not run pip install . in the development checkout.

Install development tools with `python -m pip install 'paramiko>=2.11,<5' 'packaging>=21' build twine`. Run `python tools/run_checks.py` from working_branch. Run `python tools/check_release.py --output /tmp/sshscript-candidate-UNIQUE` to build a clean allowlisted source distribution, build its wheel, verify the exact public test/instruction list in the sdist, rerun the credential-free gates from that extracted sdist, check metadata and test the installed wheel. The output directory must not exist. Local preparation includes current files, including uncommitted changes; only committed inputs are available in CI.

Review and commit the intended development changes before any explicitly authorized merge into src/main. Follow [VERSIONING.md](VERSIONING.md): edit only working_branch/_version.py on the working_branch branch. Never edit src/main directly. Development builds use distinct .devN versions. During active development, minor releases may include incompatible changes; explicitly select the release version with the maintainer and briefly document major differences. Promotion to a stable version is a separately authorized action after release validation, not an automatic patch bump on merge. Version imports must refer to _version.py; build and upload tools never edit versions.

From git/, run `sh update_from_src.sh` to synchronize the integrated src tree. The explicit allowlist preserves unrelated files; review deletions separately when retiring modules. Review the diff, including newly created files. Run `python tools/run_checks.py` and `python tools/check_release.py --output /tmp/sshscript-release-UNIQUE` in git/. Commit reviewed release files, then verify a clean checkout of that commit before tagging or uploading. CI uses the same checks in both layouts on Linux/macOS and Python 3.11–3.14.

The default `python -m build` operation builds an sdist and then a wheel from that sdist. Successful verification writes verified.json containing artifact SHA-256 hashes. Keep this file with the two distribution files. CI artifacts are for inspection; select one verified candidate for release.

Production publication uses `.github/workflows/release.yml`. Both this workflow
and the manual PyPI uploader reject prerelease and local versions; development
artifacts may be verified locally or explicitly uploaded to TestPyPI.
`4.0.0.dev0` does not authorize a 4.0 release.

Configure the PyPI
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


## Documentation-only updates without an AI session

Use `docs-prepare` and `docs-finish` to publish selected public Markdown documents
from `working_branch` to GitHub's `release` branch. This workflow creates a local
source commit, pushes a separate documentation PR, waits for existing required CI,
and squash-merges that pinned PR. It does not change the version, create a tag,
publish to PyPI, or run the version-release workflow. The current GitHub workflow
still runs full CI for every PR; this command does not skip or bypass those checks.
The wait runs locally and consumes no AI tokens.

Requirements are POSIX, Python 3.11+, Git, authenticated `gh`, and permission to
merge PRs. Run from `working_branch/`, using a new state file for each update:

```sh
export SSHSCRIPT_DOCS_STATE="$HOME/.local/state/sshscript/docs-exitcode.json"
python3 -B tools/release_manager.py docs-prepare \
  --source . --checkout ../git \
  --message "Clarify SSHScript exitcode naming in agent skill" \
  --files skills/sshscript/SKILL.md
```

Review the entire printed diff. The plan selects complete files, including any
prior edits in those files. Only explicitly selected `.md` paths listed in
`tools/prepare_release.py`'s `ROOT_FILES` are supported; it rejects code,
unlisted/private documents, symlinks, executable documents and deletions. Existing
source staging must be reviewed and cleared before planning. Unselected working
changes and private untracked files are preserved. If an upstream document has
changed since the committed source copy, reconcile it before making a new plan.

After reviewing, authorize the local commit, push, CI wait and PR merge:

```sh
python3 -B tools/release_manager.py docs-finish --push
```

If the network fails, the wait times out, or the process is interrupted, run that
same command again with the same state file. Content hashes and source HEAD checks
stop publication if the selected files or source history changed after planning.
The candidate commit is based on the saved remote `release` snapshot, so unrelated
source commits and publication checkout changes are not pushed. Required checks
must succeed; failures stop the command for review. Use `--timeout` before the
subcommand to bound the wait, for example `--timeout 3600 docs-finish --push`.
Documentation state is separate from version-release state; the commands reject
using one workflow's saved state with the other workflow.

This route leaves `src/main` and the publication checkout's worktree/index/HEAD
unchanged. The selected documents are committed locally on `working_branch`;
later integration into `src/main` remains a separate explicitly authorized step.
It updates GitHub repository documents only: it does not synchronize gh-pages,
rebuild the website's skill ZIP, or refresh installed skill copies. Those outputs
need their normal separate synchronization/publication workflow when requested.

## Maintainer CLI: push through PyPI without an AI session

`tools/release_manager.py` runs the publication stages locally and saves progress
between commands. Waiting consumes no AI tokens; GitHub's CI still takes its
usual time. It requires POSIX, Python 3.11+, Git, `gh`, authenticated GitHub
access (`gh auth status`), and permission to merge the release PR and approve
the protected `pypi` environment. Installed-wheel verification also needs network
access and Python's `venv`/pip support. PyPI uses the existing Trusted Publisher;
the tool needs no PyPI password or token.

First review, validate, commit and explicitly merge the selected version into
`src/main` using the normal development process. This tool never selects or
changes a version or merges into main. The committed main snapshot must contain
the matching changelog entry and release preparation rules. The following uses
**7.0.1 only as an example**, not as a version decision.

Run from `working_branch/`. Give each release its own state file outside Git:

```sh
export SSHSCRIPT_RELEASE_STATE="$HOME/.local/state/sshscript/7.0.1.json"
python3 tools/release_manager.py prepare --version 7.0.1 --source ../src --checkout ../git
git -C ../git diff --stat
git -C ../git diff
git -C ../git ls-files --others --exclude-standard
```

`prepare` reads committed main, freezes its SHA and content hashes, and copies
only the public allowlist into the `release` checkout. It can fetch and integrate
the previous remote release into that publication checkout. It preserves unrelated
untracked files and stops on tracked changes, untracked destination collisions,
or unpublished local content. Review newly added files as well as the diff.
If public inputs were intentionally retired, review the listed paths and repeat
`prepare` with `--remove-retired`. It never writes to `src/main`.

After reviewing the prepared files, run all remaining stages:

```sh
python3 tools/release_manager.py finish --publish --approve-pypi
```

This commits the reviewed publication files, pushes a candidate branch, creates
a PR targeting `release`, waits for required CI, squash-merges the pinned PR,
pushes an annotated version tag, waits for the release workflow, checks the draft
artifacts and approves `pypi`. It then verifies the public GitHub/PyPI file hashes
and tests the installed PyPI wheel in a temporary virtual environment.
`--approve-pypi` explicitly authorizes automated environment approval after those
checks. Without it, `finish --publish` stops with exit code **3** when approval
is needed, preserving progress.

For separate stages, use these commands in order:

| Command after `python3 tools/release_manager.py` | Action |
| --- | --- |
| `submit` | Commit the prepared files, push the candidate, create/reuse its PR. |
| `wait-ci` | Wait for that PR's checks and complete CI workflow to succeed. |
| `merge-tag` | Merge the pinned PR and push its annotated version tag. |
| `wait-release` | Wait for release CI; exit 3 when protected approval is needed. |
| `approve-pypi --yes` | Verify draft hashes/build gates and approve `pypi`. |
| `wait-release` | Wait for upload and public GitHub Release completion. |
| `verify --install-check` | Compare GitHub/PyPI hashes and test a fresh installation. |
| `status` | Inspect saved identities and current GitHub status at any time. |

The publication commit sent to GitHub contains the reviewed tree on the frozen
remote release base; unrelated local commit history is not pushed. Normal branch
protection remains in effect. The tool never force-pushes, replaces tags, bypasses
protection or automatically retries failed CI.

### Stop, resume, and recover

Keep the same state file and rerun the interrupted stage, or `finish --publish`
with the desired approval option. Successful merge/tag steps are reused. Ctrl-C
returns 130; failures/timeouts return 1. State writes are atomic, access is
restricted to the current user, and a lock prevents two commands using the same
state concurrently. State contains paths, SHAs and publication metadata, not
credentials. Do not run separate release sessions against the same checkout at
the same time or delete the state while publication is in progress.

Global options precede the command. The default polling interval is 60 seconds
and waiting continues until completion or interruption. For a bounded wait:

```sh
python3 tools/release_manager.py --interval 30 --timeout 3600 wait-ci
```

On a failure, inspect the reported PR/run URL or
`gh run view RUN_ID --repo iapyeh/sshscript --log-failed`. For a confirmed transient
failure, use `gh run rerun RUN_ID --repo iapyeh/sshscript --failed`, then repeat the
wait command. A source fix requires the normal working_branch commit and
explicit main merge, followed by a new state/candidate from a clean publication
checkout. The tool refuses to silently change the frozen candidate. Preserve
the failed session for inspection; never reset main to restart publication.

If the PR was already merged manually or its state file is unavailable, recover
into a **new** state file (replace `PR_NUMBER` with the actual merged PR):

```sh
python3 tools/release_manager.py --state "$HOME/.local/state/sshscript/recovered.json" recover --version 7.0.1 --pr PR_NUMBER --checkout ../git
```

Then use that same `--state` path with `status` and `finish --publish` (optionally
`--approve-pypi`). Recovery validates the merged tree/version and reuses an
existing annotated tag only when it points to that exact merge. It never starts
a replacement release for an already published version.

Website documentation remains a separate reviewed `gh-pages` publication. Push
its intended commit normally and use `gh run watch RUN_ID --repo iapyeh/sshscript`
to wait locally for its deployment without an AI session.

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

*Last modified: 2026-10-29 16:26:49*
