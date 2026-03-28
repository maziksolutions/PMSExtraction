import React, { useState } from 'react'
import { NavLink, Outlet, useParams } from 'react-router-dom'
import {
  LayoutDashboard,
  Ship,
  Users,
  Settings,
  LogOut,
  Menu,
  ChevronRight,
  MessageSquare,
  BarChart2,
  Shield,
  FolderOpen,
  ClipboardList,
  Wrench,
  Package,
  BookOpen,
  Download,
  Library,
  ClipboardCheck,
  Zap,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useAuth } from '@/hooks/useAuth'
import { UserRole } from '@/types'
import ActivityFeed from '@/components/ActivityFeed'
import PresenceIndicators from '@/components/PresenceIndicators'
import AIAssistant from '@/components/AIAssistant'
import { useVesselSocket } from '@/hooks/useVesselSocket'

const roleLabels: Record<UserRole, string> = {
  [UserRole.SuperAdmin]: 'Super Admin',
  [UserRole.VesselAdmin]: 'Vessel Admin',
  [UserRole.QCReviewer]: 'QC Reviewer',
  [UserRole.Viewer]: 'Viewer',
  [UserRole.ApiIntegration]: 'API Integration',
}

const roleBadgeColors: Record<UserRole, string> = {
  [UserRole.SuperAdmin]: 'bg-violet-600 text-violet-100',
  [UserRole.VesselAdmin]: 'bg-sky-600 text-sky-100',
  [UserRole.QCReviewer]: 'bg-amber-600 text-amber-100',
  [UserRole.Viewer]: 'bg-slate-600 text-slate-100',
  [UserRole.ApiIntegration]: 'bg-emerald-700 text-emerald-100',
}

const topNavItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/vessels', label: 'Vessels', icon: Ship },
  { to: '/library', label: 'Library', icon: Library },
  { to: '/users', label: 'Users', icon: Users, requiredRole: UserRole.SuperAdmin },
  { to: '/feedback', label: 'Feedback', icon: BarChart2, requiredRole: UserRole.SuperAdmin },
  { to: '/admin/extraction-prompts', label: 'Extraction Prompts', icon: Zap, requiredRole: UserRole.SuperAdmin },
  { to: '/admin', label: 'Admin', icon: Shield, requiredRole: UserRole.SuperAdmin },
]

// Vessel-level nav items — shown when vesselId is in route params
const vesselNavItems = (vesselId: string) => [
  { to: `/vessels/${vesselId}/precheck`, label: 'Pre-Check', icon: ClipboardCheck },
  { to: `/vessels/${vesselId}/ingestion`, label: 'Ingestion', icon: FolderOpen },
  { to: `/vessels/${vesselId}/manuals`, label: 'Manuals', icon: ClipboardList },
  { to: `/vessels/${vesselId}/components`, label: 'Components', icon: Wrench },
  { to: `/vessels/${vesselId}/jobs`, label: 'Jobs', icon: BookOpen },
  { to: `/vessels/${vesselId}/spares`, label: 'Spares', icon: Package },
  { to: `/vessels/${vesselId}/standard-jobs`, label: 'Standard Jobs', icon: ClipboardList },
  { to: `/vessels/${vesselId}/export`, label: 'Export', icon: Download },
]

const Layout: React.FC = () => {
  const { user } = useAuthStore()
  const { logout } = useAuth()
  const { vesselId } = useParams<{ vesselId?: string }>()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)

  const { presenceList, activityFeed, isConnected } = useVesselSocket(vesselId)

  const userRole = user?.role as UserRole | undefined

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    [
      'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150',
      isActive
        ? 'bg-sky-500/20 text-sky-400 shadow-inner'
        : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100',
    ].join(' ')

  const SidebarContent = () => (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b border-slate-800 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-500 shadow">
          <Ship className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-sm font-bold leading-tight text-white">Maritime PMS</p>
          <p className="text-xs leading-tight text-slate-400">Union Maritime</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-widest text-slate-600">
          Main Menu
        </p>
        {topNavItems.map((item) => {
          if (item.requiredRole && userRole !== item.requiredRole) return null
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.exact}
              className={navLinkClass}
              onClick={() => setSidebarOpen(false)}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
              <ChevronRight className="ml-auto h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" />
            </NavLink>
          )
        })}

        {/* Vessel-level nav when inside a vessel context */}
        {vesselId && (
          <>
            <p className="mb-2 mt-4 px-3 text-xs font-semibold uppercase tracking-widest text-slate-600">
              Vessel Workflow
            </p>
            {vesselNavItems(vesselId).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={navLinkClass}
                onClick={() => setSidebarOpen(false)}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* User info at bottom */}
      <div className="border-t border-slate-800 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-white uppercase">
            {user?.full_name?.charAt(0) ?? 'U'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-200">{user?.full_name}</p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={logout}
          className="mt-3 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-800 hover:text-red-400"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col bg-slate-900 md:flex">
        <SidebarContent />
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative z-50 w-64 bg-slate-900">
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-4 md:px-6">
          <div className="flex items-center gap-3">
            <button
              className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white md:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="hidden text-sm font-semibold text-slate-200 md:block">
              Maritime PMS Data Extraction Tool
            </h1>
          </div>

          <div className="flex items-center gap-3">
            {/* Presence indicators — shown when in a vessel context */}
            {vesselId && (
              <PresenceIndicators users={presenceList} isConnected={isConnected} />
            )}

            {userRole && (
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${roleBadgeColors[userRole]}`}
              >
                {roleLabels[userRole]}
              </span>
            )}

            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-sky-600 text-sm font-semibold text-white uppercase">
              {user?.full_name?.charAt(0) ?? 'U'}
            </div>
            <span className="hidden text-sm text-slate-300 md:block">{user?.full_name}</span>

            {/* Activity feed toggle — shown when in a vessel context */}
            {vesselId && (
              <button
                onClick={() => setActivityOpen((o) => !o)}
                className={`rounded-lg p-2 text-sm transition-colors ${
                  activityOpen
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
                title="Activity Feed"
              >
                <MessageSquare className="h-4 w-4" />
              </button>
            )}
          </div>
        </header>

        {/* Body: page content + optional activity feed panel */}
        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto bg-slate-950 p-4 md:p-6">
            <Outlet />
          </main>

          {/* Activity Feed side panel */}
          {vesselId && activityOpen && (
            <aside className="hidden w-80 shrink-0 border-l border-slate-800 bg-slate-900 md:block">
              <ActivityFeed events={activityFeed} />
            </aside>
          )}
        </div>
      </div>

      {/* AI Assistant floating widget — shown on all vessel pages (gets vesselId from URL params internally) */}
      {vesselId && <AIAssistant />}
    </div>
  )
}

export default Layout
