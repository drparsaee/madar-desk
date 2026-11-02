# Shared UNC path and download design

- Accept existing UNC file paths with spaces in share names. UI rejects non-strings, oversized paths, non-UNC, device paths, invalid Windows filename characters and dot/dot-dot components, consistent with `native_app.valid_share_path`.
- Keep `openSharedFile` for File Explorer and add `downloadSharedFile(path)` for save-to-Downloads. UI offers both actions; HTML preview remains unsupported.
- Download occurs on the client via Windows-authenticated SMB, destination inside that user's Downloads folder. Create destination exclusively; append numeric suffix on collision; clean failed partial copy; do not run file or overwrite an existing copy.
- Treat inaccessible SMB files and directories as native operation errors for visible UI feedback. No server writes and no application state mutations.
