# Releasing

## Version and checks

1. Update `VERSION`, the Claude adapter manifest, and `CHANGELOG.md` together.
   Use a prerelease such as `0.1.0-beta.1` until the compatibility record is
   sufficient for a stable release.
2. Run the checks in [CONTRIBUTING.md](../CONTRIBUTING.md).
3. Run the Linux and macOS GitHub Actions jobs. Record actual results in
   [validation.md](../validation.md); do not turn planned checks into claims.
4. Try both installation methods from a fresh checkout. Check that a second
   load does not duplicate indicators, switching to `none` removes only the
   preset, and uninstall preserves existing tmux settings.
5. Confirm the real-agent smoke test: run a task, switch to another session,
   wait for its bell, and visit the notified window to acknowledge it.
   Check cancellation separately. The static demo and event tests do not
   substitute for this check on a newly supported agent version.
6. Review the committed files for temporary files, private configuration,
   credentials, and unrelated changes.

## Package and publish

The release workflow builds an archive from the tagged commit and includes
its SHA-256 checksum. It does not install or invoke an agent.

```sh
git tag -a "v$(cat VERSION)" -m "Release $(cat VERSION)"
git push -u origin main
git push origin "v$(cat VERSION)"
```

If the release tag is already present in your checkout, skip the `git tag`
command. The prepared first-beta checkout already includes its local tag.

The tag starts CI. Once CI succeeds, the Release workflow prepares a **draft**
GitHub release. For a tag containing `-`, the release is marked as a prerelease.
Review its notes and artifacts before publishing the draft. Enable GitHub
Actions in the repository before pushing the release tag.

For a local archive of a committed version:

```sh
python3 tools/package_release.py
```

Artifacts appear in `dist/`, which is excluded from Git. For this first beta,
the public repository is `https://github.com/benremer/tmux-agent-status`.
Create that repository empty before the first push.

## Beta support policy

The core targets tmux 3.4 and newer. A beta can be shared while macOS and
additional agent-version checks remain pending, provided those limits are
prominent in the compatibility table. Do not describe an untested platform
as verified. Breaking beta changes need release notes and migration steps.
