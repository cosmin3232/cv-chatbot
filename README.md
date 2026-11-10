# CV Chatbot

A chatbot project with a Next.js frontend and a separate backend directory.

## Structure

- `frontend/`: Next.js, TypeScript, Tailwind CSS, shadcn/ui, and Prompt Kit.
- `backend/`: FastAPI chat API, local Ollama integration, and PDF/Word knowledge import.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The frontend calls the backend at `http://localhost:8000` by default. Set up Ollama and import/review your documents following [backend/README.md](backend/README.md), then start the backend before chatting. Conversations are stored in browser memory and reset on refresh.

## Production build

```bash
cd frontend
npm run build
npm start
```

See [frontend/README.md](frontend/README.md) for component details.
