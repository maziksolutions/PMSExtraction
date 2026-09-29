import React, { useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Ship,
  Users,
  Shield,
  FolderOpen,
  ClipboardList,
  Wrench,
  BookOpen,
  Package,
  Download,
  Library,
  Layers,
  Plus,
  X,
  Sparkles,
} from 'lucide-react'
import { useTabStore, WorkspaceTab } from '@/store/tabStore'

const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  LayoutDashboard,
  Ship,
  Users,
  Shield,
  FolderOpen,
  ClipboardList,
  Wrench,
  BookOpen,
  Package,
  Download,
  Library,
  Layers,
  Sparkles,
}

export const WorkspaceTabBar: React.FC = () => {
  const navigate = useNavigate()
  const { tabs, activeTabId, switchTab, closeTab, openTab, closeOtherTabs } = useTabStore()
  const tabListRef = useRef<HTMLDivElement>(null)

  // Scroll active tab into view smoothly
  useEffect(() => {
    if (tabListRef.current) {
      const activeEl = tabListRef.current.querySelector('[data-active="true"]') as HTMLElement | null
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
      }
    }
  }, [activeTabId])

  const handleTabClick = (tab: WorkspaceTab) => {
    if (tab.id === activeTabId) return
    const path = switchTab(tab.id)
    if (path) {
      navigate(path)
    }
  }

  const handleClose = (e: React.MouseEvent, tabId: string) => {
    e.stopPropagation()
    const nextPath = closeTab(tabId)
    if (nextPath) {
      navigate(nextPath)
    }
  }

  const handleNewTab = () => {
    const newTabId = openTab('/')
    switchTab(newTabId)
    navigate('/')
  }

  return (
    <div className="flex h-10 w-full shrink-0 items-center border-b border-slate-800 bg-slate-900/90 px-2 backdrop-blur-md">
      {/* Scrollable Tab List */}
      <div
        ref={tabListRef}
        className="flex flex-1 items-center gap-1 overflow-x-auto no-scrollbar py-1"
      >
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId
          const IconComp = tab.icon && ICON_MAP[tab.icon] ? ICON_MAP[tab.icon] : LayoutDashboard

          return (
            <div
              key={tab.id}
              data-active={isActive ? 'true' : 'false'}
              onClick={() => handleTabClick(tab)}
              onAuxClick={(e) => {
                // Middle click closes tab
                if (e.button === 1 && tab.isClosable !== false && tabs.length > 1) {
                  e.preventDefault()
                  handleClose(e, tab.id)
                }
              }}
              className={`group relative flex h-8 max-w-[220px] min-w-[120px] items-center gap-2 rounded-t-lg border-t-2 px-3 text-xs font-medium cursor-pointer select-none transition-all duration-150 ${
                isActive
                  ? 'border-sky-500 bg-slate-950 text-sky-200 shadow-sm'
                  : 'border-transparent bg-slate-900/50 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`}
              title={tab.title}
            >
              <IconComp className={`h-3.5 w-3.5 shrink-0 transition-colors ${isActive ? 'text-sky-400' : 'text-slate-500 group-hover:text-slate-400'}`} />
              
              <span className="truncate flex-1 text-left">{tab.title}</span>

              {/* Close Button */}
              {tab.isClosable !== false && tabs.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => handleClose(e, tab.id)}
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-red-400 transition-colors opacity-70 group-hover:opacity-100"
                  title="Close tab (Middle click)"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
          )
        })}

        {/* Add Tab Button */}
        <button
          type="button"
          onClick={handleNewTab}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-800 hover:text-white transition-colors ml-0.5"
          title="Open new tab (Dashboard)"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
