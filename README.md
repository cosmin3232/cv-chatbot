# CV Chatbot

A chatbot project with a Next.js frontend and a separate backend directory.

## Structure

- `frontend/`: Next.js, TypeScript, Tailwind CSS, shadcn/ui, and Prompt Kit.
- `backend/`: Placeholder for the backend implementation.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The chat currently uses demo replies; an AI backend is not connected yet. Messages are stored in memory and reset on refresh.

## Production build

```bash
cd frontend
npm run build
npm start
```

See [frontend/README.md](frontend/README.md) for component details.
