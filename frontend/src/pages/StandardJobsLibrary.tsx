import React, { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen,
  Upload,
  RefreshCw,
  CheckCircle,
  XCircle,
  Trash2,
  ChevronDown,
  ChevronRight,
  Plus,
} from 'lucide-react'
import apiClient from '@/api/client'

// ─── Types ───────────────────────────────────────────────────────────────────

interface StandardJob {
  id: string
  class_society: string
  job_type?: string
  machinery_type: string
  job_name: string
  job_description: string | null
  performing_rank?: string | null
  verifying_rank?: string | null
  frequency: number | null
  frequency_type: string | null
  is_critical: boolean
  library_reference: string | null
}

interface StandardJobFormState {
  class_society: string
  machinery_type: string
  job_name: string
  job_description: string
  performing_rank: string
  verifying_rank: string
  frequency: string
  frequency_type: string
  is_critical: boolean
  library_reference: string
}

type TabType = 'standard' | 'class' | 'critical'

const CLASS_SOCIETIES = ['DNV GL', "Lloyd's Register", 'Bureau Veritas', 'ABS', 'ClassNK']
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
const LIBRARY_SORT_OPTIONS = [
  { value: 'job_name', label: 'Job Name' },
  { value: 'machinery_type', label: 'Machinery' },
  { value: 'performing_rank', label: 'Rank' },
  { value: 'class_society', label: 'Class Society' },
  { value: 'frequency', label: 'Frequency' },
  { value: 'reference', label: 'Reference' },
]

// ─── Import Panel ─────────────────────────────────────────────────────────────

const ImportPanel: React.FC<{ jobType: TabType; onImported: () => void }> = ({ jobType, onImported }) => {
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<{ parsed_rows?: number; imported: number; updated: number; unchanged: number; skipped: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      const importType = jobType === 'critical' ? 'critical' : jobType
      const res = await apiClient.post(
        `/standard-jobs/bulk-import?job_type=${importType}`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      return res.data as { parsed_rows?: number; imported: number; updated: number; unchanged: number; skipped: number }
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      onImported()
      if (fileRef.current) fileRef.current.value = ''
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail || 'Import failed. Check the file format and try again.')
      setResult(null)
    },
  })

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setResult(null)
    setError(null)
    importMutation.mutate(file)
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">
        Import {jobType === 'standard' ? 'Standard Jobs' : jobType === 'class' ? 'Class Society Jobs' : 'Critical Jobs'} from Excel / CSV
      </h3>

      <div className="text-xs text-slate-500 mb-4 space-y-1">
        {jobType !== 'class' ? (
          <>
            <p>Supported workbook sheets: <span className="text-slate-400">Audit standard jobs, Annex Job Title, Critical Jobs</span></p>
            <p>The importer auto-detects job title, description, criticality, frequency, and reference fields from the workbook. `Annex 1 PMS_Jobs` is not required.</p>
            <p>The same workbook can be used in both tabs: the Standard Jobs tab imports non-critical rows, and the Critical Jobs tab imports only rows marked critical.</p>
            {jobType === 'standard' && (
              <p>Critical jobs are stored in the Critical Jobs library and are added later from Jobs Review instead of comparison.</p>
            )}
            {jobType === 'critical' && (
              <p>This imports only the critical jobs sheet into the Critical Jobs library.</p>
            )}
          </>
        ) : (
          <>
            <p>Required columns: <span className="text-slate-400">job_name, machinery_type</span></p>
            <p>Optional columns: <span className="text-slate-400">job_description, class_society, frequency, frequency_type, is_critical, library_reference</span></p>
          </>
        )}
        {jobType === 'class' && (
          <p>class_society values: <span className="text-slate-400">DNV GL, Lloyd's Register, Bureau Veritas, ABS, ClassNK</span></p>
        )}
        <p>frequency_type values: <span className="text-slate-400">daily, weekly, monthly, yearly, hourly</span></p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={importMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {importMutation.isPending ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Upload className="w-4 h-4" />
          )}
          {importMutation.isPending ? 'Importing...' : 'Choose File to Import'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          onChange={handleFile}
          className="hidden"
        />

        {result && (
          <div className="flex items-center gap-3 text-sm">
            {typeof result.parsed_rows === 'number' && (
              <span className="text-slate-400">
                <strong>{result.parsed_rows}</strong> parsed
              </span>
            )}
            <span className="flex items-center gap-1.5 text-emerald-400">
              <CheckCircle className="w-4 h-4" />
              <strong>{result.imported}</strong> imported
            </span>
            {result.updated > 0 && (
              <span className="text-sky-400">
                <strong>{result.updated}</strong> updated
              </span>
            )}
            {result.unchanged > 0 && (
              <span className="text-amber-300">
                <strong>{result.unchanged}</strong> unchanged
              </span>
            )}
            {result.skipped > 0 && (
              <span className="text-slate-400">
                <strong>{result.skipped}</strong> skipped
              </span>
            )}
          </div>
        )}
        {error && (
          <span className="flex items-center gap-1.5 text-red-400 text-sm">
            <XCircle className="w-4 h-4" />
            {error}
          </span>
        )}
      </div>
    </div>
  )
}

// ─── Jobs Table ───────────────────────────────────────────────────────────────

const JobsTable: React.FC<{ jobType: TabType }> = ({ jobType }) => {
  const queryClient = useQueryClient()
  const [filterSociety, setFilterSociety] = useState('')
  const [filterMachinery, setFilterMachinery] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('job_name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['standard-jobs-library', jobType, filterSociety, filterMachinery, search, sortBy, sortOrder, page, pageSize],
    queryFn: async () => {
      const params: Record<string, string> = {}
      params.job_type = jobType
      params.page = String(page)
      params.page_size = String(pageSize)
      params.sort_by = sortBy
      params.sort_order = sortOrder
      if (jobType === 'class' && filterSociety) params.class_society = filterSociety
      if (filterMachinery) params.machinery_type = filterMachinery
      if (search) params.search = search
      const res = await apiClient.get('/standard-jobs', { params })
      return res.data as { items: StandardJob[]; total: number; total_pages: number; page: number; page_size: number }
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/standard-jobs/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['standard-jobs-library'] }),
  })

  const jobs: StandardJob[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1
  const pageJobs = jobs

  React.useEffect(() => {
    setPage(1)
  }, [jobType, filterSociety, filterMachinery, search, sortBy, sortOrder, pageSize])

  React.useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        {jobType === 'class' && (
          <select
            value={filterSociety}
            onChange={(e) => { setFilterSociety(e.target.value); setPage(1) }}
            className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-sky-500"
          >
            <option value="">All Class Societies</option>
            {CLASS_SOCIETIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <input
          type="text"
          value={filterMachinery}
          onChange={(e) => { setFilterMachinery(e.target.value); setPage(1) }}
          placeholder="Filter by machinery type..."
          className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-sky-500 w-56"
        />
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder="Search jobs..."
          className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-sky-500 w-56"
        />
        <select
          value={sortBy}
          onChange={(e) => { setSortBy(e.target.value); setPage(1) }}
          className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          {LIBRARY_SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={sortOrder}
          onChange={(e) => { setSortOrder(e.target.value as 'asc' | 'desc'); setPage(1) }}
          className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-sky-500"
        >
          <option value="asc">Sort A-Z / Low-High</option>
          <option value="desc">Sort Z-A / High-Low</option>
        </select>
        {(filterSociety || filterMachinery) && (
          <button
            onClick={() => { setFilterSociety(''); setFilterMachinery(''); setSearch(''); setSortBy('job_name'); setSortOrder('asc') }}
            className="text-xs text-slate-400 underline hover:text-slate-200"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="py-12 text-center text-slate-500">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
          Loading...
        </div>
      ) : isError ? (
        <div className="bg-slate-800 border border-red-800 rounded-xl p-12 text-center">
          <XCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-300 font-medium">Unable to load {jobType === 'standard' ? 'standard' : jobType === 'class' ? 'class society' : 'critical'} jobs</p>
          <p className="text-slate-400 text-sm mt-1">{error instanceof Error ? error.message : 'Unknown error'}</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <BookOpen className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400 font-medium">No {jobType === 'standard' ? 'standard' : jobType === 'class' ? 'class society' : 'critical'} jobs imported yet</p>
          <p className="text-slate-500 text-sm mt-1">Use the import panel above to load jobs from Excel or CSV.</p>
        </div>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-300">
              {jobType === 'standard' ? 'Standard Jobs' : jobType === 'class' ? 'Class Society Jobs' : 'Critical Jobs'} Library
            </span>
            <span className="text-xs text-slate-500">{total} jobs</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-900/50 text-xs text-slate-400 uppercase">
                  <th className="w-8 px-4 py-3" />
                  <th className="text-left px-4 py-3 font-medium">Job Name</th>
                  <th className="text-left px-4 py-3 font-medium">Machinery</th>
                  <th className="text-left px-4 py-3 font-medium">Rank</th>
                  {jobType === 'class' && <th className="text-left px-4 py-3 font-medium">Class Society</th>}
                  <th className="text-left px-4 py-3 font-medium">Frequency</th>
                  <th className="text-left px-4 py-3 font-medium">Critical</th>
                  <th className="text-left px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {pageJobs.map((job) => (
                  <React.Fragment key={job.id}>
                    <tr className="hover:bg-slate-700/20 transition-colors">
                      <td className="px-4 py-3">
                        <button
                          onClick={() => setExpandedId(expandedId === job.id ? null : job.id)}
                          className="text-slate-500 hover:text-slate-300"
                        >
                          {expandedId === job.id
                            ? <ChevronDown className="w-4 h-4" />
                            : <ChevronRight className="w-4 h-4" />
                          }
                        </button>
                      </td>
                      <td className="px-4 py-3 text-slate-200 font-medium max-w-xs">
                        <span className={`mr-2 inline-block w-1.5 h-1.5 rounded-full ${job.is_critical ? 'bg-red-400' : 'bg-slate-600'}`} />
                        {job.job_name}
                      </td>
                      <td className="px-4 py-3 text-slate-400">{job.machinery_type}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {[job.performing_rank, job.verifying_rank].filter(Boolean).join(' / ') || '-'}
                      </td>
                      {jobType === 'class' && (
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded-full text-xs bg-sky-900/50 text-sky-400 border border-sky-700/40">
                            {job.class_society}
                          </span>
                        </td>
                      )}
                      <td className="px-4 py-3 text-slate-400 text-xs">
                        {job.frequency ? `${job.frequency} ${job.frequency_type ?? ''}`.trim() : '-'}
                      </td>
                      <td className="px-4 py-3">
                        {job.is_critical
                          ? <span className="text-red-400 text-xs font-medium">Critical</span>
                          : <span className="text-slate-600 text-xs">-</span>
                        }
                      </td>
                      <td className="px-4 py-3 text-slate-500 text-xs">{job.library_reference ?? '-'}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            if (window.confirm(`Delete "${job.job_name}"?`)) deleteMutation.mutate(job.id)
                          }}
                          className="text-slate-600 hover:text-red-400 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                    {expandedId === job.id && job.job_description && (
                      <tr className="bg-slate-900/40">
                        <td colSpan={jobType === 'class' ? 8 : 7} className="px-8 py-3 text-xs text-slate-400">
                          {job.job_description}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-700 px-4 py-2.5 shrink-0">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span>{total} total</span>
              <span>·</span>
              <span>Show</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
                className="bg-slate-700 border border-slate-600 rounded px-2 py-0.5 text-white text-xs"
              >
                {PAGE_SIZE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <span>per page</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40"
              >
                {'<'} Prev
              </button>
              <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40"
              >
                Next {'>'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const StandardJobsLibrary: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('standard')
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const [form, setForm] = useState<StandardJobFormState>({
    class_society: 'General',
    machinery_type: '',
    job_name: '',
    job_description: '',
    performing_rank: '',
    verifying_rank: '',
    frequency: '',
    frequency_type: '',
    is_critical: false,
    library_reference: '',
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        frequency: form.frequency ? Number(form.frequency) : null,
      }
      const res = await apiClient.post('/standard-jobs', payload)
      return res.data
    },
    onSuccess: () => {
      setShowAddDialog(false)
      setAddError(null)
      setForm({
        class_society: activeTab === 'class' ? 'DNV GL' : 'General',
        machinery_type: '',
        job_name: '',
        job_description: '',
        performing_rank: '',
        verifying_rank: '',
        frequency: '',
        frequency_type: '',
        is_critical: activeTab === 'critical',
        library_reference: '',
      })
      refresh()
    },
    onError: (err: any) => {
      setAddError(err?.response?.data?.detail || 'Unable to add job')
    },
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['standard-jobs-library'] })
    queryClient.invalidateQueries({ queryKey: ['standard-jobs'] })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <BookOpen className="w-7 h-7 text-sky-400" />
          Standard Jobs Library
        </h1>
        <p className="text-slate-400 mt-1">
          {activeTab === 'standard'
            ? 'Global maintenance job standards - imported once, applied to all vessels'
            : activeTab === 'class'
              ? "Classification society job requirements - DNV GL, Lloyd's Register, Bureau Veritas, ABS, ClassNK"
              : 'Critical maintenance jobs library - added to vessels after Jobs QC.'}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700">
        {([
          { value: 'standard', label: 'Standard Jobs' },
          { value: 'class', label: 'Class Society Jobs' },
          { value: 'critical', label: 'Critical Jobs' },
        ] as { value: TabType; label: string }[]).map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setActiveTab(value)}
            className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === value
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-white hover:border-slate-500'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex justify-end">
        <button
          onClick={() => {
            setAddError(null)
            setForm((prev) => ({
              ...prev,
              class_society: activeTab === 'class' ? (prev.class_society === 'General' ? 'DNV GL' : prev.class_society) : 'General',
              is_critical: activeTab === 'critical',
            }))
            setShowAddDialog(true)
          }}
          className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
        >
          <Plus className="h-4 w-4" />
          Add Job
        </button>
      </div>

      {/* Import Panel */}
      <ImportPanel key={activeTab} jobType={activeTab} onImported={refresh} />

      {/* Jobs Table */}
      <JobsTable key={`table-${activeTab}`} jobType={activeTab} />

      {showAddDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-2xl rounded-xl border border-slate-700 bg-slate-900 p-6">
            <h2 className="text-lg font-semibold text-white">Add Library Job</h2>
            <p className="mt-1 text-sm text-slate-400">
              Create a reusable {activeTab === 'standard' ? 'company SMS' : activeTab === 'class' ? 'CMS / class' : 'critical'} standard job.
            </p>
            <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Class Society</span>
                <select
                  value={form.class_society}
                  onChange={(e) => setForm((prev) => ({ ...prev, class_society: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                  disabled={activeTab !== 'class'}
                >
                  {activeTab !== 'class' ? (
                    <option value="General">General</option>
                  ) : (
                    CLASS_SOCIETIES.map((society) => <option key={society} value={society}>{society}</option>)
                  )}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Machinery Type</span>
                <input
                  value={form.machinery_type}
                  onChange={(e) => setForm((prev) => ({ ...prev, machinery_type: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-slate-400">Job Name</span>
                <input
                  value={form.job_name}
                  onChange={(e) => setForm((prev) => ({ ...prev, job_name: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-slate-400">Job Description</span>
                <textarea
                  rows={4}
                  value={form.job_description}
                  onChange={(e) => setForm((prev) => ({ ...prev, job_description: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Performing Rank</span>
                <input
                  value={form.performing_rank}
                  onChange={(e) => setForm((prev) => ({ ...prev, performing_rank: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Verifying Rank</span>
                <input
                  value={form.verifying_rank}
                  onChange={(e) => setForm((prev) => ({ ...prev, verifying_rank: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Frequency</span>
                <input
                  value={form.frequency}
                  onChange={(e) => setForm((prev) => ({ ...prev, frequency: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Frequency Type</span>
                <select
                  value={form.frequency_type}
                  onChange={(e) => setForm((prev) => ({ ...prev, frequency_type: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                >
                  <option value="">None</option>
                  <option value="daily">daily</option>
                  <option value="weekly">weekly</option>
                  <option value="monthly">monthly</option>
                  <option value="yearly">yearly</option>
                  <option value="hourly">hourly</option>
                </select>
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-slate-400">Library Reference</span>
                <input
                  value={form.library_reference}
                  onChange={(e) => setForm((prev) => ({ ...prev, library_reference: e.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200"
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={form.is_critical}
                  onChange={(e) => setForm((prev) => ({ ...prev, is_critical: e.target.checked }))}
                  disabled={activeTab === 'critical'}
                />
                Critical Job
              </label>
            </div>
            {addError && <p className="mt-4 text-sm text-red-400">{addError}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setShowAddDialog(false)}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {createMutation.isPending ? 'Saving...' : 'Add Job'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StandardJobsLibrary
