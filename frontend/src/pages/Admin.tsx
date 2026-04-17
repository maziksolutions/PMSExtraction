import React from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { CheckCircle, XCircle, AlertTriangle, Trash2, Shield } from 'lucide-react'
import apiClient from '@/api/client'

interface AuditLog {
  id: string
  user_id: string | null
  ip_address: string
  method: string
  path: string
  status_code: number
  duration_ms: number
  created_at: string
}

interface HealthComponent {
  [key: string]: string
}

interface HealthTargets {
  [key: string]: string
}

const Admin: React.FC = () => {
  const { data: healthData, refetch: refetchHealth } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => apiClient.get('/admin/system-health').then((r) => r.data),
    refetchInterval: 30_000,
  })

  const { data: auditData } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => apiClient.get('/admin/audit-logs').then((r) => r.data),
  })

  const components: HealthComponent = healthData?.components ?? {}
  const connectionTargets: HealthTargets = healthData?.connection_targets ?? {}
  const auditLogs: AuditLog[] = auditData?.items ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Shield className="h-6 w-6 text-violet-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">Admin Console</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            System health, audit logs, and data management.
          </p>
        </div>
      </div>

      {/* System Health */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">System Health</h2>
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-sm font-medium ${
                healthData?.status === 'healthy'
                  ? 'bg-green-700 text-green-100'
                  : healthData?.status === 'degraded'
                  ? 'bg-amber-700 text-amber-100'
                  : 'bg-slate-700 text-slate-300'
              }`}
            >
              {healthData?.status ?? 'Unknown'}
            </span>
            <button
              onClick={() => refetchHealth()}
              className="text-xs text-slate-400 underline hover:text-slate-200"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          {Object.entries(components).map(([name, status]) => {
            const isHealthy = status === 'healthy'
            return (
              <div
                key={name}
                className={`flex items-center gap-3 rounded-lg border p-3 ${
                  isHealthy
                    ? 'border-green-800 bg-green-900/10'
                    : 'border-red-800 bg-red-900/10'
                }`}
              >
                {isHealthy ? (
                  <CheckCircle className="h-5 w-5 shrink-0 text-green-400" />
                ) : (
                  <XCircle className="h-5 w-5 shrink-0 text-red-400" />
                )}
                <div>
                  <p className="text-sm font-medium capitalize text-slate-200">
                    {name.replace('_', ' ')}
                  </p>
                  <p
                    className={`text-xs ${isHealthy ? 'text-green-400' : 'text-red-400'}`}
                  >
                    {isHealthy ? 'Healthy' : status}
                  </p>
                  {connectionTargets[name] && (
                    <p className="mt-1 text-[11px] text-slate-500">
                      Target: <span className="font-mono">{connectionTargets[name]}</span>
                    </p>
                  )}
                </div>
              </div>
            )
          })}
          {Object.keys(components).length === 0 && (
            <div className="col-span-3 py-6 text-center text-sm text-slate-500">
              Loading health status...
            </div>
          )}
        </div>
      </div>

      {/* Audit Logs */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-5 py-4">
          <h2 className="text-base font-semibold text-white">Audit Log</h2>
          <p className="text-xs text-slate-400">All state-changing operations recorded for compliance.</p>
        </div>

        {auditLogs.length === 0 ? (
          <div className="py-12 text-center text-slate-500">No audit log entries.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs text-slate-500 uppercase">
                  <th className="px-5 py-3">Timestamp</th>
                  <th className="px-5 py-3">Method</th>
                  <th className="px-5 py-3">Path</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Duration</th>
                  <th className="px-5 py-3">IP</th>
                  <th className="px-5 py-3">User</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {auditLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-800/50">
                    <td className="px-5 py-2.5 font-mono text-xs text-slate-400">
                      {log.created_at?.slice(0, 19).replace('T', ' ')}
                    </td>
                    <td className="px-5 py-2.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                          log.method === 'DELETE'
                            ? 'bg-red-900 text-red-200'
                            : log.method === 'POST'
                            ? 'bg-green-900 text-green-200'
                            : log.method === 'PATCH' || log.method === 'PUT'
                            ? 'bg-amber-900 text-amber-200'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {log.method}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 font-mono text-xs text-slate-300 max-w-xs truncate">
                      {log.path}
                    </td>
                    <td className="px-5 py-2.5">
                      <span
                        className={`text-xs font-medium ${
                          log.status_code < 300
                            ? 'text-green-400'
                            : log.status_code < 400
                            ? 'text-amber-400'
                            : 'text-red-400'
                        }`}
                      >
                        {log.status_code}
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-slate-400 text-xs">{log.duration_ms}ms</td>
                    <td className="px-5 py-2.5 font-mono text-xs text-slate-500">{log.ip_address}</td>
                    <td className="px-5 py-2.5 font-mono text-xs text-slate-500">
                      {log.user_id?.slice(0, 8) ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Data Deletion Panel */}
      <div className="rounded-xl border border-red-900 bg-red-950/20 p-5">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="h-5 w-5 text-red-400" />
          <h2 className="text-base font-semibold text-red-300">Data Deletion Policy</h2>
        </div>
        <p className="text-sm text-red-200/70 mb-4">
          Vessel data is automatically deleted 90 days after the final export. You can manually trigger deletion for a specific vessel.
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Vessel ID (UUID)"
            className="flex-1 rounded-lg border border-red-900 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:border-red-700 focus:outline-none"
            id="deletion-vessel-id"
          />
          <button
            onClick={() => {
              const id = (document.getElementById('deletion-vessel-id') as HTMLInputElement)?.value
              if (id && confirm(`Confirm data deletion schedule for vessel ${id}?`)) {
                apiClient.post(`/admin/data-deletion/${id}`)
              }
            }}
            className="flex items-center gap-2 rounded-lg border border-red-800 bg-red-900/30 px-4 py-2 text-sm text-red-300 hover:bg-red-900/50"
          >
            <Trash2 className="h-4 w-4" />
            Schedule Deletion
          </button>
        </div>
      </div>
    </div>
  )
}

export default Admin
