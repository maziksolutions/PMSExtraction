import React, { useState, useCallback, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  FolderOpen,
  Folder,
  ChevronRight,
  ArrowLeft,
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
  id: string
  size: number
  path: string
  modified: string
  selected?: boolean
}

interface SPFolder {
  id: string
  name: string
  child_count?: number
  modified?: string
}

interface BreadcrumbItem {
  id: string
  name: string
  driveId: string
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
  const [folders, setFolders] = useState<SPFolder[]>([])

  // Folder navigation states
  const [currentDriveId, setCurrentDriveId] = useState<string | null>(null)
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null)
  const [currentFolderName, setCurrentFolderName] = useState<string | null>(null)
  const [currentParentId, setCurrentParentId] = useState<string | null>(null)
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([])

  // Selection states (tracked across all navigated folders)
  const [selectedFiles, setSelectedFiles] = useState<Record<string, SPFile>>({})

  // File type filtering: 'all' | 'pdf' | 'word' | 'excel'
  const [fileTypeFilter, setFileTypeFilter] = useState<'all' | 'pdf' | 'word' | 'excel'>('all')

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isSessionRestored, setIsSessionRestored] = useState(false)

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

  // Restore active session on page mount
  React.useEffect(() => {
    if (sessionsData && !isSessionRestored) {
      const activeSession = sessionsData.items?.find(
        (s: any) => s.status === 'active'
      )
      if (activeSession) {
        setActiveSessionId(activeSession.id)
        setStep(3)
      }
      setIsSessionRestored(true)
    }
  }, [sessionsData, isSessionRestored])

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
    mutationFn: (variables: { url: string; drive_id?: string; folder_id?: string }) =>
      apiClient
        .post(
          `/vessels/${vesselId}/ingestion/list-files`,
          {
            folder_url: variables.url,
            drive_id: variables.drive_id,
            folder_id: variables.folder_id,
          },
          { timeout: 120_000 }
        )
        .then((r) => r.data),
    onSuccess: (data) => {
      setFiles(data.files as SPFile[])
      setFolders(data.folders as SPFolder[])
      setCurrentDriveId(data.drive_id)
      setCurrentFolderId(data.folder_id)
      setCurrentParentId(data.parent_id)
      setCurrentFolderName(data.folder_name)

      // Update breadcrumbs history stack
      setBreadcrumbs((prev) => {
        const existingIdx = prev.findIndex((item) => item.id === data.folder_id)
        if (existingIdx !== -1) {
          return prev.slice(0, existingIdx + 1)
        }
        return [
          ...prev,
          {
            id: data.folder_id,
            name: data.folder_name || 'Root',
            driveId: data.drive_id,
          },
        ]
      })

      setStep(2)
    },
  })

  const startIngestionMutation = useMutation({
    mutationFn: () =>
      apiClient
        .post(`/vessels/${vesselId}/ingestion/start`, {
          folder_url: folderUrl,
          selected_files: Object.values(selectedFiles),
        })
        .then((r) => r.data),
    onSuccess: (data: Session) => {
      setActiveSessionId(data.id)
      setStep(3)
      queryClient.invalidateQueries({ queryKey: ['ingestion-sessions', vesselId] })
    },
  })

  const handleNavigateToFolder = useCallback((folderId: string, folderName: string) => {
    listFilesMutation.mutate({
      url: folderUrl,
      drive_id: currentDriveId || undefined,
      folder_id: folderId
    })
  }, [listFilesMutation, folderUrl, currentDriveId])

  const handleBreadcrumbClick = useCallback((index: number) => {
    const target = breadcrumbs[index]
    listFilesMutation.mutate({
      url: folderUrl,
      drive_id: target.driveId,
      folder_id: target.id
    })
  }, [breadcrumbs, listFilesMutation, folderUrl])

  const handleGoBack = useCallback(() => {
    if (breadcrumbs.length > 1) {
      handleBreadcrumbClick(breadcrumbs.length - 2)
    }
  }, [breadcrumbs, handleBreadcrumbClick])

  const toggleFile = useCallback((file: SPFile) => {
    setSelectedFiles((prev) => {
      const next = { ...prev }
      if (next[file.path]) {
        delete next[file.path]
      } else {
        next[file.path] = file
      }
      return next
    })
  }, [])

  const filteredFiles = files.filter((f) => {
    if (fileTypeFilter === 'all') return true
    const ext = f.name.split('.').pop()?.toLowerCase() || ''
    if (fileTypeFilter === 'pdf') return ext === 'pdf'
    if (fileTypeFilter === 'word') return ext === 'docx' || ext === 'doc'
    if (fileTypeFilter === 'excel') return ext === 'xlsx' || ext === 'xls'
    return true
  })

  const toggleAll = useCallback(() => {
    const allFilteredSelected = filteredFiles.every((f) => !!selectedFiles[f.path])
    setSelectedFiles((prev) => {
      const next = { ...prev }
      if (allFilteredSelected) {
        filteredFiles.forEach((f) => delete next[f.path])
      } else {
        filteredFiles.forEach((f) => {
          next[f.path] = f
        })
      }
      return next
    })
  }, [filteredFiles, selectedFiles])

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
                Enter the SharePoint folder or sharing link URL containing the vessel's manuals. 
                Supports both standard folders and folder sharing links.
              </p>
              <div className="flex gap-3">
                <input
                  type="url"
                  value={folderUrl}
                  onChange={(e) => setFolderUrl(e.target.value)}
                  placeholder="https://yourtenant.sharepoint.com/:f:/g/... or /sites/..."
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-white placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
                />
                <button
                  onClick={() => listFilesMutation.mutate({ url: folderUrl })}
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
                  {(listFilesMutation.error as Error)?.message || 'Failed to list folder contents. Check the URL and try again.'}
                </p>
              )}
            </div>
          )}

          {/* Step 2: File tree preview */}
          {step === 2 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
              
              {/* Explorer Header */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-850 pb-4">
                
                {/* Title & Selected Files Count */}
                <div>
                  <h2 className="text-lg font-semibold text-white font-sans">
                    Explore Folders & Files
                  </h2>
                  <p className="text-xs text-sky-400 font-medium mt-0.5">
                    {Object.keys(selectedFiles).length} file(s) selected globally across all folders
                  </p>
                </div>

                {/* Filters & Actions */}
                <div className="flex items-center gap-2 flex-wrap">
                  {/* File Type Filter */}
                  <div className="flex items-center rounded-lg border border-slate-800 bg-slate-950 p-1">
                    <span className="px-2 text-xs text-slate-500 font-medium">Filter Type:</span>
                    {(['all', 'pdf', 'word', 'excel'] as const).map((filter) => (
                      <button
                        key={filter}
                        onClick={() => setFileTypeFilter(filter)}
                        className={`rounded px-2.5 py-1 text-xs font-semibold uppercase tracking-wider transition-colors ${
                          fileTypeFilter === filter
                            ? 'bg-sky-600 text-white'
                            : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {filter === 'all' ? 'All' : filter === 'word' ? 'Word' : filter === 'excel' ? 'Excel' : 'PDF'}
                      </button>
                    ))}
                  </div>

                  <button
                    onClick={toggleAll}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-350 hover:bg-slate-800"
                  >
                    {filteredFiles.length > 0 && filteredFiles.every((f) => !!selectedFiles[f.path]) ? (
                      <CheckSquare className="h-3.5 w-3.5 text-sky-400" />
                    ) : (
                      <Square className="h-3.5 w-3.5" />
                    )}
                    Select All Visible
                  </button>

                  <button
                    onClick={() => {
                      setStep(1)
                      setBreadcrumbs([])
                      setFiles([])
                      setFolders([])
                    }}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-350 hover:bg-slate-800"
                  >
                    Disconnect
                  </button>

                  <button
                    onClick={() => startIngestionMutation.mutate()}
                    disabled={
                      Object.keys(selectedFiles).length === 0 ||
                      startIngestionMutation.isPending
                    }
                    className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
                  >
                    <Play className="h-3.5 w-3.5" />
                    {startIngestionMutation.isPending
                      ? 'Starting...'
                      : `Start Ingestion (${Object.keys(selectedFiles).length})`}
                  </button>
                </div>
              </div>

              {/* Breadcrumb Navigation */}
              <div className="flex items-center gap-1.5 overflow-x-auto rounded-lg bg-slate-950 p-2 text-xs text-slate-450 border border-slate-850">
                {breadcrumbs.length > 1 && (
                  <button
                    onClick={handleGoBack}
                    className="mr-2 flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-slate-300 hover:bg-slate-700 transition-colors"
                  >
                    <ArrowLeft className="h-3 w-3" /> Back
                  </button>
                )}
                {breadcrumbs.map((bc, idx) => (
                  <React.Fragment key={bc.id}>
                    {idx > 0 && <span className="text-slate-600">/</span>}
                    <button
                      onClick={() => handleBreadcrumbClick(idx)}
                      disabled={idx === breadcrumbs.length - 1}
                      className={`hover:underline truncate max-w-[150px] font-medium ${
                        idx === breadcrumbs.length - 1 ? 'text-sky-400 font-semibold cursor-default' : 'text-slate-300'
                      }`}
                    >
                      {bc.name}
                    </button>
                  </React.Fragment>
                ))}
              </div>

              {/* Explorer List */}
              <div className="divide-y divide-slate-850 rounded-lg border border-slate-850 overflow-hidden bg-slate-900/50">
                
                {/* Render Folders first */}
                {folders.map((folder) => (
                  <div
                    key={folder.id}
                    onClick={() => handleNavigateToFolder(folder.id, folder.name)}
                    className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-slate-800/40 group transition-all duration-150"
                  >
                    <Folder className="h-4 w-4 shrink-0 text-amber-500 fill-amber-500/25 group-hover:scale-105 transition-transform" />
                    <span className="flex-1 text-sm font-medium text-slate-200 group-hover:text-white transition-colors truncate">
                      {folder.name}
                    </span>
                    {folder.child_count !== undefined && (
                      <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">
                        {folder.child_count} items
                      </span>
                    )}
                    <ChevronRight className="h-4 w-4 text-slate-650 group-hover:text-slate-400 group-hover:translate-x-0.5 transition-all" />
                  </div>
                ))}

                {/* Render Files */}
                {filteredFiles.map((file) => {
                  const isChecked = !!selectedFiles[file.path]
                  return (
                    <label
                      key={file.path}
                      className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-slate-800/30 transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleFile(file)}
                        className="h-4 w-4 rounded border-slate-600 bg-slate-700 text-sky-500 focus:ring-0 focus:ring-offset-0"
                      />
                      <FileText className={`h-4 w-4 shrink-0 transition-colors ${isChecked ? 'text-sky-400' : 'text-slate-400'}`} />
                      <span className={`flex-1 text-sm truncate transition-colors ${isChecked ? 'text-white font-medium' : 'text-slate-350'}`}>
                        {file.name}
                      </span>
                      <span className="text-xs text-slate-550 w-20 text-right">
                        {formatBytes(file.size)}
                      </span>
                      <span className="text-xs text-slate-650 w-24 text-right hidden sm:inline">
                        {file.modified?.slice(0, 10)}
                      </span>
                    </label>
                  )
                })}

                {/* Empty State */}
                {folders.length === 0 && filteredFiles.length === 0 && (
                  <div className="py-12 text-center text-slate-550">
                    <FolderOpen className="mx-auto mb-2 h-8 w-8 text-slate-650" />
                    <p className="text-sm">No folders or files matching filter in this directory</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Step 3: Progress tracker */}
          {step === 3 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-6">
              
              {/* Tracker Header */}
              <div className="flex items-center justify-between flex-wrap gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    Ingestion Progress
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Monitor downloading and extraction status of SharePoint manuals.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {activeSession && (
                    <span
                      className={`rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wider ${
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
                    className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                  </button>
                  <button
                    onClick={() => {
                      setActiveSessionId(null)
                      setStep(1)
                      setFiles([])
                      setFolders([])
                      setSelectedFiles({})
                      setBreadcrumbs([])
                      setFolderUrl('')
                    }}
                    className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500"
                  >
                    New Ingestion
                  </button>
                </div>
              </div>

              {activeSession && (
                <div className="grid grid-cols-3 gap-4">
                  <div className="rounded-lg bg-slate-850 p-3 text-center border border-slate-800">
                    <p className="text-2xl font-bold text-white">
                      {activeSession.total_files}
                    </p>
                    <p className="text-xs text-slate-400">Total Files</p>
                  </div>
                  <div className="rounded-lg bg-slate-850 p-3 text-center border border-slate-800">
                    <p className="text-2xl font-bold text-green-400">
                      {activeSession.downloaded_files}
                    </p>
                    <p className="text-xs text-slate-400">Completed</p>
                  </div>
                  <div className="rounded-lg bg-slate-850 p-3 text-center border border-slate-800">
                    <p className="text-2xl font-bold text-red-400">
                      {activeSession.failed_files}
                    </p>
                    <p className="text-xs text-slate-400">Failed</p>
                  </div>
                </div>
              )}

              {/* Previous Sessions */}
              <div className="border-t border-slate-850 pt-4">
                <h3 className="mb-3 text-sm font-semibold text-slate-350">
                  Previous Sessions
                </h3>
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {(sessionsData?.items ?? []).map((s: Session) => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setActiveSessionId(s.id)
                        setStep(3)
                        setSessionPolling(true)
                      }}
                      className={`flex w-full items-center justify-between rounded-lg border px-4 py-2 text-sm transition-all duration-150 ${
                        activeSessionId === s.id
                          ? 'border-sky-600 bg-sky-950/20 text-sky-300 shadow-[0_0_12px_rgba(56,189,248,0.1)]'
                          : 'border-slate-800 bg-slate-900/40 text-slate-300 hover:border-slate-700 hover:bg-slate-900/80'
                      }`}
                    >
                      <span className="font-medium">{s.created_at?.slice(0, 10)} at {s.created_at?.slice(11, 16)}</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          statusColors[s.status] ?? ''
                        }`}
                      >
                        {s.status}
                      </span>
                      <span className="text-slate-400">
                        {s.downloaded_files}/{s.total_files} files
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="relative overflow-auto rounded-lg border border-slate-850 max-h-72">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950 text-left text-xs text-slate-500 uppercase font-semibold">
                      <th className="p-3 sticky top-0 bg-slate-950 z-10">File Name</th>
                      <th className="p-3 sticky top-0 bg-slate-950 z-10">Size</th>
                      <th className="p-3 sticky top-0 bg-slate-950 z-10">Status</th>
                      <th className="p-3 sticky top-0 bg-slate-950 z-10">Retries</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850 bg-slate-900/20">
                    {manuals.length === 0 ? (
                      <tr>
                        <td
                          colSpan={4}
                          className="py-12 text-center text-slate-500"
                        >
                          No files tracked yet. Processing will begin shortly.
                        </td>
                      </tr>
                    ) : (
                      manuals.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-900/40 transition-colors">
                          <td className="p-3 text-slate-200 font-medium truncate max-w-xs sm:max-w-md">
                            {m.original_filename}
                          </td>
                          <td className="p-3 text-slate-400">
                            {formatBytes(m.file_size_bytes)}
                          </td>
                          <td className="p-3">
                            <span
                              className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                                statusColors[m.status] ?? 'bg-slate-700 text-slate-300'
                              }`}
                            >
                              {m.status}
                            </span>
                            {m.error_message && (
                              <span className="ml-2 text-xs text-red-400 block sm:inline mt-1 sm:mt-0">
                                {m.error_message}
                              </span>
                            )}
                          </td>
                          <td className="p-3 text-slate-450">{m.retry_count}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Start Screening section */}
              <div className="rounded-xl border border-violet-800 bg-violet-955/5 p-5 space-y-4 shadow-lg shadow-violet-950/5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-violet-300">Auto-Screen Manuals</p>
                    <p className="text-xs text-slate-450 mt-0.5">
                      Classify all queued manuals using AI / keyword analysis
                    </p>
                  </div>
                  <button
                    onClick={startScreening}
                    disabled={screeningState?.status === 'running'}
                    className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-60 transition-colors"
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
                  <div className="space-y-1.5">
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
                  <div className="flex items-center gap-2 text-sm text-green-400 bg-green-950/20 px-3 py-2 rounded-lg w-fit border border-green-900/30">
                    <CheckCircle2 className="h-4 w-4" />
                    Screening complete! Go to <strong className="mx-0.5">Manuals</strong> tab to review results.
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default Ingestion
