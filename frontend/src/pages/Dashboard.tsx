import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  ClipboardCheck,
  Clock,
  FolderOpen,
  Ship,
  TrendingUp,
} from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole, VesselStatus } from '@/types'
import type { PaginatedList, VesselProject } from '@/types'

interface StatCardProps {
  label: string
  value: number | string
  icon: React.ElementType
  color: string
  trend?: string
  onClick?: () => void
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon: Icon, color, trend, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={!onClick}
    className="group flex w-full items-start gap-4 rounded-xl border border-slate-800 bg-slate-900 p-5 text-left shadow transition hover:border-sky-700 hover:bg-slate-800 disabled:cursor-default disabled:hover:border-slate-800 disabled:hover:bg-slate-900"
  >
    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${color}`}>
      <Icon className="h-5 w-5 text-white" />
    </div>
    <div className="flex-1">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-0.5 text-2xl font-bold text-slate-100">{value}</p>
      {trend ? <p className="mt-1 text-xs text-emerald-400">{trend}</p> : null}
    </div>
    {onClick ? <ChevronRight className="mt-1 h-4 w-4 text-slate-500 transition group-hover:text-sky-400" /> : null}
  </button>
)

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
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${cfg.classes}`}>{cfg.label}</span>
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === UserRole.SuperAdmin

  const { data: vesselData, isLoading, isError } = useQuery({
    queryKey: ['vessels', 'dashboard'],
    queryFn: async () => {
      const response = await apiClient.get<PaginatedList<VesselProject>>('/vessels?page=1&page_size=100')
      return response.data
    },
  })

  const vessels = vesselData?.items ?? []
  const recentVessels = vessels.slice(0, 5)
  const totalVessels = vesselData?.total ?? 0

  const activeVessels = vessels.filter(
    (vessel) => vessel.status !== VesselStatus.Complete && vessel.status !== VesselStatus.Draft
  )
  const reviewingVessels = vessels.filter((vessel) => vessel.status === VesselStatus.Reviewing)
  const completedVessels = vessels.filter((vessel) => vessel.status === VesselStatus.Complete)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">
          Welcome back, {user?.full_name?.split(' ')[0] ?? 'User'}
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          Here is an overview of your Maritime PMS projects.
        </p>
      </div>

      {isSuperAdmin ? (
        <div className="flex items-center gap-3 rounded-lg border border-violet-500/30 bg-violet-500/10 px-4 py-3">
          <AlertCircle className="h-4 w-4 shrink-0 text-violet-400" />
          <p className="text-sm text-violet-300">
            You are viewing all tenants as <strong>Super Admin</strong>.
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Vessels"
          value={isLoading ? '...' : totalVessels}
          icon={Ship}
          color="bg-sky-600"
          trend={totalVessels > 0 ? `${totalVessels} project(s)` : undefined}
          onClick={() => navigate('/vessels')}
        />
        <StatCard
          label="Active Projects"
          value={isLoading ? '...' : `${activeVessels.length}/${totalVessels}`}
          icon={FolderOpen}
          color="bg-amber-600"
          onClick={() => navigate(activeVessels[0] ? `/vessels/${activeVessels[0].id}/ingestion` : '/vessels')}
        />
        <StatCard
          label="Pending Reviews"
          value={isLoading ? '...' : `${reviewingVessels.length}/${totalVessels}`}
          icon={ClipboardCheck}
          color="bg-violet-600"
          onClick={() => navigate(reviewingVessels[0] ? `/vessels/${reviewingVessels[0].id}/manuals` : '/vessels')}
        />
        <StatCard
          label="Completed Exports"
          value={isLoading ? '...' : `${completedVessels.length}/${totalVessels}`}
          icon={CheckCircle}
          color="bg-emerald-600"
          trend={completedVessels.length > 0 ? 'Ready for export' : undefined}
          onClick={() => navigate(completedVessels[0] ? `/vessels/${completedVessels[0].id}/export` : '/vessels')}
        />
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 shadow">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-sky-400" />
            <h2 className="font-semibold text-slate-200">Recent Vessel Projects</h2>
          </div>
          <button
            type="button"
            onClick={() => navigate('/vessels')}
            className="text-xs text-sky-400 hover:underline"
          >
            View all
          </button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
            <Clock className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading projects...</span>
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center gap-2 py-12 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Failed to load vessel projects.</span>
          </div>
        ) : recentVessels.length === 0 ? (
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
                {recentVessels.map((vessel) => (
                  <tr
                    key={vessel.id}
                    onClick={() => navigate(`/vessels/${vessel.id}/ingestion`)}
                    className="cursor-pointer transition-colors hover:bg-slate-800/50"
                  >
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
