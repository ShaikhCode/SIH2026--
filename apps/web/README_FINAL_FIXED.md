# BhashaSaathi Web — FinalV20.1 publish fix

This web folder includes the publish white-screen safeguards.

## Important behavior
- Publish requires only source + teacher-approved target translations.
- Audio and practice never block publish.
- Publish receives a small acknowledgement and immediately updates the UI locally.
- Authoritative lesson/version refresh runs in the background and cannot blank the already-published view.
- Background preparation polling refreshes the full lesson pack only when a job reaches READY/FAILED, not every running heartbeat.
- AppErrorBoundary catches render-time React failures instead of showing a blank screen.

## Run
```powershell
cd apps\web
npm install
npm run build
npm run dev
```
API must be the matching FinalV20.1 backend.
