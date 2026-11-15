export type ChatMessage = { id: string; role: "user" | "assistant"; content: string };
export type Conversation = {
  id: string;
  title: string;
  messages: ChatMessage[];
  draft: string;
  isLoading: boolean;
  error: string | null;
};

/** Called on a fresh page mount and every explicit New conversation action. */
export function createConversation(): Conversation {
  return {
    id: crypto.randomUUID(), title: "New conversation", messages: [],
    draft: "", isLoading: false, error: null,
  };
}
