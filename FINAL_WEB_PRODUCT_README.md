# BhashaSaathi Final Web Product

This build focuses on the real web workflow and fixes account-role selection, language selection, creator/student routing, classroom creation UX, and authenticated product flows.

## Important
Keep these local folders/files from your existing machine:
- apps/api/.venv
- apps/api/models
- apps/api/.env

Replace the application code with this build.

## Account model
Registration now lets a new user choose:
- Creator / Educator
- Student / Learner

The API registration endpoint now honors the selected account_role. A creator can also open My Learning and join classrooms; classroom creation remains creator-only and practice submission remains student-account-only.

## Run
Backend terminal:
```powershell
cd D:\git\BhashaSaathi_Local_NoDocker\apps\api
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend terminal:
```powershell
cd D:\git\BhashaSaathi_Local_NoDocker\apps\web
npm install
npm run dev
```

Open http://localhost:5173
