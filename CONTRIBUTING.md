# Development and releases

Use this repository as the source of truth. Keep the checkout at a stable path;
the installed local plugin can refer to it. Save application documents before updating.

```powershell
git status --short --branch
git fetch --prune origin
git switch main
git pull --ff-only
git switch -c feature/short-description
# Make changes and run the checks documented in README.md.
git diff --check
git diff
git add <explicit-files>
git diff --cached
git commit -m "Describe the change"
git push -u origin feature/short-description
```

Open a pull request into main. Use fix/ for bug fixes and docs/ for documentation.
Never force-push main. Fast-forward-only pulls stop safely when histories diverge.
Review staged files before every commit; keep local config, secrets, generated media,
voice samples, model weights, runtime state and installed applications outside Git.
Start with the provided configuration examples, then follow README.md to build/install.
Generated plugin directories are rebuilt from source except where README.md says otherwise.

Before a release, run the documented tests and packaging checks, update the plugin
version and CHANGELOG.md, then create an annotated vX.Y.Z tag. Publish source and
verified release packages through GitHub Releases. Do not upload software/model installers.
Keep upstream copyright notices and THIRD_PARTY_NOTICES.md when changing dependencies.

MIT covers the repository's own code. Third-party software, models, trademarks and
user-provided media retain their respective terms. An MIT code license does not grant
rights to redistribute private reference voices or commercial application assets.
