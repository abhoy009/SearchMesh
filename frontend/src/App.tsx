import { useState, useRef, useEffect } from 'react'
import { Send, Settings, CheckCircle2, AlertCircle, Bot, User, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'

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
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

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
      alert(JSON.stringify(data, null, 2))
    } catch (error) {
      alert('Could not load config')
    }
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      <header className="flex items-center justify-between px-6 py-4 border-b">
        <div className="flex items-center gap-2 font-semibold text-lg text-foreground">
          <Search className="w-5 h-5 text-primary" />
          Agent Search
        </div>
        <Button variant="outline" size="sm" onClick={handleConfigClick}>
          <Settings className="w-4 h-4 mr-2" />
          Config
        </Button>
      </header>

      <div className="flex-1 overflow-hidden relative max-w-4xl w-full mx-auto p-4 flex flex-col">
        <ScrollArea className="flex-1 pr-4" ref={scrollRef}>
          <div className="flex flex-col gap-6 pb-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex gap-3 max-w-[85%] ${msg.role === 'user' ? 'self-end flex-row-reverse' : 'self-start'}`}>
                <div className="flex-shrink-0 mt-1">
                  {msg.role === 'user' ? (
                    <div className="bg-primary text-primary-foreground p-1.5 rounded-full">
                      <User className="w-4 h-4" />
                    </div>
                  ) : (
                    <div className="bg-secondary text-secondary-foreground p-1.5 rounded-full">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}
                </div>
                
                <div className="flex flex-col gap-2">
                  <div className={`p-4 rounded-2xl ${msg.role === 'user' ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-secondary text-secondary-foreground rounded-tl-sm'}`}>
                    {msg.loading ? (
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-current animate-bounce" />
                        <div className="w-2 h-2 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
                        <div className="w-2 h-2 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    )}
                    {msg.error && (
                      <div className="flex items-center gap-2 text-destructive mt-2 text-sm font-medium">
                        <AlertCircle className="w-4 h-4" />
                        {msg.error}
                      </div>
                    )}
                  </div>

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="flex gap-2 overflow-x-auto pb-2 -mx-2 px-2 scrollbar-hide">
                      {msg.sources.map((source, i) => (
                        <a
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex flex-col gap-1 min-w-[200px] max-w-[250px] p-3 rounded-xl border bg-card hover:border-primary transition-colors text-sm"
                        >
                          <div className="font-medium truncate">{source.title}</div>
                          <div className="text-muted-foreground text-xs truncate">
                            {new URL(source.url).hostname || source.url}
                          </div>
                        </a>
                      ))}
                    </div>
                  )}

                  {msg.stats && (
                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mt-1">
                      {msg.stats.webStatus && (
                        <span className="flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          {msg.stats.webStatus}
                        </span>
                      )}
                      <span>
                        Total: {msg.stats.total}ms 
                        (Search: {msg.stats.search}ms, Fetch: {msg.stats.fetch}ms, Generate: {msg.stats.respond}ms)
                      </span>
                      {msg.stats.cacheHit && (
                        <span className="text-primary font-medium flex items-center gap-1">
                          ⚡ Cache hit
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>

      <div className="p-4 bg-background border-t">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto flex gap-3 relative">
          <Input
            value={input}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
            placeholder="Ask anything..."
            disabled={isProcessing}
            className="flex-1 rounded-full px-6 py-6 bg-secondary/50 border-secondary focus-visible:ring-primary shadow-sm"
          />
          <Button 
            type="submit" 
            disabled={isProcessing || !input.trim()} 
            size="icon"
            className="rounded-full w-12 h-12 shadow-sm shrink-0"
          >
            <Send className="w-5 h-5" />
          </Button>
        </form>
      </div>
    </div>
  )
}
