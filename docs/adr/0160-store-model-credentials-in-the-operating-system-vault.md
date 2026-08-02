Status: accepted

# Store Model Credentials in the Operating System Vault

The Native Desktop Application will persist each Researcher Model Credential through a Secret Store abstraction backed by the operating system credential vault.
Project files, databases, configuration snapshots, logs, exports, and API read responses will never contain the plaintext credential; environment variables remain compatible runtime inputs but are not a persistence target for credentials saved through the workspace.
A stored credential takes precedence for workspace-launched work, and the supported environment variable is consulted only when no stored credential exists.

## Consequences

- macOS Keychain, Windows Credential Manager, and Linux Secret Service require platform adapters behind the same Secret Store contract.
- An unavailable credential vault is an explicit configuration error rather than a reason to fall back to plaintext storage.
- The application can report, replace, test, and delete a credential without reading its plaintext value back to the GUI.
- Deleting a stored credential reveals the environment fallback when one is present, and the API reports the effective source without exposing the secret.
