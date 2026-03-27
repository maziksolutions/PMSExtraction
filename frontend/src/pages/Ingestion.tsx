import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen,
  Play,
  RefreshCw,
  CheckSquare,
  Square,
  AlertCircle,
  FileText,
} from 'lucide-react'
import apiClient from '@/api/client'

interface SPFile {
  name: string
  size: number
  path: string
  modified: string
  selected?: boolean
}

interface ManualStatus {
  id: string
  original_filename: string
  file_size_bytes: number
  status: string
  error_message?: string
  retry_count: number
}

interface Session {
  id: string
  status: string
  total_files: number
  downloaded_files: number
  failed_files: number
  created_at: string
  manuals?: ManualStatus[]
}

const statusColors: Record<string, string> = {
  queued: 'bg-slate-600 text-slate-200',
  downloading: 'bg-blue-600 text-blue-100',
  converting: 'bg-yellow-600 text-yellow-100',
  translating: 'bg-purple-600 text-purple-100',
  scanning: 'bg-orange-600 text-orange-100',
  classified: 'bg-green-600 text-green-100',
  failed: 'bg-red-600 text-red-100',
  active: 'bg-blue-600 text-blue-100',
  completed: 'bg-green-600 text-green-100',
  cancelled: 'bg-slate-600 text-slate-200',
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const Ingestion: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [folderUrl, setFolderUrl] = useState('')
  const [files, setFiles] = useState<SPFile[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  // List sessions
  const { data: sessionsData } = useQuery({
    queryKey: ['ingestion-sessions', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/ingestion/sessions`).then((r) => r.data),
    enabled: !!vesselId,
  })

  // Poll active session
  const { data: sessionDetail } = useQuery({
    queryKey: ['session-detail', activeSessionId],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/ingestion/sessions/${activeSessionId}`)
        .then((r) => r.data),
    enabled: !!activeSessionId,
    refetchInterval: 3000,
  })

  const listFilesMutation = useMutation({
    mutationFn: (url: string) =>
      apiClient
        .post(`/vessels/${vesselId}/ingestion/list-files`, { folder_url: url })
        .then((r) => r.data),
    onSuccess: (data) => {
      setFiles(
        (data.files as SPFile[]).map((f) => ({ ...f, selected: true }))
      )
      setStep(2)
    },
  })

  const startIngestionMutation = useMutation({
    mutationFn: () =>
      apiClient
        .post(`/vessels/${vesselId}/ingestion/start`, {
          folder_url: folderUrl,
          selected_files: files.filter((f) => f.selected),
        })
        .then((r) => r.data),
    onSuccess: (data: Session) => {
      setActiveSessionId(data.id)
      setStep(3)
      queryClient.invalidateQueries({ queryKey: ['ingestion-sessions', vesselId] })
    },
  })

  const toggleFile = useCallback((path: string) => {
    setFiles((prev) =>
      prev.map((f) => (f.path === path ? { ...f, selected: !f.selected } : f))
    )
  }, [])

  const toggleAll = useCallback(() => {
    const allSelected = files.every((f) => f.selected)
    setFiles((prev) => prev.map((f) => ({ ...f, selected: !allSelected })))
  }, [files])

  const activeSession: Session | null = sessionDetail ?? null
  const manuals: ManualStatus[] = activeSession?.manuals ?? []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Ingestion</h1>
        <p className="mt-1 text-sm text-slate-400">
          Connect to SharePoint, select files, and track ingestion progress.
        </p>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {[
          { n: 1, label: 'Connect SharePoint' },
          { n: 2, label: 'Select Files' },
          { n: 3, label: 'Track Progress' },
        ].map(({ n, label }, i) => (
          <React.Fragment key={n}>
            {i > 0 && <div className="h-px flex-1 bg-slate-700" />}
            <div
              className={`flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium ${
                step === n
                  ? 'bg-sky-600 text-white'
                  : step > n
                  ? 'bg-green-700 text-green-100'
                  : 'bg-slate-800 text-slate-400'
              }`}
            >
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/20 text-xs font-bold">
                {n}
              </span>
              {label}
            </div>
          </React.Fragment>
        ))}
      </div>

      {/* Step 1: Connect SharePoint */}
      {step === 1 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">
            Connect to SharePoint
          </h2>
          <p className="mb-4 text-sm text-slate-400">
            Enter the SharePoint folder URL containing the vessel's manuals. You
            may be redirected to authenticate with Microsoft.
          </p>
          <div className="flex gap-3">
            <input
              type="url"
              value={folderUrl}
              onChange={(e) => setFolderUrl(e.target.value)}
              placeholder="https://yourtenant.sharepoint.com/sites/..."
              className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
            />
            <button
              onClick={() => listFilesMutation.mutate(folderUrl)}
              disabled={!folderUrl || listFilesMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              <FolderOpen className="h-4 w-4" />
              {listFilesMutation.isPending ? 'Connecting...' : 'Connect'}
            </button>
          </div>
          {listFilesMutation.isError && (
            <p className="mt-3 text-sm text-red-400">
              <AlertCircle className="inline h-4 w-4 mr-1" />
              Failed to list files. Check the URL and try again.
            </p>
          )}
        </div>
      )}

      {/* Step 2: File tree preview */}
      {step === 2 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              Select Files ({files.filter((f) => f.selected).length}/{files.length})
            </h2>
            <div className="flex gap-2">
              <button
                onClick={toggleAll}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                {files.every((f) => f.selected) ? (
                  <CheckSquare className="h-3.5 w-3.5" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}
                Toggle All
              </button>
              <button
                onClick={() => setStep(1)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                Back
              </button>
              <button
                onClick={() => startIngestionMutation.mutate()}
                disabled={
                  !files.some((f) => f.selected) ||
                  startIngestionMutation.isPending
                }
                className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" />
                {startIngestionMutation.isPending
                  ? 'Starting...'
                  : 'Start Ingestion'}
              </button>
            </div>
          </div>

          <div className="divide-y divide-slate-800">
            {files.map((file) => (
              <label
                key={file.path}
                className="flex cursor-pointer items-center gap-4 py-3 hover:bg-slate-800/50"
              >
                <input
                  type="checkbox"
                  checked={file.selected ?? true}
                  onChange={() => toggleFile(file.path)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-sky-500"
                />
                <FileText className="h-4 w-4 shrink-0 text-slate-400" />
                <span className="flex-1 text-sm text-slate-200">{file.name}</span>
                <span className="text-xs text-slate-500">
                  {formatBytes(file.size)}
                </span>
                <span className="text-xs text-slate-600">{file.modified?.slice(0, 10)}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Step 3: Progress tracker */}
      {step === 3 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              Ingestion Progress
            </h2>
            <div className="flex items-center gap-3">
              {activeSession && (
                <span
                  className={`rounded-full px-3 py-0.5 text-xs font-medium ${
                    statusColors[activeSession.status] ?? 'bg-slate-700 text-slate-300'
                  }`}
                >
                  {activeSession.status}
                </span>
              )}
              <button
                onClick={() =>
                  queryClient.invalidateQueries({
                    queryKey: ['session-detail', activeSessionId],
                  })
                }
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                <RefreshCw className="h-3 w-3" />
                Refresh
              </button>
            </div>
          </div>

          {activeSession && (
            <div className="mb-4 grid grid-cols-3 gap-4">
              <div className="rounded-lg bg-slate-800 p-3 text-center">
                <p className="text-2xl font-bold text-white">
                  {activeSession.total_files}
                </p>
                <p className="text-xs text-slate-400">Total Files</p>
              </div>
              <div className="rounded-lg bg-slate-800 p-3 text-center">
                <p className="text-2xl font-bold text-green-400">
                  {activeSession.downloaded_files}
                </p>
                <p className="text-xs text-slate-400">Completed</p>
              </div>
              <div className="rounded-lg bg-slate-800 p-3 text-center">
                <p className="text-2xl font-bold text-red-400">
                  {activeSession.failed_files}
                </p>
                <p className="text-xs text-slate-400">Failed</p>
              </div>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
                  <th className="pb-2 pr-4">File Name</th>
                  <th className="pb-2 pr-4">Size</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2">Retries</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {manuals.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="py-6 text-center text-slate-500"
                    >
                      No files tracked yet. Processing will begin shortly.
                    </td>
                  </tr>
                ) : (
                  manuals.map((m) => (
                    <tr key={m.id}>
                      <td className="py-2.5 pr-4 text-slate-200">
                        {m.original_filename}
                      </td>
                      <td className="py-2.5 pr-4 text-slate-400">
                        {formatBytes(m.file_size_bytes)}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            statusColors[m.status] ?? 'bg-slate-700 text-slate-300'
                          }`}
                        >
                          {m.status}
                        </span>
                        {m.error_message && (
                          <span className="ml-2 text-xs text-red-400">
                            {m.error_message}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 text-slate-400">{m.retry_count}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 border-t border-slate-800 pt-4">
            <h3 className="mb-2 text-sm font-semibold text-slate-300">
              Previous Sessions
            </h3>
            <div className="space-y-2">
              {(sessionsData?.items ?? []).map((s: Session) => (
                <button
                  key={s.id}
                  onClick={() => setActiveSessionId(s.id)}
                  className={`flex w-full items-center justify-between rounded-lg border px-4 py-2 text-sm transition-colors ${
                    activeSessionId === s.id
                      ? 'border-sky-600 bg-sky-900/20 text-sky-300'
                      : 'border-slate-700 bg-slate-800 text-slate-300 hover:border-slate-600'
                  }`}
                >
                  <span>{s.created_at?.slice(0, 10)}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      statusColors[s.status] ?? ''
                    }`}
                  >
                    {s.status}
                  </span>
                  <span>
                    {s.downloaded_files}/{s.total_files} files
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Ingestion
