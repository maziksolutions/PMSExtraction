import React from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Ship,
  FolderOpen,
  ClipboardCheck,
  CheckCircle,
  TrendingUp,
  Clock,
  AlertCircle,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole, VesselStatus } from '@/types'
import type { VesselProject, PaginatedList } from '@/types'

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

interface StatCardProps {
  label: string
  value: number | string
  icon: React.ElementType
  color: string
  trend?: string
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon: Icon, color, trend }) => (
  <div className="flex items-start gap-4 rounded-xl border border-slate-800 bg-slate-900 p-5 shadow">
    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${color}`}>
      <Icon className="h-5 w-5 text-white" />
    </div>
    <div>
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-0.5 text-2xl font-bold text-slate-100">{value}</p>
      {trend && <p className="mt-1 text-xs text-emerald-400">{trend}</p>}
    </div>
  </div>
)

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

const statusConfig: Record<VesselStatus, { label: string; classes: string }> = {
  [VesselStatus.Draft]: { label: 'Draft', classes: 'bg-slate-700 text-slate-300' },
  [VesselStatus.Ingesting]: { label: 'Ingesting', classes: 'bg-blue-700 text-blue-200' },
  [VesselStatus.Classifying]: { label: 'Classifying', classes: 'bg-amber-700 text-amber-200' },
  [VesselStatus.Reviewing]: { label: 'Reviewing', classes: 'bg-violet-700 text-violet-200' },
  [VesselStatus.Exporting]: { label: 'Exporting', classes: 'bg-sky-700 text-sky-200' },
  [VesselStatus.Complete]: { label: 'Complete', classes: 'bg-emerald-700 text-emerald-200' },
}

const StatusBadge: React.FC<{ status: VesselStatus }> = ({ status }) => {
  const cfg = statusConfig[status] ?? { label: status, classes: 'bg-slate-700 text-slate-300' }
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.classes}`}>
      {cfg.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

const Dashboard: React.FC = () => {
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === UserRole.SuperAdmin

  const { data: vesselData, isLoading, isError } = useQuery({
    queryKey: ['vessels', 'dashboard'],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedList<VesselProject>>('/vessels?page=1&page_size=5')
      return response.data
    },
  })

  const vessels = vesselData?.items ?? []
  const totalVessels = vesselData?.total ?? 0

  const activeCount = vessels.filter(
    (v) =>
      v.status !== VesselStatus.Complete &&
      v.status !== VesselStatus.Draft
  ).length

  const reviewingCount = vessels.filter((v) => v.status === VesselStatus.Reviewing).length
  const completedCount = vessels.filter((v) => v.status === VesselStatus.Complete).length

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100">
          Welcome back, {user?.full_name?.split(' ')[0] ?? 'User'}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Here is an overview of your Maritime PMS projects.
        </p>
      </div>

      {/* Role-aware notice */}
      {isSuperAdmin && (
        <div className="flex items-center gap-3 rounded-lg border border-violet-500/30 bg-violet-500/10 px-4 py-3">
          <AlertCircle className="h-4 w-4 shrink-0 text-violet-400" />
          <p className="text-sm text-violet-300">
            You are viewing all tenants as <strong>Super Admin</strong>.
          </p>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Vessels"
          value={isLoading ? '…' : totalVessels}
          icon={Ship}
          color="bg-sky-600"
          trend={totalVessels > 0 ? `${totalVessels} project(s)` : undefined}
        />
        <StatCard
          label="Active Projects"
          value={isLoading ? '…' : activeCount}
          icon={FolderOpen}
          color="bg-amber-600"
        />
        <StatCard
          label="Pending Reviews"
          value={isLoading ? '…' : reviewingCount}
          icon={ClipboardCheck}
          color="bg-violet-600"
        />
        <StatCard
          label="Completed Exports"
          value={isLoading ? '…' : completedCount}
          icon={CheckCircle}
          color="bg-emerald-600"
          trend={completedCount > 0 ? 'Ready for export' : undefined}
        />
      </div>

      {/* Recent vessels table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 shadow">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-sky-400" />
            <h2 className="font-semibold text-slate-200">Recent Vessel Projects</h2>
          </div>
          <a href="/vessels" className="text-xs text-sky-400 hover:underline">
            View all
          </a>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
            <Clock className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading projects…</span>
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center gap-2 py-12 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Failed to load vessel projects.</span>
          </div>
        ) : vessels.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-slate-500">
            <Ship className="mb-3 h-10 w-10 opacity-30" />
            <p className="text-sm font-medium">No vessel projects yet.</p>
            <p className="text-xs">Create your first project in the Vessels section.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Vessel
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    IMO Number
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Type
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Status
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {vessels.map((vessel) => (
                  <tr key={vessel.id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-5 py-3 font-medium text-slate-200">{vessel.name}</td>
                    <td className="px-5 py-3 font-mono text-slate-400">{vessel.imo_number}</td>
                    <td className="px-5 py-3 text-slate-400">{vessel.vessel_type}</td>
                    <td className="px-5 py-3">
                      <StatusBadge status={vessel.status} />
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(vessel.created_at).toLocaleDateString('en-GB')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Dashboard
