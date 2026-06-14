import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Send, Settings, CheckCircle2, AlertCircle, Bot, Compass, Globe, Copy, Check, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
type Source = {
  url: string
  title: string
  source: string
}

type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  loading?: boolean
  stats?: {
    total: number
    search: number
    fetch: number
    respond: number
    cacheHit?: boolean
    webStatus?: string
  }
  error?: string
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Hello! I'm your local AI assistant with web search capabilities. What would you like to know?"
    }
  ])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(() => {
    // Priority: URL param > localStorage
    const params = new URLSearchParams(window.location.search)
    return params.get('session') || localStorage.getItem('searchmesh_session_id')
  })
  const [isProcessing, setIsProcessing] = useState(false)
  const [configData, setConfigData] = useState<any>(null)
  const [isConfigOpen, setIsConfigOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Sync session_id to localStorage + URL whenever it changes
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('searchmesh_session_id', sessionId)
      const params = new URLSearchParams(window.location.search)
      params.set('session', sessionId)
      history.replaceState(null, '', `?${params.toString()}`)
    }
  }, [sessionId])

  const handleCopySession = () => {
    if (!sessionId) return
    navigator.clipboard.writeText(sessionId)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleNewSession = () => {
    localStorage.removeItem('searchmesh_session_id')
    // Remove ?session= from the URL
    const params = new URLSearchParams(window.location.search)
    params.delete('session')
    const newUrl = params.toString() ? `?${params.toString()}` : window.location.pathname
    history.replaceState(null, '', newUrl)
    setSessionId(null)
    setMessages([{
      id: 'welcome',
      role: 'assistant',
      content: "Hello! I'm your local AI assistant with web search capabilities. What would you like to know?"
    }])
  }

  // On mount: if a session_id exists, load its history from the backend
  useEffect(() => {
    if (!sessionId) return
    fetch(`http://localhost:8000/v1/sessions/${sessionId}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data || !data.turns || data.turns.length === 0) return
        const hydrated = data.turns.map((turn: { role: string; content: string }, i: number) => ({
          id: `history-${i}`,
          role: turn.role as 'user' | 'assistant',
          content: turn.content,
        }))
        setMessages(hydrated)
      })
      .catch(() => {/* session not found or Redis down — start fresh */})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isProcessing) return

    const userMsg = input.trim()
    setInput('')
    setIsProcessing(true)

    setMessages(prev => [
      ...prev,
      { id: Date.now().toString(), role: 'user', content: userMsg }
    ])

    const botMsgId = (Date.now() + 1).toString()
    setMessages(prev => [
      ...prev,
      { id: botMsgId, role: 'assistant', content: '', loading: true }
    ])

    try {
      const response = await fetch('http://localhost:8000/v1/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMsg,
          session_id: sessionId,
          use_web: true,
          stream: true
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      setMessages(prev => prev.map(msg => 
        msg.id === botMsgId ? { ...msg, loading: false } : msg
      ))

      const reader = response.body?.getReader()
      const decoder = new TextDecoder("utf-8")
      let responseText = ""

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                
                if (data.type === 'metadata') {
                  setMessages(prev => prev.map(msg => 
                    msg.id === botMsgId ? { ...msg, sources: data.data.results } : msg
                  ))
                } else if (data.type === 'token') {
                  responseText += data.content
                  setMessages(prev => prev.map(msg => 
                    msg.id === botMsgId ? { ...msg, content: responseText } : msg
                  ))
                } else if (data.type === 'final') {
                  setMessages(prev => prev.map(msg => 
                    msg.id === botMsgId ? { 
                      ...msg, 
                      stats: {
                        total: data.data.latency?.total,
                        search: data.data.latency?.search,
                        fetch: data.data.latency?.fetch,
                        respond: data.data.latency?.respond,
                        cacheHit: data.data.cache_hit,
                        webStatus: data.data.metrics?.context_validated ? 'Web context used' : 
                                 (data.data.metrics?.search_used ? 'Searched, but no relevant context' : 'No web search needed')
                      } 
                    } : msg
                  ))
                  if (data.data.session_id) {
                    setSessionId(data.data.session_id)
                  }
                } else if (data.type === 'error') {
                  setMessages(prev => prev.map(msg => 
                    msg.id === botMsgId ? { ...msg, error: data.data.detail } : msg
                  ))
                }
              } catch (e) {
                console.error('Error parsing SSE data:', e, line)
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error:', error)
      setMessages(prev => prev.map(msg => 
        msg.id === botMsgId ? { 
          ...msg, 
          loading: false, 
          error: "Sorry, an error occurred while processing your request." 
        } : msg
      ))
    } finally {
      setIsProcessing(false)
    }
  }

  const handleConfigClick = async () => {
    try {
      const response = await fetch('http://localhost:8000/v1/config')
      const data = await response.json()
      setConfigData(data)
      setIsConfigOpen(true)
    } catch (error) {
      console.error('Could not load config', error)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-background text-foreground font-sans selection:bg-primary/20">
      <header className="flex items-center justify-between px-6 py-4 border-b border-border/40 bg-background/80 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-2 font-medium text-lg tracking-tight">
          <div className="bg-primary text-primary-foreground p-1.5 rounded-lg shadow-sm">
            <Compass className="w-4 h-4" />
          </div>
          Agent Search
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <button
              onClick={handleCopySession}
              title={`Click to copy full session ID:\n${sessionId}`}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-secondary/60 border border-border/40 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
              {sessionId.slice(0, 8)}
            </button>
          )}
          {sessionId && (
            <Button variant="ghost" size="sm" onClick={handleNewSession} title="Start a new session" className="text-muted-foreground hover:text-foreground transition-colors">
              <RotateCcw className="w-4 h-4" />
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={handleConfigClick} className="text-muted-foreground hover:text-foreground transition-colors">
            <Settings className="w-4 h-4 mr-2" />
            Config
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-hidden relative w-full flex flex-col">
        <ScrollArea className="flex-1 w-full" ref={scrollRef}>
          <div className="max-w-3xl w-full mx-auto px-4 py-8 flex flex-col gap-10 pb-32">
            {messages.length === 1 && (
              <div className="flex flex-col items-center justify-center text-center mt-20 mb-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="bg-secondary/50 p-4 rounded-2xl mb-6 shadow-sm border border-border/50">
                  <Compass className="w-8 h-8 text-primary" />
                </div>
                <h1 className="text-3xl font-semibold tracking-tight mb-3">Where to?</h1>
                <p className="text-muted-foreground max-w-md">Search the web or ask me anything. I'm connected to your local agent mesh.</p>
              </div>
            )}
            
            {messages.filter(m => m.id !== 'welcome').map((msg) => (
              <div key={msg.id} className="flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-4 duration-500">
                {msg.role === 'user' ? (
                  <div className="flex justify-end mb-4">
                    <div className="bg-secondary/80 border border-border/50 text-foreground px-5 py-3.5 rounded-3xl max-w-[85%] text-[15px] leading-relaxed shadow-sm">
                      {msg.content}
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-4 w-full">
                    <div className="flex items-center gap-3 text-sm font-medium text-muted-foreground">
                      <div className="bg-primary/10 text-primary p-1.5 rounded-md border border-primary/20">
                        <Bot className="w-3.5 h-3.5" />
                      </div>
                      Agent Search
                    </div>

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-col gap-2.5 w-full mt-1 mb-2">
                        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                          <Globe className="w-3.5 h-3.5" />
                          Sources
                        </div>
                        <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide w-full">
                          {msg.sources.map((source, i) => (
                            <a
                              key={i}
                              href={source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex flex-col justify-between min-w-[220px] max-w-[260px] h-20 p-3.5 rounded-xl border border-border/60 bg-secondary/30 hover:bg-secondary/80 hover:border-border transition-all group shrink-0"
                            >
                              <div className="font-medium text-sm line-clamp-2 leading-tight group-hover:text-primary transition-colors">
                                {source.title}
                              </div>
                              <div className="flex items-center gap-1.5 text-muted-foreground text-xs truncate mt-auto pt-2">
                                <div className="w-3 h-3 rounded-full bg-muted flex items-center justify-center shrink-0">
                                  {source.source === 'duckduckgo' ? '🦆' : '🔍'}
                                </div>
                                <span className="truncate">{new URL(source.url).hostname || source.url}</span>
                              </div>
                            </a>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="text-[15px] leading-relaxed text-foreground/90 prose prose-invert prose-sm max-w-none">
                      {msg.loading ? (
                        <div className="flex items-center gap-1.5 h-6">
                          <div className="w-2 h-2 rounded-full bg-primary/60 animate-pulse" />
                          <div className="w-2 h-2 rounded-full bg-primary/60 animate-pulse delay-150" />
                          <div className="w-2 h-2 rounded-full bg-primary/60 animate-pulse delay-300" />
                        </div>
                      ) : (
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
                            em: ({ children }) => <em className="italic text-foreground/80">{children}</em>,
                            ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                            h1: ({ children }) => <h1 className="text-xl font-bold mb-2 text-foreground">{children}</h1>,
                            h2: ({ children }) => <h2 className="text-lg font-semibold mb-2 text-foreground">{children}</h2>,
                            h3: ({ children }) => <h3 className="text-base font-semibold mb-1 text-foreground">{children}</h3>,
                            code: ({ children }) => <code className="bg-secondary px-1 py-0.5 rounded text-sm font-mono text-primary">{children}</code>,
                            pre: ({ children }) => <pre className="bg-secondary p-3 rounded-lg text-sm font-mono overflow-x-auto mb-2">{children}</pre>,
                            blockquote: ({ children }) => <blockquote className="border-l-2 border-primary/40 pl-3 italic text-muted-foreground mb-2">{children}</blockquote>,
                            a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline underline-offset-2 hover:text-primary/80">{children}</a>,
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      )}
                      {msg.error && (
                        <div className="flex items-center gap-2 text-destructive mt-3 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-sm font-medium">
                          <AlertCircle className="w-4 h-4" />
                          {msg.error}
                        </div>
                      )}
                    </div>

                    {msg.stats && (
                      <div className="flex flex-wrap items-center gap-3 text-[11px] font-medium text-muted-foreground/70 mt-2 border-t border-border/40 pt-3">
                        {msg.stats.webStatus && (
                          <span className="flex items-center gap-1.5">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500/80" />
                            {msg.stats.webStatus}
                          </span>
                        )}
                        <span className="flex items-center gap-1.5">
                          <span className="w-1 h-1 rounded-full bg-muted-foreground/30"></span>
                          {msg.stats.total}ms total
                        </span>
                        {msg.stats.cacheHit && (
                          <span className="text-primary/90 flex items-center gap-1.5">
                            <span className="w-1 h-1 rounded-full bg-primary/50"></span>
                            ⚡ Cache hit
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ScrollArea>

        {/* Input Area */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-background via-background/95 to-transparent pt-10 pb-6 px-4">
          <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative group">
            <div className="absolute inset-0 bg-primary/5 rounded-3xl blur-xl transition-all duration-500 group-focus-within:bg-primary/10"></div>
            <div className="relative flex items-center bg-secondary/80 backdrop-blur-xl border border-border/60 rounded-3xl p-1.5 shadow-lg transition-all duration-300 focus-within:border-primary/30 focus-within:ring-4 focus-within:ring-primary/5">
              <Input
                value={input}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
                placeholder="Ask anything..."
                disabled={isProcessing}
                className="flex-1 bg-transparent border-none shadow-none focus-visible:ring-0 px-4 py-3 h-12 text-[15px]"
              />
              <Button 
                type="submit" 
                disabled={isProcessing || !input.trim()} 
                size="icon"
                className="rounded-full w-10 h-10 shrink-0 mr-0.5 bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm"
              >
                <Send className="w-4 h-4 ml-0.5" />
              </Button>
            </div>
            <div className="text-center mt-3 text-[11px] text-muted-foreground/60 font-medium tracking-wide">
              AI-powered responses may contain inaccuracies.
            </div>
          </form>
        </div>
      </div>
      <Dialog open={isConfigOpen} onOpenChange={setIsConfigOpen}>
        <DialogContent className="sm:max-w-md bg-secondary/90 backdrop-blur-xl border-border/50 text-foreground">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-primary" />
              Agent Configuration
            </DialogTitle>
            <DialogDescription>
              Current runtime configuration and connected services.
            </DialogDescription>
          </DialogHeader>
          {configData && (
            <div className="bg-background/50 border border-border/40 rounded-lg p-4 mt-4 max-h-[60vh] overflow-y-auto">
              <pre className="text-xs text-muted-foreground font-mono whitespace-pre-wrap">
                {JSON.stringify(configData, null, 2)}
              </pre>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
