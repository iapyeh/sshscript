# Support policy

SSHScript is community-maintained. Support, triage, and fixes are provided on a
best-effort basis with no service-level agreement or guaranteed response time.

## Supported scope

| Component | Support level |
| --- | --- |
| Latest SSHScript 3.1.x | Bug and security fixes |
| Earlier SSHScript releases | Unsupported; reproduce on the latest 3.1.x first |
| Python 3.11–3.14 | Continuously tested in public CI |
| Current Linux and macOS | Continuously tested for the credential-free suite |
| OpenSSH on Ubuntu | Tested with disposable real-SSH integration |
| Other SSH server implementations | Best effort |
| Paramiko `>=2.11,<5` | Accepted dependency range; not every combination is continuously tested |
| Windows and other operating systems | Not currently tested or supported |

The package metadata requires Python 3.11 or newer. A newer interpreter not yet
listed in the CI matrix is installable under that constraint but is not treated
as verified until it has been added to the matrix.

## Where to ask

Use the following channels:

- [SSHScript v3 documentation](https://iapyeh.github.io/sshscript/v3a/) for
  installation, concepts, tutorials, and known workflows;
- [GitHub Discussions](https://github.com/iapyeh/sshscript/discussions) for
  usage questions and design discussions;
- [GitHub Issues](https://github.com/iapyeh/sshscript/issues) for reproducible
  defects and feature requests;
- [private vulnerability reporting](https://github.com/iapyeh/sshscript/security/advisories/new)
  for security issues.

Do not use a public issue for a suspected vulnerability. Follow
[SECURITY.md](SECURITY.md) instead.

## Before opening a defect

Confirm the problem on the latest 3.1.x release and collect version information:

```sh
sshscript --version
python3 -c "import platform, paramiko; print(platform.platform()); print(paramiko.__version__)"
```

Reduce the behavior to a credential-free local reproducer or a disposable SSH
host whenever possible. A useful defect report includes:

- SSHScript, Python, and Paramiko versions;
- operating system and SSH server implementation/version;
- whether the command is local, direct SSH, nested SSH, PTY, `sudo`/`su`, or
  file transfer;
- a minimal executable example and exact reproduction steps;
- expected behavior, actual behavior, exit status, and a redacted traceback;
- whether the issue reproduces with the module API, dollar syntax, or both.

Do not post passwords, private keys, tokens, internal hostnames, complete
private paths, inventories, or captured production output. Replace them with
synthetic values and check every attachment before upload.

## Maintenance boundaries

The project can address reproducible SSHScript behavior and improve documented
integration points. The following remain the deployer's responsibility:

- site-specific architecture and production rollout design;
- SSH server hardening, host-key enrollment, account authorization, and
  firewall policy;
- distribution-specific PAM, `sudoers`, shell startup, and privilege policy;
- availability and behavior of remote commands and third-party services;
- secret storage, credential rotation, audit retention, and incident response.

Concise reproductions, documentation corrections, and patches are welcome even
when an environment is outside the support matrix. Acceptance still depends on
maintainability, security, test coverage, and compatibility with supported
systems.

## Production use

Production/Stable describes the release maturity and public release gates; it
is not a warranty for every host policy or automation task. Pin dependencies,
review the automation, test against disposable representatives of the target
systems, define timeouts and rollback behavior, and monitor exit status before
rolling out privileged or destructive changes.
