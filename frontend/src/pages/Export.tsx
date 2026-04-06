import React, { useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, Upload, CheckCircle, AlertTriangle, FileText } from 'lucide-react'
import apiClient from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { UserRole } from '@/types'

interface ExportVersion {
  id: string
  version_number: number
  status: string
  row_counts: Record<string, number> | null
  created_at: string
  generated_by: string
}

const Export: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()
  const { user } = useAuthStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [downloadError, setDownloadError] = React.useState<string | null>(null)
  const [downloadMessage, setDownloadMessage] = React.useState<string | null>(null)

  const { data: exportsData } = useQuery({
    queryKey: ['exports', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/exports`).then((r) => r.data),
    enabled: !!vesselId,
    refetchInterval: (query) => {
      const items: ExportVersion[] = query.state.data?.items ?? []
      return items.some((item) => item.status === 'generating') ? 3000 : false
    },
  })

  const { data: schemasData } = useQuery({
    queryKey: ['export-schemas'],
    queryFn: () => apiClient.get('/export-schemas').then((r) => r.data),
  })

  const triggerExportMutation = useMutation({
    mutationFn: () => apiClient.post(`/vessels/${vesselId}/exports`).then((r) => r.data),
    onSuccess: async (exportVersion) => {
      queryClient.invalidateQueries({ queryKey: ['exports', vesselId] })
      if (exportVersion?.id && exportVersion?.version_number) {
        try {
          await handleDownload(exportVersion.id, exportVersion.version_number)
        } catch (error) {
          setDownloadError((error as Error).message)
        }
      }
    },
    onError: (error: Error) => setDownloadError(error.message),
  })

  const uploadSchemaMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return apiClient
        .post('/export-schemas', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
        .then((r) => r.data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['export-schemas'] })
    },
  })

  const handleSchemaUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) uploadSchemaMutation.mutate(file)
  }

  const handleDownload = async (exportId: string, version: number) => {
    const res = await apiClient.get(`/vessels/${vesselId}/exports/${exportId}/download`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `vessel_pms_export_v${version}.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    setDownloadError(null)
    setDownloadMessage(`Export v${version} downloaded successfully.`)
  }

  const versions: ExportVersion[] = exportsData?.items ?? []
  const schemas = schemasData?.items ?? []
  const hasSchema = schemas.length > 0
  const isSuperAdmin = user?.role === UserRole.SuperAdmin

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Export</h1>
        <p className="mt-1 text-sm text-slate-400">Generate and download vessel PMS data exports.</p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="mb-4 text-base font-semibold text-white">Pre-Export Checklist</h2>
        <div className="space-y-2.5">
          <div className="flex items-center gap-3">
            <CheckCircle className="h-4 w-4 shrink-0 text-green-400" />
            <span className="text-sm text-slate-300">
              {hasSchema ? 'Custom export template configured' : 'Default export template available'}
            </span>
            {!hasSchema && (
              <span className="text-xs text-slate-500">(optional custom template not uploaded)</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <CheckCircle className="h-4 w-4 shrink-0 text-green-400" />
            <span className="text-sm text-slate-300">At least 1 accepted record of each type</span>
          </div>
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
            <span className="text-sm text-slate-300">Zero pending records required</span>
            {isSuperAdmin && (
              <button className="text-xs text-sky-400 underline hover:text-sky-300">
                Override with Super Admin approval
              </button>
            )}
          </div>
        </div>
      </div>

      {!hasSchema && (
        <div className="rounded-xl border border-amber-800 bg-amber-900/10 p-5">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-400" />
            <h2 className="text-base font-semibold text-amber-300">Optional Custom Export Template</h2>
          </div>
          <p className="mb-4 text-sm text-amber-200/70">
            Exports already work with the built-in format. Upload an Excel template only if you need a company-specific column layout.
          </p>
          <label className="flex w-fit cursor-pointer items-center gap-2 rounded-lg bg-amber-700 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600">
            <Upload className="h-4 w-4" />
            Upload Custom Template
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              onChange={handleSchemaUpload}
            />
          </label>
        </div>
      )}

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">Generate Export</h2>
            <p className="mt-1 text-sm text-slate-400">
              Generates an Excel workbook with Components, Jobs, Spares, and Excluded Records sheets.
            </p>
          </div>
          <button
            onClick={() => triggerExportMutation.mutate()}
            disabled={triggerExportMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <FileText className="h-4 w-4" />
            {triggerExportMutation.isPending ? 'Generating...' : 'Generate Export'}
          </button>
        </div>
        {triggerExportMutation.isError && (
          <div className="mt-3 rounded-lg border border-red-800 bg-red-900/20 p-3 text-sm text-red-300">
            {String((triggerExportMutation.error as any)?.response?.data?.detail ?? 'Export failed')}
          </div>
        )}
        {downloadError ? (
          <div className="mt-3 rounded-lg border border-red-800 bg-red-900/20 p-3 text-sm text-red-300">
            {downloadError}
          </div>
        ) : null}
        {downloadMessage ? (
          <div className="mt-3 rounded-lg border border-green-800 bg-green-900/20 p-3 text-sm text-green-300">
            {downloadMessage}
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-5 py-4">
          <h2 className="text-base font-semibold text-white">Export History</h2>
        </div>
        {versions.length === 0 ? (
          <div className="py-12 text-center text-slate-500">No exports yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left text-xs uppercase text-slate-500">
                <th className="px-5 py-3">Version</th>
                <th className="px-5 py-3">Date</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Components</th>
                <th className="px-5 py-3">Jobs</th>
                <th className="px-5 py-3">Spares</th>
                <th className="px-5 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {versions.map((v) => (
                <tr key={v.id} className="hover:bg-slate-800/50">
                  <td className="px-5 py-3 font-mono text-slate-300">v{v.version_number}</td>
                  <td className="px-5 py-3 text-slate-400">
                    {v.created_at?.slice(0, 16).replace('T', ' ')}
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        v.status === 'ready'
                          ? 'bg-green-700 text-green-100'
                          : v.status === 'generating'
                            ? 'bg-blue-700 text-blue-100'
                            : 'bg-red-700 text-red-100'
                      }`}
                    >
                      {v.status}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-slate-300">{v.row_counts?.components ?? '—'}</td>
                  <td className="px-5 py-3 text-slate-300">{v.row_counts?.jobs ?? '—'}</td>
                  <td className="px-5 py-3 text-slate-300">{v.row_counts?.spares ?? '—'}</td>
                  <td className="px-5 py-3">
                    {v.status === 'ready' && (
                      <button
                        onClick={() => handleDownload(v.id, v.version_number)}
                        className="flex items-center gap-1.5 rounded bg-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-600"
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default Export
