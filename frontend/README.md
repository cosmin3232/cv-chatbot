This is a [Next.js](https://nextjs.org) chat frontend using [shadcn/ui](https://ui.shadcn.com/) and [Prompt Kit](https://www.prompt-kit.com/docs/introduction).

## Chat UI

The home page renders `src/components/chat.tsx`. It includes a responsive conversation sidebar, conversation search, recruiter-focused starter prompts, multiline input, Markdown replies, copy-message actions, and automatic scrolling. Use **New conversation** to start another chat, select a sidebar entry to resume a conversation (including its draft), or use the header trash button to remove the current conversation from this browser session. On mobile, the header menu opens the conversation sidebar.

The browser view and drafts are held in memory and reset on refresh. Each chat page mount and **New conversation** click generates a fresh UUID v4 in the browser. Messages within one conversation share that UUID; switching sidebar entries keeps the original UUID. The backend archives accepted user messages, replies, and failed generation attempts in SQLite for the owner. The sidebar is not a public view of that database, and its remove button does not delete archived records. The chat footer discloses private owner storage. Set up the model and documents using [backend/README.md](../backend/README.md).

The UI calls `agentService.sendPrompt({ conversationId, messageId, prompt, history }, { signal })` from `src/services/agent-service.ts`. It sends a JSON POST to `/api/chat` on the backend and validates the `{ content: string }` response. History contains previous messages, excluding the new prompt, and is bounded to the server's limits. `messageId` is the user message's UUID, allowing exact retries to avoid duplicate archive entries. Pending requests disable sending in their own conversation; removing a conversation cancels its browser request. Failed requests restore the draft and display an error so it can be sent again. Sending the restored draft from the UI creates a new message attempt, while API clients can reuse an existing failed message ID for an idempotent retry.

`NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`. Copy `.env.example` to `.env.local` to override it. This URL is public and must be reachable from the visitor's browser; do not put secrets in it. Restart Next.js after changes and rebuild for production. The HTTP helper in `src/services/http-client.ts` forwards cancellation and throws `HttpError` for unsuccessful responses. Requests time out after 130 seconds.

shadcn/ui is configured in `components.json` with Radix components and Tailwind v4. Prompt Kit component source lives in `src/components/ui/` alongside its shadcn dependencies. To add more components, run these commands from `frontend`:

```bash
npx shadcn@latest add dialog
npx shadcn@latest add "https://prompt-kit.com/c/loader.json"
```

## Job-fit analysis

Open `/job-match`, or use **Analyze a job description** in the chat sidebar. Paste a description or upload PDF/DOCX, review the extracted preview, and select **Analyze fit**. Results show requirement-level statuses, job excerpts, CV evidence, explanations, and follow-up questions. Input edits clear the old report. Cancel abandons the browser request; analysis may take several minutes on a local CPU.

The feature uses `src/services/job-match-service.ts`, validates report data at runtime, and calls `POST /api/job-description/extract` and `POST /api/job-match` on the configured backend. Analysis requests time out after 250 seconds; if the server deadline is increased above 240 seconds, adjust the frontend service timeout as well. The upload limit is 5 MB, the PDF page limit is 10, and reviewed text is limited to 8,000 characters and 12 distinct requirements. Successful uploads (original file and extracted text) are saved privately in SQLite for the site owner, as stated beside the upload control. They do not become candidate knowledge. There are no public archive retrieval routes or recruiter history screens. Later preview edits and reports are not archived.

Run all frontend service tests with `node --test tests/services.test.mjs tests/job-match-service.test.mjs`.
Session UUID tests can also be included with `node --test tests/services.test.mjs tests/job-match-service.test.mjs tests/chat-session.test.mjs`.

## Getting Started

Run the service tests with `node --test tests/services.test.mjs` from `frontend` using Node with built-in TypeScript support. Tests cover request payloads, response validation, bounded history, cancellation, HTTP errors, and network failures.

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the chat by modifying `src/components/chat.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
