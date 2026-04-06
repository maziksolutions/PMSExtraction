import React from 'react'

interface ResizableSplitViewProps {
  left: React.ReactNode
  right: React.ReactNode
  storageKey: string
  initialLeftPercent?: number
  minLeftPercent?: number
  minRightPercent?: number
  className?: string
}

const ResizableSplitView: React.FC<ResizableSplitViewProps> = ({
  left,
  right,
  storageKey,
  initialLeftPercent = 58,
  minLeftPercent = 30,
  minRightPercent = 24,
  className = '',
}) => {
  const [leftPercent, setLeftPercent] = React.useState(() => {
    if (typeof window === 'undefined') return initialLeftPercent
    const saved = window.localStorage.getItem(storageKey)
    const parsed = saved ? Number(saved) : NaN
    return Number.isFinite(parsed) ? parsed : initialLeftPercent
  })
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const dragStateRef = React.useRef<{ active: boolean }>({ active: false })

  React.useEffect(() => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(storageKey, String(leftPercent))
    }
  }, [leftPercent, storageKey])

  React.useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!dragStateRef.current.active || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      if (!rect.width) return
      const next = ((event.clientX - rect.left) / rect.width) * 100
      const bounded = Math.max(minLeftPercent, Math.min(100 - minRightPercent, next))
      setLeftPercent(bounded)
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
  }, [minLeftPercent, minRightPercent])

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    dragStateRef.current.active = true
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
  }

  return (
    <div ref={containerRef} className={`flex h-full min-h-0 gap-4 ${className}`}>
      <div
        className="min-w-0"
        style={{ width: `${leftPercent}%`, flex: `0 0 ${leftPercent}%` }}
      >
        {left}
      </div>
      <button
        type="button"
        onPointerDown={startDrag}
        className="group relative hidden w-3 shrink-0 cursor-col-resize rounded-full bg-transparent xl:block"
        aria-label="Resize panels"
        title="Drag to resize"
      >
        <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-slate-800 transition-colors group-hover:bg-sky-500" />
        <span className="absolute left-1/2 top-1/2 h-10 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-slate-700/80 transition-colors group-hover:bg-sky-500" />
      </button>
      <div className="min-w-0 flex-1">
        {right}
      </div>
    </div>
  )
}

export default ResizableSplitView
