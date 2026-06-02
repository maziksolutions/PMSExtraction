import React from 'react'

interface ResizableRowSplitViewProps {
  top: React.ReactNode
  bottom: React.ReactNode
  storageKey: string
  initialTopPercent?: number
  minTopPercent?: number
  minBottomPercent?: number
  className?: string
}

const ResizableRowSplitView: React.FC<ResizableRowSplitViewProps> = ({
  top,
  bottom,
  storageKey,
  initialTopPercent = 48,
  minTopPercent = 20,
  minBottomPercent = 20,
  className = '',
}) => {
  const [topPercent, setTopPercent] = React.useState(() => {
    if (typeof window === 'undefined') return initialTopPercent
    const saved = window.localStorage.getItem(storageKey)
    const parsed = saved ? Number(saved) : NaN
    return Number.isFinite(parsed) ? parsed : initialTopPercent
  })
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const dragStateRef = React.useRef<{ active: boolean }>({ active: false })

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, String(topPercent))
    }
  }, [topPercent, storageKey])

  React.useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!dragStateRef.current.active || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      if (!rect.height) return
      const next = ((event.clientY - rect.top) / rect.height) * 100
      const bounded = Math.max(minTopPercent, Math.min(100 - minBottomPercent, next))
      setTopPercent(bounded)
    }

    const handlePointerUp = () => {
      dragStateRef.current.active = false
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [minTopPercent, minBottomPercent])

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    dragStateRef.current.active = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'row-resize'
  }

  return (
    <div ref={containerRef} className={`flex flex-col h-full min-h-0 gap-2 ${className}`}>
      <div
        className="min-h-0 w-full"
        style={{ height: `${topPercent}%`, flex: `0 0 ${topPercent}%` }}
      >
        {top}
      </div>
      <button
        type="button"
        onPointerDown={startDrag}
        className="group relative h-2 w-full shrink-0 cursor-row-resize bg-transparent"
        aria-label="Resize panels"
        title="Drag to resize"
      >
        <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-slate-800 transition-colors group-hover:bg-sky-500" />
        <span className="absolute left-1/2 top-1/2 w-10 h-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-700/80 transition-colors group-hover:bg-sky-500" />
      </button>
      <div className="min-h-0 flex-1 w-full">
        {bottom}
      </div>
    </div>
  )
}

export default ResizableRowSplitView
