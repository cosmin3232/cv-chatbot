"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, ArrowUpRight, Check, Code2, Copy, Lightbulb, MessageSquare, PanelLeft, Plus, Search, Sparkles, SquarePen, Trash2, X } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ChatContainerContent, ChatContainerRoot } from "@/components/ui/chat-container";
import { Message, MessageAction, MessageActions, MessageContent } from "@/components/ui/message";
import { PromptInput, PromptInputAction, PromptInputActions, PromptInputTextarea } from "@/components/ui/prompt-input";
import { PromptSuggestion } from "@/components/ui/prompt-suggestion";
import { ScrollButton } from "@/components/ui/scroll-button";
import { cn } from "@/lib/utils";
import { agentService } from "@/services/agent-service";
import { HttpError } from "@/services/http-client";

type ChatMessage = { id: string; role: "user" | "assistant"; content: string };
type Conversation = { id: string; title: string; messages: ChatMessage[]; draft: string; isLoading: boolean; error: string | null };

const suggestions = [
  { icon: Lightbulb, title: "Career overview", description: "Get to know the candidate", prompt: "Give me a brief overview of the candidate's professional background.", color: "bg-amber-50 text-amber-700" },
  { icon: SquarePen, title: "Experience", description: "Explore roles and achievements", prompt: "What relevant work experience and achievements does the candidate have?", color: "bg-blue-50 text-blue-700" },
  { icon: Code2, title: "Skills and projects", description: "Discover technical strengths", prompt: "What technical skills and projects are described in the CV?", color: "bg-violet-50 text-violet-700" },
  { icon: MessageSquare, title: "Role suitability", description: "Find evidence for your opening", prompt: "Based on the provided information, what types of roles could suit this candidate and why?", color: "bg-emerald-50 text-emerald-700" },
];

const initialConversation: Conversation = { id: "initial", title: "New conversation", messages: [], draft: "", isLoading: false, error: null };

function CopyMessage({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setError("");
    } catch {
      setError("Couldn't copy. Select the message to copy it manually.");
    }
  }
  return (
    <MessageActions className="mt-2">
      <MessageAction tooltip={copied ? "Copied" : "Copy message"}>
        <Button variant="ghost" size="icon-sm" aria-label={copied ? "Message copied" : "Copy message"} onClick={copy}>
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
        </Button>
      </MessageAction>
      <span role="status" className="text-xs">{error || (copied ? "Copied" : "")}</span>
    </MessageActions>
  );
}

export function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([initialConversation]);
  const [activeId, setActiveId] = useState("initial");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [query, setQuery] = useState("");
  const composerRef = useRef<HTMLDivElement>(null);
  const requests = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const pending = requests.current;
    return () => {
      pending.forEach((controller) => controller.abort());
      pending.clear();
    };
  }, []);
  const active = conversations.find((conversation) => conversation.id === activeId) ?? conversations[0];
  const visibleConversations = conversations.filter((conversation) => conversation.title.toLowerCase().includes(query.toLowerCase()));

  function setDraft(draft: string) {
    setConversations((previous) => previous.map((conversation) => conversation.id === active.id ? { ...conversation, draft } : conversation));
  }

  async function sendMessage() {
    const content = active.draft.trim();
    const conversationId = active.id;
    if (!content || requests.current.has(conversationId)) return;
    const controller = new AbortController();
    requests.current.set(conversationId, controller);
    const message: ChatMessage = { id: crypto.randomUUID(), role: "user", content };
    setConversations((previous) => previous.map((conversation) => conversation.id === conversationId ? {
      ...conversation,
      title: conversation.messages.length ? conversation.title : content.slice(0, 60),
      messages: [...conversation.messages, message],
      draft: "",
      isLoading: true,
      error: null,
    } : conversation));

    try {
      const response = await agentService.sendPrompt({
        conversationId,
        prompt: content,
        history: active.messages.map(({ role, content }) => ({ role, content })),
      }, { signal: controller.signal });
      if (controller.signal.aborted) return;
      const reply: ChatMessage = { id: crypto.randomUUID(), role: "assistant", content: response.content };
      setConversations((previous) => previous.map((conversation) => conversation.id === conversationId ? {
        ...conversation, messages: [...conversation.messages, reply], isLoading: false,
      } : conversation));
    } catch (error) {
      if (controller.signal.aborted) return;
      const reason = error instanceof HttpError && error.status === 429
        ? "Too many requests. Please wait a minute and try again."
        : error instanceof HttpError && error.status === 503
          ? "The assistant is busy or not configured yet. Please try again shortly."
          : "The assistant couldn't respond. Check the connection and try again.";
      setConversations((previous) => previous.map((conversation) => conversation.id === conversationId ? {
        ...conversation, isLoading: false, draft: content,
        messages: conversation.messages.filter((entry) => entry.id !== message.id),
        error: `${reason} Your prompt is back in the input.`,
      } : conversation));
    } finally {
      requests.current.delete(conversationId);
    }
  }

  function newChat() {
    const empty = conversations.find((conversation) => !conversation.messages.length && !conversation.draft);
    if (empty) setActiveId(empty.id);
    else {
      const conversation = { ...initialConversation, id: crypto.randomUUID() };
      setConversations((previous) => [conversation, ...previous]);
      setActiveId(conversation.id);
    }
    setSidebarOpen(false);
    setQuery("");
    composerRef.current?.querySelector("textarea")?.focus();
  }

  function deleteChat() {
    requests.current.get(active.id)?.abort();
    requests.current.delete(active.id);
    const remaining = conversations.filter((conversation) => conversation.id !== active.id);
    const next = remaining.length ? remaining : [{ ...initialConversation, id: crypto.randomUUID() }];
    setConversations(next);
    setActiveId(next[0].id);
  }

  return (
    <div className="flex h-dvh min-h-0 bg-background text-foreground">
      <aside id="conversation-sidebar" aria-label="Conversations" className={cn("w-full shrink-0 flex-col border-r bg-[#f7f8fa] md:flex md:w-64 lg:w-72", sidebarOpen ? "flex" : "hidden")}>
        <div className="flex h-20 shrink-0 items-center justify-between px-6">
          <a href="/" className="flex items-center gap-2.5 text-base font-semibold tracking-tight"><span className="flex size-8 items-center justify-center rounded-xl bg-zinc-900 text-white"><Sparkles className="size-4" aria-hidden="true" /></span> Personal Chat<span className="sr-only"> home</span></a>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="Close conversations" onClick={() => setSidebarOpen(false)}><X /></Button>
        </div>
        <div className="space-y-4 px-4">
          <Button onClick={newChat} className="h-10 w-full justify-start gap-2 rounded-xl"><Plus className="size-4" />New conversation</Button>
          <label className="flex items-center gap-2 rounded-lg border bg-white px-3 focus-within:ring-2 focus-within:ring-ring/30">
            <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
            <input aria-label="Search conversations" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search conversations" className="h-9 w-full min-w-0 bg-transparent text-xs outline-none" />
          </label>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-7">
          <p className="mb-3 px-3 text-[10px] font-semibold tracking-[0.15em] text-muted-foreground uppercase">This session</p>
          <nav aria-label="Conversation history" className="space-y-1">
            {visibleConversations.map((conversation) => (
              <Button key={conversation.id} variant="ghost" aria-current={conversation.id === active.id ? "page" : undefined} onClick={() => { setActiveId(conversation.id); setSidebarOpen(false); }} className={cn("h-10 w-full justify-start gap-2.5 rounded-lg px-3 text-xs font-normal", conversation.id === active.id && "bg-white shadow-xs")}>
                <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" /><span className="truncate">{conversation.title}</span>
              </Button>
            ))}
            {!visibleConversations.length && <p className="px-3 text-xs leading-5 text-muted-foreground">No conversations match your search.</p>}
          </nav>
        </div>
        <div className="m-4 rounded-xl border bg-white p-4"><p className="flex items-center gap-2 text-xs font-medium"><Sparkles className="size-3.5" />About the candidate</p><p className="mt-2 text-xs leading-5 text-muted-foreground">Ask about experience, skills, and projects. Answers are based on the supplied CV and notes.</p></div>
        <div className="flex items-center gap-3 border-t px-5 py-4"><Avatar><AvatarFallback className="bg-zinc-200 text-xs">Y</AvatarFallback></Avatar><div><p className="text-xs font-medium">Your workspace</p><p className="mt-0.5 text-[11px] text-muted-foreground">Conversations stay in this session</p></div></div>
      </aside>

      <main className={cn("min-w-0 flex-1 flex-col", sidebarOpen ? "hidden md:flex" : "flex")}>
        <header className="flex h-20 shrink-0 items-center justify-between gap-4 px-5 sm:px-9">
          <div className="flex min-w-0 items-center gap-3">
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open conversations" aria-expanded={sidebarOpen} aria-controls="conversation-sidebar" onClick={() => setSidebarOpen(true)}><PanelLeft /></Button>
            <div className="min-w-0"><p className="truncate text-sm font-medium">{active.messages.length ? active.title : "Meet the candidate"}</p><p className="mt-0.5 text-xs text-muted-foreground">Experience, skills, and the story behind the CV</p></div>
          </div>
          {active.messages.length > 0 && <Button variant="ghost" size="icon" aria-label="Delete current conversation" onClick={deleteChat}><Trash2 className="size-4 text-muted-foreground" /></Button>}
        </header>

        {active.messages.length === 0 ? (
          <section aria-labelledby="welcome-title" className="flex min-h-0 flex-1 overflow-y-auto px-6">
            <div className="m-auto w-full max-w-2xl py-10 sm:py-14">
              <div className="mb-7 flex size-14 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 shadow-xs"><Sparkles className="size-6 text-zinc-700" strokeWidth={1.5} aria-hidden="true" /></div>
              <p className="mb-3 text-xs font-medium tracking-wide text-muted-foreground">For curious recruiters and future teammates</p>
              <h1 id="welcome-title" className="text-4xl leading-tight font-medium tracking-[-0.045em] sm:text-5xl">Go beyond the CV.<br />Start a conversation.</h1>
              <p className="mt-5 max-w-md text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">Explore the candidate&apos;s background, projects, and experience. What would you like to know?</p>
              <div className="mt-9 grid gap-3 sm:grid-cols-2">
                {suggestions.map(({ icon: Icon, title, description, prompt, color }) => (
                  <PromptSuggestion key={title} onClick={() => { setDraft(prompt); composerRef.current?.querySelector("textarea")?.focus(); }} className="group h-auto justify-start gap-3 rounded-xl border-zinc-200 p-4 text-left whitespace-normal hover:border-zinc-300 hover:bg-zinc-50">
                    <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg", color)}><Icon className="size-4" aria-hidden="true" /></span>
                    <span className="flex min-w-0 flex-1 flex-col gap-1"><span className="text-xs font-medium sm:text-sm">{title}</span><span className="text-[11px] font-normal text-muted-foreground sm:text-xs">{description}</span></span>
                    <ArrowUpRight className="size-3.5 shrink-0 text-zinc-400 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden="true" />
                  </PromptSuggestion>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <ChatContainerRoot key={active.id} className="relative min-h-0 flex-1" aria-label="Conversation messages" aria-live="polite">
            <ChatContainerContent className="mx-auto max-w-3xl gap-8 px-5 py-8 sm:px-8">
              {active.messages.map((message) => (
                <Message key={message.id} className={message.role === "user" ? "justify-end" : "justify-start"}>
                  {message.role === "assistant" && <span className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-xl bg-zinc-900 text-white"><Sparkles className="size-4" aria-hidden="true" /></span>}
                  <div className="min-w-0 max-w-[85%]">
                    <p className="mb-2 text-xs font-medium text-muted-foreground">{message.role === "user" ? "You" : "Personal Chat"}</p>
                    <MessageContent markdown={message.role === "assistant"} className={message.role === "user" ? "rounded-2xl px-4 py-3 text-sm leading-6 whitespace-pre-wrap [overflow-wrap:anywhere]" : "space-y-3 bg-transparent p-0 text-sm leading-7 [overflow-wrap:anywhere] [&_p]:my-3 [&_p:first-child]:mt-0"}>{message.content}</MessageContent>
                    {message.role === "assistant" && <CopyMessage content={message.content} />}
                  </div>
                </Message>
              ))}
              {active.isLoading && <div role="status" className="flex items-center gap-3 text-sm text-muted-foreground"><Sparkles className="size-4 motion-safe:animate-pulse" aria-hidden="true" />Waiting for the agent...</div>}
            </ChatContainerContent>
            <ScrollButton aria-label="Scroll to latest message" className="absolute bottom-4 left-1/2 -translate-x-1/2" />
          </ChatContainerRoot>
        )}

        <div ref={composerRef} className="mx-auto w-full max-w-3xl shrink-0 px-4 pt-3 pb-5 sm:px-8 sm:pb-7">
          {active.error && <p role="alert" className="mb-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 text-sm text-destructive">{active.error}</p>}
          <PromptInput value={active.draft} onValueChange={setDraft} onSubmit={() => void sendMessage()} isLoading={active.isLoading} disabled={active.isLoading} maxHeight={160} className="rounded-2xl border-zinc-200 p-3 shadow-[0_4px_24px_-12px_#00000020] focus-within:border-zinc-400 focus-within:ring-2 focus-within:ring-zinc-100">
            <PromptInputTextarea aria-label="Your message" placeholder="Ask about experience, skills, or projects..." maxLength={2000} className="min-h-14 px-2 py-3 text-sm" />
            <PromptInputActions className="justify-between px-1 pt-1">
              <span className="flex items-center gap-1.5 px-1 text-[11px] text-muted-foreground"><Sparkles className="size-3" aria-hidden="true" />CV assistant</span>
              <PromptInputAction tooltip="Send message"><Button size="icon" className="size-9 rounded-xl" disabled={active.isLoading || !active.draft.trim()} onClick={() => void sendMessage()} aria-label="Send message"><ArrowUp className="size-4" /></Button></PromptInputAction>
            </PromptInputActions>
          </PromptInput>
          <p className="mt-3 text-center text-[10px] leading-4 text-muted-foreground sm:text-[11px]">Enter to send · Shift + Enter for a new line · Confirm important details with the candidate</p>
        </div>
      </main>
    </div>
  );
}
