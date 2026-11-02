# Shared file link inventory

- UI: `src/productivity.jsx` `pathValid` and `SharedLinks` used by `src/App.jsx` in project and task editor.
- Native bridge: `native_app.py` `valid_share_path`, `validate_links`, `Bridge.openSharedFile`, `JS_BRIDGE`.
- Web-only preview stub: `src/App.jsx` `mockBridge.openSharedFile`.
- `fileLinks` is only metadata in project/task state; shared binary is not an attachment or LAN API request. Windows SMB provides actual file authorization.
- Existing Explorer action selects a shared path. A new explicit download copies file bytes to the local client's Downloads folder and never launches the file.
