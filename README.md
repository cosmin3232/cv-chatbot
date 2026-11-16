# CV Chatbot

A chatbot project with a Next.js frontend and a separate backend directory.

## Structure

- `frontend/`: Next.js, TypeScript, Tailwind CSS, shadcn/ui, and Prompt Kit.
- `backend/`: FastAPI API, local Ollama or Runpod inference, PDF/Word knowledge import, and SQLite archive.
- `deploy/runpod/`: Ollama Serverless worker image and deployment instructions.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend calls the backend at `http://localhost:8000` by default. Set up Ollama and import/review your documents following [backend/README.md](backend/README.md), then start the backend before chatting. The displayed session resets on refresh; accepted messages remain in the backend's private SQLite archive.

For GPU inference that scales down between requests, follow [Runpod Serverless setup](deploy/runpod/README.md). FastAPI and SQLite stay on a persistent host; only model inference runs on Runpod.

## Production build

```bash
cd frontend
npm run build
npm start
```

See [frontend/README.md](frontend/README.md) for component details.
