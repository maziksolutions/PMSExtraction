import React, { useState, useCallback, useRef } from 'react'
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
  Upload,
  X,
  CheckCircle2,
  ScanSearch,
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

  const [tab, setTab] = useState<'upload' | 'sharepoint'>('upload')
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [folderUrl, setFolderUrl] = useState('')
  const [files, setFiles] = useState<SPFile[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  // Direct upload state
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [uploadDone, setUploadDone] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Screening state for SharePoint flow
  const [screeningState, setScreeningState] = useState<{total: number; done: number; status: string} | null>(null)
  const screeningIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startScreening = async () => {
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/manuals/screen-all`)
      if (res.data.started) {
        setScreeningState({ total: res.data.total, done: 0, status: 'running' })
        screeningIntervalRef.current = setInterval(async () => {
          try {
            const status = await apiClient.get(`/vessels/${vesselId}/manuals/screening-status`)
            setScreeningState(status.data)
            if (status.data.status === 'completed' || status.data.status === 'failed') {
              if (screeningIntervalRef.current) clearInterval(screeningIntervalRef.current)
            }
          } catch {}
        }, 1500)
      } else {
        setScreeningState({ total: 0, done: 0, status: 'completed' })
      }
    } catch {}
  }

  // List sessions
  const { data: sessionsData } = useQuery({
    queryKey: ['ingestion-sessions', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/ingestion/sessions`).then((r) => r.data),
    enabled: !!vesselId,
  })

  const [sessionPolling, setSessionPolling] = useState(true)

  // Poll active session
  const { data: sessionDetail } = useQuery({
    queryKey: ['session-detail', activeSessionId],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/ingestion/sessions/${activeSessionId}`)
        .then((r) => r.data),
    enabled: !!activeSessionId,
    refetchInterval: sessionPolling ? 3000 : false,
  })

  React.useEffect(() => {
    if (sessionDetail) {
      if (sessionDetail.status === 'completed' || sessionDetail.status === 'failed') {
        setSessionPolling(false)
        queryClient.invalidateQueries({ queryKey: ['ingestion-sessions', vesselId] })
      } else {
        setSessionPolling(true)
      }
    }
  }, [sessionDetail?.status, vesselId, queryClient])

  const listFilesMutation = useMutation({
    mutationFn: (url: string) =>
      apiClient
        .post(`/vessels/${vesselId}/ingestion/list-files`, { folder_url: url }, { timeout: 120_000 })
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

  const uploadMutation = useMutation({
    mutationFn: async (selectedFiles: File[]) => {
      const formData = new FormData()
      selectedFiles.forEach(f => formData.append('files', f))
      const res = await apiClient.post(`/vessels/${vesselId}/ingestion/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 300_000, // 5 minutes for large file uploads
      })
      return res.data
    },
    onSuccess: () => {
      setUploadDone(true)
      setUploadError('')
      queryClient.invalidateQueries({ queryKey: ['ingestion-sessions', vesselId] })
    },
    onError: (err: any) => {
      setUploadError(err?.message ?? 'Upload failed')
    },
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? [])
    setUploadFiles(prev => {
      const names = new Set(prev.map(f => f.name))
      return [...prev, ...selected.filter(f => !names.has(f.name))]
    })
    setUploadDone(false)
  }

  const removeUploadFile = (name: string) => {
    setUploadFiles(prev => prev.filter(f => f.name !== name))
    setUploadDone(false)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Ingestion</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload manuals directly or connect to SharePoint to begin extraction.
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900 p-1 w-fit">
        <button
          onClick={() => setTab('upload')}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${tab === 'upload' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'}`}
        >
          <Upload className="mr-2 inline h-4 w-4" />
          Direct Upload
        </button>
        <button
          onClick={() => setTab('sharepoint')}
          className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${tab === 'sharepoint' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'}`}
        >
          <FolderOpen className="mr-2 inline h-4 w-4" />
          SharePoint
        </button>
      </div>

      {/* Direct Upload Tab */}
      {tab === 'upload' && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-white">Upload PDF Manuals</h2>
            <p className="mt-1 text-sm text-slate-400">
              Upload one or more PDF or modern Office files directly. Supported: .pdf, .docx, .xlsx (max 50 MB each)
            </p>
          </div>

          {/* Drop zone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-700 py-12 transition-colors hover:border-sky-600 hover:bg-slate-800/50"
          >
            <Upload className="mb-3 h-10 w-10 text-slate-500" />
            <p className="text-sm font-medium text-slate-300">Click to select files</p>
            <p className="mt-1 text-xs text-slate-500">PDF, DOCX, XLSX</p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.xlsx"
            className="hidden"
            onChange={handleFileSelect}
          />

          {/* Selected files list */}
          {uploadFiles.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                {uploadFiles.length} file{uploadFiles.length > 1 ? 's' : ''} selected
              </p>
              {uploadFiles.map(f => (
                <div key={f.name} className="flex items-center gap-3 rounded-lg bg-slate-800 px-4 py-2.5">
                  <FileText className="h-4 w-4 shrink-0 text-sky-400" />
                  <span className="flex-1 truncate text-sm text-slate-200">{f.name}</span>
                  <span className="text-xs text-slate-500">{formatBytes(f.size)}</span>
                  <button onClick={() => removeUploadFile(f.name)} className="text-slate-500 hover:text-red-400">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}

              {uploadError && (
                <p className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-400">
                  <AlertCircle className="mr-1 inline h-4 w-4" />{uploadError}
                </p>
              )}

              {uploadDone ? (
                <div className="flex items-center gap-2 rounded-lg bg-green-900/30 px-4 py-3 text-sm text-green-400">
                  <CheckCircle2 className="h-5 w-5" />
                  Files uploaded successfully! Go to <strong className="mx-1">Manuals</strong> to review them.
                </div>
              ) : (
                <button
                  onClick={() => uploadMutation.mutate(uploadFiles)}
                  disabled={uploadMutation.isPending}
                  className="flex w-full items-center justify-center gap-2 rounded-lg bg-sky-600 py-2.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-60"
                >
                  {uploadMutation.isPending ? (
                    <><RefreshCw className="h-4 w-4 animate-spin" /> Uploading...</>
                  ) : (
                    <><Upload className="h-4 w-4" /> Upload {uploadFiles.length} File{uploadFiles.length > 1 ? 's' : ''}</>
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* SharePoint Tab */}
      {tab === 'sharepoint' && (
        <>
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
              {(listFilesMutation.error as Error)?.message || 'Failed to list files. Check the URL and try again.'}
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

          {/* Start Screening section */}
          <div className="mt-4 rounded-xl border border-violet-800 bg-violet-900/20 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-violet-300">Auto-Screen Manuals</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  Classify all queued manuals using AI / keyword analysis
                </p>
              </div>
              <button
                onClick={startScreening}
                disabled={screeningState?.status === 'running'}
                className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60"
              >
                {screeningState?.status === 'running' ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <ScanSearch className="h-4 w-4" />
                )}
                {screeningState?.status === 'running' ? 'Screening...' : 'Start Screening'}
              </button>
            </div>

            {screeningState && screeningState.total > 0 && screeningState.status === 'running' && (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-violet-300">
                  <span>{screeningState.done} / {screeningState.total} manuals screened</span>
                  <span>{Math.round((screeningState.done / screeningState.total) * 100)}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-2 rounded-full bg-violet-500 transition-all duration-500"
                    style={{ width: `${Math.round((screeningState.done / screeningState.total) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {screeningState?.status === 'completed' && (
              <div className="flex items-center gap-2 text-sm text-green-400">
                <CheckCircle2 className="h-4 w-4" />
                Screening complete! Go to <strong className="mx-1">Manuals</strong> tab to review results.
              </div>
            )}
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
        </>
      )}
    </div>
  )
}

export default Ingestion
