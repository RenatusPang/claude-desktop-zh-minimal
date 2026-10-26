# Security policy

- Do not share `%APPDATA%\\Claude`, `%APPDATA%\\Claude-3p`, `.env` files,
  API keys, authentication tokens, browser cookies, or application bundles.
- Only the known Windows Claude MSIX build `3.1623.0.0` is enabled. Other versions
  intentionally fail closed. A new build requires a separate audit and test.
- This tool does not patch `Claude.exe` or `app.asar`, access the network,
  change CC Switch / gateway endpoints, or run background tasks.
- Local user config files are read only to edit their `locale` property. They are
  never logged or uploaded; other fields must remain intact.
- Rollback restores the original verified JS bytes from the private backup. If files
  changed externally or Claude was updated, rollback halts rather than overwriting.
- The installed app is a Microsoft Store/MSIX package. Modifying app resource files
  may conflict with package integrity or automatic updates; use at your own risk.
- Do not run unknown PowerShell scripts or use forced ACL/ownership changes to bypass
  WindowsApps protections.
- Report security concerns privately to the repository maintainer rather than posting
  secrets in a public issue.
