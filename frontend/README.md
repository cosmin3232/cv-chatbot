This is a [Next.js](https://nextjs.org) chat frontend using [shadcn/ui](https://ui.shadcn.com/) and [Prompt Kit](https://www.prompt-kit.com/docs/introduction).

## Chat UI

The home page renders `src/components/chat.tsx`. It supports starter prompts, multiline input, sending messages, automatic scrolling, and clearing the conversation with **New chat**. Messages are held in memory and reset on refresh. Replies are explicitly labeled demo responses; no AI service is connected and no messages are sent to a server.

To connect the backend, replace the demo reply in `sendMessage` with your API request and append the returned assistant message.

shadcn/ui is configured in `components.json` with Radix components and Tailwind v4. Prompt Kit component source lives in `src/components/ui/` alongside its shadcn dependencies. To add more components, run these commands from `frontend`:

```bash
npx shadcn@latest add dialog
npx shadcn@latest add "https://prompt-kit.com/c/loader.json"
```

## Getting Started

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
