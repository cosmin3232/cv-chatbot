"use client";

import { useState } from "react";
import { ArrowUp, Code2, Lightbulb, Plus, Sparkles, SquarePen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatContainerContent, ChatContainerRoot } from "@/components/ui/chat-container";
import { Message, MessageContent } from "@/components/ui/message";
import { PromptInput, PromptInputAction, PromptInputActions, PromptInputTextarea } from "@/components/ui/prompt-input";
import { PromptSuggestion } from "@/components/ui/prompt-suggestion";
import { ScrollButton } from "@/components/ui/scroll-button";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };

const suggestions = [
  { icon: Lightbulb, title: "Explore an idea", prompt: "Help me brainstorm ideas for a personal project." },
  { icon: SquarePen, title: "Find the right words", prompt: "Help me turn a rough idea into a clear first draft." },
  { icon: Code2, title: "Build something", prompt: "Help me break a coding project into manageable steps." },
];

export function Chat() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  function sendMessage() {
    const content = input.trim();
    if (!content) return;
    // Replace this demo reply with a backend request when the API is ready.
    setMessages((previous) => [
      ...previous,
      { id: crypto.randomUUID(), role: "user", content },
      { id: crypto.randomUUID(), role: "assistant", content: "Your message came through. This is a demo response so you can try the chat interface. Connect an AI backend to start getting answers to your questions." },
    ]);
    setInput("");
  }

  function newChat() {
    setMessages([]);
    setInput("");
  }

  return (
    <div className="flex h-dvh min-h-0 flex-col bg-background">
      <header className="flex shrink-0 items-center justify-between border-b px-5 py-4 sm:px-8">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Sparkles className="size-4" aria-hidden="true" /></div>
          <div><p className="text-sm font-semibold tracking-tight">Personal Chat</p><p className="text-xs text-muted-foreground">A little space to think</p></div>
        </div>
        <Button variant="outline" onClick={newChat} className="h-9 gap-2 rounded-full px-4"><Plus aria-hidden="true" /> New chat</Button>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        {messages.length === 0 ? (
          <section className="flex min-h-0 flex-1 overflow-y-auto px-5" aria-labelledby="welcome-title">
            <div className="m-auto w-full max-w-2xl py-10 sm:py-16">
              <span className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-muted-foreground"><span className="size-1.5 rounded-full bg-amber-500" /> Demo workspace</span>
              <h1 id="welcome-title" className="text-4xl font-medium tracking-tight sm:text-5xl">What&apos;s on your mind?</h1>
              <p className="mt-4 max-w-lg text-base leading-7 text-muted-foreground">A question, a fresh idea, or a blank page. Start here and see where the conversation takes you.</p>
              <div className="mt-9 grid gap-3 sm:grid-cols-3">
                {suggestions.map(({ icon: Icon, title, prompt }) => (
                  <PromptSuggestion key={title} onClick={() => setInput(prompt)} className="h-auto flex-col items-start gap-4 rounded-2xl p-4 text-left whitespace-normal">
                    <Icon className="size-5 text-muted-foreground" aria-hidden="true" /><span className="text-sm font-medium">{title}</span>
                  </PromptSuggestion>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <ChatContainerRoot className="relative min-h-0 flex-1" aria-label="Conversation" aria-live="polite">
            <ChatContainerContent className="mx-auto max-w-3xl gap-8 px-5 py-8 sm:px-8">
              {messages.map((message) => (
                <Message key={message.id} className={message.role === "user" ? "justify-end" : "justify-start"}>
                  {message.role === "assistant" && <span className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border"><Sparkles className="size-4" aria-hidden="true" /></span>}
                  <div className="min-w-0 max-w-[85%]">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">{message.role === "user" ? "You" : "Assistant · Demo"}</p>
                    <MessageContent className={message.role === "user" ? "rounded-2xl px-4 py-3 whitespace-pre-wrap [overflow-wrap:anywhere]" : "bg-transparent p-0 leading-7 whitespace-pre-wrap [overflow-wrap:anywhere]"}>{message.content}</MessageContent>
                  </div>
                </Message>
              ))}
            </ChatContainerContent>
            <ScrollButton aria-label="Scroll to latest message" className="absolute bottom-4 left-1/2 -translate-x-1/2" />
          </ChatContainerRoot>
        )}

        <div className="mx-auto w-full max-w-3xl shrink-0 px-4 pt-3 pb-5 sm:px-8 sm:pb-6">
          <PromptInput value={input} onValueChange={setInput} onSubmit={sendMessage} maxHeight={180} className="rounded-3xl p-3 shadow-sm focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20">
            <PromptInputTextarea aria-label="Your message" placeholder="Ask anything, or start with an idea..." className="px-2 py-3 text-base" />
            <PromptInputActions className="justify-between px-1 pt-2">
              <span className="text-xs text-muted-foreground">Demo chat <span className="hidden sm:inline">· No AI connected</span></span>
              <PromptInputAction tooltip="Send message"><Button size="icon" className="size-9 rounded-full" disabled={!input.trim()} onClick={sendMessage} aria-label="Send message"><ArrowUp className="size-4" /></Button></PromptInputAction>
            </PromptInputActions>
          </PromptInput>
          <p className="mt-3 text-center text-[11px] text-muted-foreground">Enter to send · Shift + Enter for a new line · Messages stay in this session</p>
        </div>
      </main>
    </div>
  );
}
