import React, { useRef, useEffect, useState, useCallback } from 'react'
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
  Copy,
  ArrowRightToLine,
  XCircle,
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

interface ContextMenuState {
  x: number
  y: number
  tabId: string
}

export const WorkspaceTabBar: React.FC = () => {
  const navigate = useNavigate()
  const {
    tabs,
    activeTabId,
    switchTab,
    switchToIndex,
    cycleTab,
    closeTab,
    closeOtherTabs,
    closeTabsToRight,
    duplicateTab,
    openTab,
  } = useTabStore()

  const tabListRef = useRef<HTMLDivElement>(null)
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)

  // Scroll active tab into view smoothly
  useEffect(() => {
    if (tabListRef.current) {
      const activeEl = tabListRef.current.querySelector('[data-active="true"]') as HTMLElement | null
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
      }
    }
  }, [activeTabId])

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 1. Alt + 1..9 directly jumps to tab 1..9
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.key >= '1' && e.key <= '9') {
        e.preventDefault()
        const targetIndex = parseInt(e.key, 10) - 1
        const targetPath = switchToIndex(targetIndex)
        if (targetPath) {
          navigate(targetPath)
        }
        return
      }

      // 2. Alt + ArrowRight / Ctrl + PageDown -> Cycle Next Tab
      if ((e.altKey && e.key === 'ArrowRight') || (e.ctrlKey && e.key === 'PageDown')) {
        e.preventDefault()
        const nextPath = cycleTab('next')
        if (nextPath) {
          navigate(nextPath)
        }
        return
      }

      // 3. Alt + ArrowLeft / Ctrl + PageUp -> Cycle Prev Tab
      if ((e.altKey && e.key === 'ArrowLeft') || (e.ctrlKey && e.key === 'PageUp')) {
        e.preventDefault()
        const prevPath = cycleTab('prev')
        if (prevPath) {
          navigate(prevPath)
        }
        return
      }

      // 4. Alt + W -> Close active tab
      if (e.altKey && (e.key === 'w' || e.key === 'W')) {
        e.preventDefault()
        const nextPath = closeTab(activeTabId)
        if (nextPath) {
          navigate(nextPath)
        }
        return
      }

      // 5. Alt + T -> Open new tab
      if (e.altKey && (e.key === 't' || e.key === 'T')) {
        e.preventDefault()
        const newTabId = openTab('/')
        switchTab(newTabId)
        navigate('/')
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [switchToIndex, cycleTab, closeTab, activeTabId, openTab, switchTab, navigate])

  // Close context menu on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (contextMenu) {
        setContextMenu(null)
      }
    }
    window.addEventListener('click', handleOutsideClick)
    return () => window.removeEventListener('click', handleOutsideClick)
  }, [contextMenu])

  const handleTabClick = (tab: WorkspaceTab) => {
    if (tab.id === activeTabId) return
    const path = switchTab(tab.id)
    if (path) {
      navigate(path)
    }
  }

  const handleClose = useCallback((e: React.MouseEvent, tabId: string) => {
    e.stopPropagation()
    const nextPath = closeTab(tabId)
    if (nextPath) {
      navigate(nextPath)
    }
  }, [closeTab, navigate])

  const handleNewTab = () => {
    const newTabId = openTab('/')
    switchTab(newTabId)
    navigate('/')
  }

  const handleContextMenu = (e: React.MouseEvent, tabId: string) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      tabId,
    })
  }

  const contextTab = tabs.find((t) => t.id === contextMenu?.tabId)
  const contextTabIndex = tabs.findIndex((t) => t.id === contextMenu?.tabId)

  return (
    <div className="relative flex h-10 w-full shrink-0 items-center border-b border-slate-800 bg-slate-900/90 px-2 backdrop-blur-md">
      {/* Scrollable Tab List */}
      <div
        ref={tabListRef}
        className="flex flex-1 items-center gap-1 overflow-x-auto no-scrollbar py-1"
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTabId
          const IconComp = tab.icon && ICON_MAP[tab.icon] ? ICON_MAP[tab.icon] : LayoutDashboard
          const shortcutLabel = index < 9 ? `Alt+${index + 1}` : undefined

          return (
            <div
              key={tab.id}
              data-active={isActive ? 'true' : 'false'}
              onClick={() => handleTabClick(tab)}
              onContextMenu={(e) => handleContextMenu(e, tab.id)}
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
              title={`${tab.title}${shortcutLabel ? ` (${shortcutLabel})` : ''}`}
            >
              <IconComp className={`h-3.5 w-3.5 shrink-0 transition-colors ${isActive ? 'text-sky-400' : 'text-slate-500 group-hover:text-slate-400'}`} />
              
              <span className="truncate flex-1 text-left">{tab.title}</span>

              {/* Close Button */}
              {tab.isClosable !== false && tabs.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => handleClose(e, tab.id)}
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-md text-slate-500 hover:bg-slate-800 hover:text-red-400 transition-colors opacity-70 group-hover:opacity-100"
                  title="Close tab (Alt+W / Middle Click)"
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
          title="Open new tab (Alt+T)"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Right-Click Context Menu */}
      {contextMenu && contextTab && (
        <div
          className="fixed z-50 min-w-[170px] rounded-xl border border-slate-750 bg-slate-900/95 py-1.5 shadow-2xl backdrop-blur-md text-xs font-medium text-slate-200 animate-in fade-in zoom-in-95 duration-100"
          style={{
            top: Math.min(contextMenu.y, window.innerHeight - 180),
            left: Math.min(contextMenu.x, window.innerWidth - 190),
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Duplicate Tab */}
          <button
            type="button"
            onClick={() => {
              const nextPath = duplicateTab(contextTab.id)
              if (nextPath) navigate(nextPath)
              setContextMenu(null)
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-slate-800 hover:text-white transition-colors text-left"
          >
            <Copy className="h-3.5 w-3.5 text-slate-400" />
            <span>Duplicate Tab</span>
          </button>

          {/* Close Tab */}
          {contextTab.isClosable !== false && tabs.length > 1 && (
            <button
              type="button"
              onClick={(e) => {
                handleClose(e, contextTab.id)
                setContextMenu(null)
              }}
              className="flex w-full items-center justify-between px-3 py-1.5 hover:bg-slate-800 hover:text-white transition-colors text-left"
            >
              <div className="flex items-center gap-2">
                <X className="h-3.5 w-3.5 text-slate-400" />
                <span>Close Tab</span>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">Alt+W</span>
            </button>
          )}

          <div className="my-1 border-t border-slate-800" />

          {/* Close Other Tabs */}
          {tabs.length > 1 && (
            <button
              type="button"
              onClick={() => {
                closeOtherTabs(contextTab.id)
                setContextMenu(null)
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-slate-800 hover:text-white transition-colors text-left"
            >
              <XCircle className="h-3.5 w-3.5 text-slate-400" />
              <span>Close Other Tabs</span>
            </button>
          )}

          {/* Close Tabs to Right */}
          {contextTabIndex >= 0 && contextTabIndex < tabs.length - 1 && (
            <button
              type="button"
              onClick={() => {
                closeTabsToRight(contextTab.id)
                setContextMenu(null)
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-slate-800 hover:text-white transition-colors text-left"
            >
              <ArrowRightToLine className="h-3.5 w-3.5 text-slate-400" />
              <span>Close Tabs to the Right</span>
            </button>
          )}

          <div className="my-1 border-t border-slate-800" />

          {/* New Tab */}
          <button
            type="button"
            onClick={() => {
              handleNewTab()
              setContextMenu(null)
            }}
            className="flex w-full items-center justify-between px-3 py-1.5 hover:bg-slate-800 hover:text-white transition-colors text-left"
          >
            <div className="flex items-center gap-2">
              <Plus className="h-3.5 w-3.5 text-slate-400" />
              <span>New Tab</span>
            </div>
            <span className="text-[10px] text-slate-500 font-mono">Alt+T</span>
          </button>
        </div>
      )}
    </div>
  )
}
