import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { useTabStore } from '@/store/tabStore'

export const WorkspaceBreadcrumbs: React.FC = () => {
  const navigate = useNavigate()
  const { tabs, activeTabId, navigateBreadcrumb } = useTabStore()

  const activeTab = tabs.find((t) => t.id === activeTabId)
  const breadcrumbs = activeTab?.breadcrumbs || []

  if (breadcrumbs.length === 0) return null

  const handleCrumbClick = (index: number) => {
    // If clicking the current/last crumb, do nothing
    if (index === breadcrumbs.length - 1) return

    const targetPath = navigateBreadcrumb(index)
    if (targetPath) {
      navigate(targetPath)
    }
  }

  return (
    <nav
      aria-label="Breadcrumb"
      className="flex h-7 w-full shrink-0 items-center overflow-x-auto border-b border-slate-800/80 bg-slate-950/70 px-4 text-[11px] text-slate-400 no-scrollbar"
    >
      <ol className="flex items-center gap-1.5 whitespace-nowrap">
        {breadcrumbs.map((crumb, idx) => {
          const isLast = idx === breadcrumbs.length - 1

          return (
            <li key={`${crumb.path}-${idx}`} className="flex items-center gap-1.5">
              {idx > 0 && (
                <ChevronRight className="h-3 w-3 text-slate-600 shrink-0 select-none" />
              )}
              
              {isLast ? (
                <span className="font-semibold text-slate-200 truncate max-w-[240px]">
                  {crumb.title}
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => handleCrumbClick(idx)}
                  className="flex items-center gap-1 text-slate-400 hover:text-sky-300 hover:underline transition-colors truncate max-w-[200px]"
                  title={`Navigate back to ${crumb.title}`}
                >
                  {idx === 0 && <Home className="h-2.5 w-2.5 shrink-0" />}
                  <span>{crumb.title}</span>
                </button>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
