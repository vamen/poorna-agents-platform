import { create } from 'zustand'
import type { AgentMessage, Session } from '../api/sessions'

interface SessionStore {
  activeSessionId: string | null
  sessions: Record<string, Session>
  messages: Record<string, AgentMessage[]>
  setActiveSession: (id: string | null) => void
  upsertSession: (session: Session) => void
  addMessage: (sessionId: string, message: AgentMessage) => void
  clearSession: (sessionId: string) => void
}

export const useSessionStore = create<SessionStore>((set) => ({
  activeSessionId: null,
  sessions: {},
  messages: {},
  setActiveSession: (id) => set({ activeSessionId: id }),
  upsertSession: (session) =>
    set((state) => ({ sessions: { ...state.sessions, [session.id]: session } })),
  addMessage: (sessionId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [sessionId]: [...(state.messages[sessionId] || []), message],
      },
    })),
  clearSession: (sessionId) =>
    set((state) => {
      const { [sessionId]: _, ...rest } = state.messages
      return { messages: rest }
    }),
}))
