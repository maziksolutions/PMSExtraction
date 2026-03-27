import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { MessageSquare, X, Send, Bot, User, Loader2, AlertCircle } from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

interface Ambiguity {
  id: string
  entity_type: string
  entity_id: string | null
  question_text: string
  context_page: number | null
}

type Tab = 'chat' | 'ambiguities' | 'summary'

const AIAssistant: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const { accessToken } = useAuthStore()

  const [isOpen, setIsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "Hello! I'm your maritime PMS assistant. Ask me anything about the extracted data, or select a row in the grid to get context-aware help.",
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const { data: ambiguitiesData, refetch: refetchAmbiguities } = useQuery({
    queryKey: ['ambiguities', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/assistant/ambiguities`).then((r) => r.data),
    enabled: !!vesselId && isOpen,
  })

  const { data: summaryData, refetch: refetchSummary } = useQuery({
    queryKey: ['assistant-summary', vesselId],
    queryFn: () =>
      apiClient.post(`/vessels/${vesselId}/assistant/batch-summary`, {}).then((r) => r.data),
    enabled: !!vesselId && activeTab === 'summary',
  })

  const resolveAmbiguityMutation = useMutation({
    mutationFn: ({ itemId, resolution }: { itemId: string; resolution: string }) =>
      apiClient
        .post(`/vessels/${vesselId}/assistant/ambiguities/${itemId}/resolve`, { resolution })
        .then((r) => r.data),
    onSuccess: () => refetchAmbiguities(),
  })

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isStreaming || !vesselId) return

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    const currentInput = input.trim()
    setInput('')

    const assistantMsgId = (Date.now() + 1).toString()
    setMessages((prev) => [
      ...prev,
      { id: assistantMsgId, role: 'assistant', content: '', timestamp: new Date() },
    ])
    setIsStreaming(true)

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/vessels/${vesselId}/assistant/chat`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            message: currentInput,
            context_type: 'general',
          }),
        }
      )

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) throw new Error('No reader')

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'delta') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId
                      ? { ...m, content: m.content + data.content }
                      : m
                  )
                )
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: 'Sorry, I encountered an error. Please try again.' }
            : m
        )
      )
    } finally {
      setIsStreaming(false)
    }
  }, [input, isStreaming, vesselId, accessToken])

  const ambiguities: Ambiguity[] = ambiguitiesData?.items ?? []

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-sky-600 shadow-lg hover:bg-sky-500 transition-colors"
        title="AI Assistant"
      >
        {isOpen ? (
          <X className="h-6 w-6 text-white" />
        ) : (
          <MessageSquare className="h-6 w-6 text-white" />
        )}
      </button>

      {/* Chat panel */}
      {isOpen && (
        <div className="fixed bottom-24 right-6 z-50 flex w-96 flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
          style={{ height: '560px' }}>
          {/* Header */}
          <div className="flex items-center gap-2 border-b border-slate-800 bg-slate-800 px-4 py-3">
            <Bot className="h-5 w-5 text-sky-400" />
            <span className="font-semibold text-white">AI Assistant</span>
            {ambiguities.length > 0 && (
              <span className="ml-auto rounded-full bg-amber-600 px-2 py-0.5 text-xs font-bold text-white">
                {ambiguities.length}
              </span>
            )}
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-800">
            {(['chat', 'ambiguities', 'summary'] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 py-2 text-xs font-medium transition-colors ${
                  activeTab === tab
                    ? 'border-b-2 border-sky-500 text-sky-400'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                {tab === 'ambiguities' && ambiguities.length > 0 && (
                  <span className="ml-1 rounded-full bg-amber-600 px-1.5 text-xs text-white">
                    {ambiguities.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Chat tab */}
          {activeTab === 'chat' && (
            <>
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                  >
                    <div
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                        msg.role === 'assistant' ? 'bg-sky-700' : 'bg-slate-700'
                      }`}
                    >
                      {msg.role === 'assistant' ? (
                        <Bot className="h-3.5 w-3.5 text-white" />
                      ) : (
                        <User className="h-3.5 w-3.5 text-white" />
                      )}
                    </div>
                    <div
                      className={`max-w-xs rounded-xl px-3 py-2 text-xs leading-relaxed ${
                        msg.role === 'assistant'
                          ? 'bg-slate-800 text-slate-200'
                          : 'bg-sky-700 text-white'
                      }`}
                    >
                      {msg.content || (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      )}
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
              <div className="border-t border-slate-800 p-3 flex gap-2">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                  placeholder="Ask anything..."
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                  disabled={isStreaming}
                />
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || isStreaming}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-600 text-white hover:bg-sky-500 disabled:opacity-50"
                >
                  {isStreaming ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </button>
              </div>
            </>
          )}

          {/* Ambiguities tab */}
          {activeTab === 'ambiguities' && (
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {ambiguities.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  No pending ambiguities.
                </div>
              ) : (
                ambiguities.map((a) => (
                  <div key={a.id} className="rounded-lg border border-slate-700 bg-slate-800 p-3">
                    <div className="flex items-center gap-1.5 mb-2">
                      <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
                      <span className="text-xs font-medium text-amber-300">{a.entity_type}</span>
                    </div>
                    <p className="text-xs text-slate-200 mb-2">{a.question_text}</p>
                    <button
                      onClick={() => {
                        const resolution = prompt('Your answer:')
                        if (resolution) {
                          resolveAmbiguityMutation.mutate({ itemId: a.id, resolution })
                        }
                      }}
                      className="rounded bg-sky-700 px-2.5 py-1 text-xs text-white hover:bg-sky-600"
                    >
                      Answer
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Summary tab */}
          {activeTab === 'summary' && (
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {summaryData ? (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="rounded-lg bg-slate-800 p-2.5 text-center">
                      <p className="text-lg font-bold text-white">{summaryData.total}</p>
                      <p className="text-xs text-slate-400">Total</p>
                    </div>
                    <div className="rounded-lg bg-amber-900/30 p-2.5 text-center">
                      <p className="text-lg font-bold text-amber-400">{summaryData.pending}</p>
                      <p className="text-xs text-amber-300">Pending</p>
                    </div>
                    <div className="rounded-lg bg-green-900/30 p-2.5 text-center">
                      <p className="text-lg font-bold text-green-400">{summaryData.resolved}</p>
                      <p className="text-xs text-green-300">Resolved</p>
                    </div>
                  </div>
                  <div className="rounded-lg bg-slate-800 p-3">
                    <p className="text-xs text-slate-300">{summaryData.summary}</p>
                  </div>
                  {Object.entries(summaryData.pending_by_entity_type ?? {}).map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between rounded-lg bg-slate-800 px-3 py-2">
                      <span className="text-xs text-slate-300">{type}</span>
                      <span className="rounded-full bg-amber-700 px-2 py-0.5 text-xs text-white">
                        {String(count)}
                      </span>
                    </div>
                  ))}
                </>
              ) : (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  )
}

export default AIAssistant
