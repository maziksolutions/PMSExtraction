import React from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Brain, TrendingUp, AlertCircle, Zap } from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole } from '@/types'

interface DashboardData {
  total_corrections_by_type: Record<string, number>
  correction_rate_trend: { week: string; count: number }[]
  current_model_version: string
  pending_fine_tune_count: number
  false_positive_rate_by_category: Record<string, number>
  false_negative_rate_by_category: Record<string, number>
}

const CORRECTION_COLORS: Record<string, string> = {
  false_positive: 'bg-red-700',
  false_negative: 'bg-amber-700',
  wrong_value: 'bg-blue-700',
  wrong_mapping: 'bg-purple-700',
}

const FeedbackDashboard: React.FC = () => {
  const { user } = useAuthStore()
  const isSuperAdmin = user?.role === UserRole.SuperAdmin

  const { data, isLoading } = useQuery<DashboardData>({
    queryKey: ['feedback-dashboard'],
    queryFn: () => apiClient.get('/feedback/dashboard').then((r) => r.data),
  })

  const triggerFineTuneMutation = useMutation({
    mutationFn: () => apiClient.post('/feedback/trigger-fine-tune').then((r) => r.data),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="text-slate-500">Loading feedback data...</div>
      </div>
    )
  }

  const totalCorrections = Object.values(data?.total_corrections_by_type ?? {}).reduce(
    (a, b) => a + b,
    0
  )
  const trend = data?.correction_rate_trend ?? []
  const maxTrendCount = Math.max(...trend.map((t) => t.count), 1)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Feedback & Model Performance</h1>
          <p className="mt-1 text-sm text-slate-400">
            Track correction patterns and manage AI model improvements.
          </p>
        </div>
        {isSuperAdmin && (
          <button
            onClick={() => triggerFineTuneMutation.mutate()}
            disabled={triggerFineTuneMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
          >
            <Brain className="h-4 w-4" />
            {triggerFineTuneMutation.isPending ? 'Requesting...' : 'Trigger Fine-tune'}
          </button>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-2xl font-bold text-white">{totalCorrections}</p>
          <p className="text-sm text-slate-400">Total Corrections</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-2xl font-bold text-white">
            {trend.length > 0 ? trend[trend.length - 1].count : 0}
          </p>
          <p className="text-sm text-slate-400">This Week</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-2xl font-bold text-amber-400">{data?.pending_fine_tune_count ?? 0}</p>
          <p className="text-sm text-slate-400">Pending Fine-tune</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <p className="text-lg font-bold text-sky-400">{data?.current_model_version ?? 'base'}</p>
          <p className="text-sm text-slate-400">Model Version</p>
        </div>
      </div>

      {/* Trend Chart */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="mb-4 flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-sky-400" />
          <h2 className="text-base font-semibold text-white">Correction Rate Trend (12 Weeks)</h2>
        </div>
        <div className="flex h-32 items-end gap-1">
          {trend.length === 0 ? (
            <p className="text-sm text-slate-500">No trend data yet.</p>
          ) : (
            trend.map((t) => (
              <div key={t.week} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-t bg-sky-600 min-h-1 transition-all"
                  style={{ height: `${(t.count / maxTrendCount) * 100}%` }}
                  title={`${t.week}: ${t.count} corrections`}
                />
                <span className="hidden text-xs text-slate-600 xl:block">
                  {t.week.split('-')[1]}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Corrections by Type */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-4 text-base font-semibold text-white">Corrections by Type</h2>
        <div className="space-y-2">
          {Object.entries(data?.total_corrections_by_type ?? {}).map(([type, count]) => {
            const pct = totalCorrections > 0 ? (count / totalCorrections) * 100 : 0
            return (
              <div key={type}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-slate-300">{type.replace('_', ' ')}</span>
                  <span className="text-slate-400">{count}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${CORRECTION_COLORS[type] ?? 'bg-slate-600'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            )
          })}
          {Object.keys(data?.total_corrections_by_type ?? {}).length === 0 && (
            <p className="text-sm text-slate-500">No corrections recorded yet.</p>
          )}
        </div>
      </div>

      {/* False Positive / Negative by Category */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { title: 'False Positives by Category', data: data?.false_positive_rate_by_category ?? {} },
          { title: 'False Negatives by Category', data: data?.false_negative_rate_by_category ?? {} },
        ].map(({ title, data: catData }) => (
          <div key={title} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <h3 className="mb-3 text-sm font-semibold text-white">{title}</h3>
            {Object.keys(catData).length === 0 ? (
              <p className="text-xs text-slate-500">No data.</p>
            ) : (
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-slate-500">
                    <th className="pb-2">Category</th>
                    <th className="pb-2 text-right">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {Object.entries(catData).map(([cat, count]) => (
                    <tr key={cat}>
                      <td className="py-1.5 text-slate-300">{cat}</td>
                      <td className="py-1.5 text-right text-slate-400">{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>

      {/* Fine-tune Status */}
      {(data?.pending_fine_tune_count ?? 0) > 0 && (
        <div className="rounded-xl border border-amber-800 bg-amber-900/10 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-amber-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-amber-300">Fine-tune Pending</p>
            <p className="text-xs text-amber-400/70">
              {data?.pending_fine_tune_count} fine-tune request(s) pending. Once processed, the
              model will improve its extraction accuracy.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export default FeedbackDashboard
