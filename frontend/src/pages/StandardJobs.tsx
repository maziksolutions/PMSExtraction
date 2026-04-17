import React, { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Download, Play, XCircle } from 'lucide-react'
import apiClient from '@/api/client'

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

interface Match {
  id: string
  standard_job_id: string
  matched_job_id: string | null
  match_status: string
  match_score: number | null
  not_applicable_reason: string | null
  matched_job_name?: string | null
  matched_job_code?: string | null
  matched_job_description?: string | null
  matched_job_qc_status?: string | null
  matched_job_origin?: 'manual' | 'review' | null
  jobs_review_job_id?: string | null
  jobs_review_job_name?: string | null
  jobs_review_job_qc_status?: string | null
}

interface ComparisonSummary {
  library_total: number
  added_to_review_total: number
  not_applicable_total: number
  manual_linked_total: number
}

interface ComponentOption {
  id: string
  component_name: string
  group1: string
  main_machinery: string
}

const MATCH_COLORS: Record<string, string> = {
  matched: 'bg-green-700 text-green-100',
  partial: 'bg-amber-700 text-amber-100',
  not_found: 'bg-red-700 text-red-100',
  not_applicable: 'bg-slate-600 text-slate-300',
}

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
const SORT_OPTIONS = [
  { value: 'job_name', label: 'Job Name' },
  { value: 'machinery_type', label: 'Machinery Type' },
  { value: 'class_society', label: 'Class Society' },
  { value: 'frequency', label: 'Frequency' },
  { value: 'reference', label: 'Reference' },
]
const CLASS_SOCIETY_OPTIONS = [
  { value: 'DNV GL', label: 'DNV' },
  { value: "Lloyd's Register", label: 'LR' },
  { value: 'Bureau Veritas', label: 'BV' },
  { value: 'ABS', label: 'ABS' },
  { value: 'ClassNK', label: 'NK' },
  { value: 'KR', label: 'KR' },
  { value: 'IRS', label: 'IRS' },
]

function displayClassSociety(value: string | null | undefined): string {
  const matched = CLASS_SOCIETY_OPTIONS.find((option) => option.value === value)
  return matched?.label ?? value ?? '-'
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  const maybeError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = maybeError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return maybeError?.message ?? fallback
}

function normalize(value: string | null | undefined): string {
  return (value ?? '').toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim()
}

function renderProcedurePreview(value: string | null | undefined): React.ReactNode {
  if (!value?.trim()) {
    return <span className="text-xs text-slate-500">No procedure</span>
  }

  return (
    <div
      title={value}
      className="max-w-[320px] whitespace-pre-wrap break-words text-xs leading-5 text-slate-300 line-clamp-4"
    >
      {value}
    </div>
  )
}

function suggestComponentId(job: StandardJob, components: ComponentOption[]): string {
  const machinery = normalize(job.machinery_type)
  const jobName = normalize(job.job_name)
  let bestId = ''
  let bestScore = 0

  for (const component of components) {
    const componentName = normalize(component.component_name)
    const mainMachinery = normalize(component.main_machinery)
    let score = 0
    if (machinery && mainMachinery === machinery) score += 100
    if (machinery && componentName === machinery) score += 90
    if (machinery && mainMachinery.includes(machinery)) score += 55
    if (machinery && machinery.includes(mainMachinery)) score += 45
    if (jobName && componentName && jobName.includes(componentName)) score += 30
    if (jobName && mainMachinery && jobName.includes(mainMachinery)) score += 20
    if (score > bestScore) {
      bestScore = score
      bestId = component.id
    }
  }

  return bestScore >= 45 ? bestId : ''
}

const StandardJobs: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [filterSociety, setFilterSociety] = useState('')
  const [filterMachinery, setFilterMachinery] = useState('')
  const [filterMatchStatus, setFilterMatchStatus] = useState('')
  const [naReason, setNaReason] = useState('')
  const [naMatchId, setNaMatchId] = useState<string | null>(null)
  const [showNaDialog, setShowNaDialog] = useState(false)
  const [libraryType, setLibraryType] = useState<'standard' | 'class'>('standard')
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([])
  const [componentSelections, setComponentSelections] = useState<Record<string, string>>({})
  const [batchComponentId, setBatchComponentId] = useState('')
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('job_name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [naMatchIds, setNaMatchIds] = useState<string[]>([])

  const standardJobsQuery = useQuery({
    queryKey: ['standard-jobs-comparison', libraryType, filterSociety, filterMachinery, search, sortBy, sortOrder, page, pageSize],
    queryFn: () => {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
        is_critical: 'false',
        job_type: libraryType,
        sort_by: sortBy,
        sort_order: sortOrder,
      }
      if (libraryType === 'class' && filterSociety) params.class_society = filterSociety
      if (filterMachinery) params.machinery_type = filterMachinery
      if (search) params.search = search
      return apiClient.get('/standard-jobs', { params }).then((r) => r.data)
    },
  })

  const componentOptionsQuery = useQuery({
    queryKey: ['standard-job-components', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/components`, { params: { page: 1, page_size: 5000, is_unmapped: 'false' } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const summaryQuery = useQuery({
    queryKey: ['std-job-summary', vesselId, libraryType, filterSociety, filterMachinery, search],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/standard-jobs/summary`, {
        params: {
          job_type: libraryType,
          class_society: filterSociety || undefined,
          machinery_type: filterMachinery || undefined,
          search: search || undefined,
          is_critical: false,
        },
      }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const pageJobs: StandardJob[] = standardJobsQuery.data?.items ?? []
  const pageJobIds = pageJobs.map((job) => job.id)

  const matchesQuery = useQuery({
    queryKey: ['std-job-matches', vesselId, pageJobIds.join(','), filterMatchStatus],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/standard-jobs/matches`, {
          params: {
            page: 1,
            page_size: Math.max(1, pageJobIds.length || 1),
            standard_job_ids: pageJobIds.join(','),
            ...(filterMatchStatus ? { match_status: filterMatchStatus } : {}),
          },
        })
        .then((r) => r.data),
    enabled: !!vesselId && pageJobIds.length > 0,
  })

  const runComparisonMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/run-comparison`, {
        job_type: libraryType,
        class_society: libraryType === 'class' ? (filterSociety || null) : null,
        machinery_type: filterMachinery || null,
      }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['standard-jobs-comparison'] })
      queryClient.invalidateQueries({ queryKey: ['std-job-summary', vesselId] })
      setActionMessage(
        libraryType === 'class' && filterSociety
          ? `Comparison completed for ${displayClassSociety(filterSociety)} class jobs against instruction-manual jobs.`
          : 'Comparison completed against instruction-manual jobs.'
      )
      setActionError(null)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Comparison failed'))
      setActionMessage(null)
    },
  })

  const importSelectedMutation = useMutation({
    mutationFn: (payload: { standard_job_ids?: string[]; import_all?: boolean; component_map?: Record<string, string> }) =>
      apiClient
        .post(`/vessels/${vesselId}/standard-jobs/import-batch`, {
          standard_job_ids: payload.standard_job_ids ?? [],
          component_map: payload.component_map ?? {},
          job_type: libraryType,
          class_society: filterSociety || null,
          machinery_type: filterMachinery || null,
          include_critical: false,
          import_all: payload.import_all ?? false,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      const totalAffected = (data.imported ?? 0) + (data.merged ?? 0)
      setActionMessage(`Added ${data.imported} and updated ${data.merged} library jobs in Jobs Review. The comparison view has been refreshed so you can verify what moved.`)
      setActionError(null)
      setSelectedJobIds([])
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['standard-jobs-comparison'] })
      queryClient.invalidateQueries({ queryKey: ['std-job-summary', vesselId] })
      if (totalAffected > 0) setPage(1)
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to add standard jobs to Jobs Review'))
      setActionMessage(null)
    },
  })

  const importSingleMutation = useMutation({
    mutationFn: ({ standardJobId, componentId }: { standardJobId: string; componentId?: string }) =>
      apiClient
        .post(`/vessels/${vesselId}/standard-jobs/import/${standardJobId}`, null, {
          params: componentId ? { component_id: componentId } : {},
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setActionMessage('Library job added to Jobs Review. The row will now show its Jobs Review linkage here.')
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['standard-jobs-comparison'] })
      queryClient.invalidateQueries({ queryKey: ['std-job-summary', vesselId] })
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Failed to add standard job to Jobs Review'))
      setActionMessage(null)
    },
  })

  const markNaMutation = useMutation({
    mutationFn: ({ matchId, reason }: { matchId: string; reason: string }) =>
      apiClient.patch(`/vessels/${vesselId}/standard-jobs/matches/${matchId}`, {
        match_status: 'not_applicable',
        not_applicable_reason: reason,
      }).then((r) => r.data),
    onSuccess: () => {
      setActionMessage('Standard job marked as not applicable.')
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-summary', vesselId] })
      setShowNaDialog(false)
      setNaReason('')
      setNaMatchId(null)
      setNaMatchIds([])
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Unable to update match'))
      setActionMessage(null)
    },
  })

  const batchMarkNaMutation = useMutation({
    mutationFn: async ({ matchIds, reason }: { matchIds: string[]; reason: string }) => {
      await Promise.all(
        matchIds.map((matchId) =>
          apiClient.patch(`/vessels/${vesselId}/standard-jobs/matches/${matchId}`, {
            match_status: 'not_applicable',
            not_applicable_reason: reason,
          })
        )
      )
    },
    onSuccess: () => {
      setActionMessage(`Marked ${naMatchIds.length} selected library job(s) as not applicable.`)
      setActionError(null)
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['std-job-summary', vesselId] })
      setShowNaDialog(false)
      setNaReason('')
      setNaMatchId(null)
      setNaMatchIds([])
    },
    onError: (error: unknown) => {
      setActionError(getApiErrorMessage(error, 'Unable to update selected matches'))
      setActionMessage(null)
    },
  })

  const allJobs: StandardJob[] = standardJobsQuery.data?.items ?? []
  const total = standardJobsQuery.data?.total ?? 0
  const totalPages = standardJobsQuery.data?.total_pages ?? 1
  const summary: ComparisonSummary | undefined = summaryQuery.data
  const components: ComponentOption[] = componentOptionsQuery.data?.items ?? []
  const matches: Match[] = matchesQuery.data?.items ?? []
  const matchByStdJobId = Object.fromEntries(matches.map((match) => [match.standard_job_id, match]))

  const suggestedComponentMap = useMemo(() => {
    const next: Record<string, string> = {}
    for (const job of allJobs) {
      const suggestion = suggestComponentId(job, components)
      if (suggestion) next[job.id] = suggestion
    }
    return next
  }, [allJobs, components])

  const visibleJobs = useMemo(() => {
    if (!filterMatchStatus) return allJobs
    return allJobs.filter((job) => (matchByStdJobId[job.id]?.match_status ?? 'not_found') === filterMatchStatus)
  }, [allJobs, filterMatchStatus, matchByStdJobId])

  const selectedSet = new Set(selectedJobIds)
  const visibleMatches = visibleJobs.map((job) => matchByStdJobId[job.id]).filter(Boolean) as Match[]
  const selectedMatches = selectedJobIds.map((jobId) => matchByStdJobId[jobId]).filter(Boolean) as Match[]
  const selectedMatchIds = selectedMatches.map((match) => match.id)
  const matchedCount = visibleMatches.filter((match) => match.match_status === 'matched').length
  const partialCount = visibleMatches.filter((match) => match.match_status === 'partial').length
  const notFoundCount = visibleMatches.filter((match) => match.match_status === 'not_found').length
  const notApplicableCount = visibleMatches.filter((match) => match.match_status === 'not_applicable').length
  const allSelected = visibleJobs.length > 0 && visibleJobs.every((job) => selectedSet.has(job.id))

  React.useEffect(() => {
    setPage(1)
    setSelectedJobIds([])
    setBatchComponentId('')
  }, [libraryType, filterSociety, filterMachinery, search, sortBy, sortOrder, pageSize])

  React.useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  const handleMarkNA = (matchId: string) => {
    setNaMatchId(matchId)
    setNaMatchIds([])
    setShowNaDialog(true)
  }

  const handleBatchMarkNA = () => {
    if (!selectedMatchIds.length) return
    setNaMatchId(null)
    setNaMatchIds(selectedMatchIds)
    setShowNaDialog(true)
  }

  const toggleJobSelection = (jobId: string) => {
    setSelectedJobIds((prev) => (
      prev.includes(jobId) ? prev.filter((id) => id !== jobId) : [...prev, jobId]
    ))
  }

  const getMappedComponentId = (jobId: string) => componentSelections[jobId] ?? suggestedComponentMap[jobId] ?? ''

  const buildComponentMapPayload = (jobIds: string[]) =>
    jobIds.reduce<Record<string, string>>((acc, jobId) => {
      const componentId = getMappedComponentId(jobId)
      if (componentId) acc[jobId] = componentId
      return acc
    }, {})

  const applyBatchComponentSelection = () => {
    if (!batchComponentId || selectedJobIds.length === 0) return
    setComponentSelections((prev) => {
      const next = { ...prev }
      for (const jobId of selectedJobIds) {
        next[jobId] = batchComponentId
      }
      return next
    })
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Standard Jobs Comparison</h1>
          <p className="mt-1 text-sm text-slate-400">
            Compare instruction-manual jobs against imported company SMS and CMS / class libraries, then send selected library jobs to Jobs Review.
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Library import and library maintenance are handled on the Standard Jobs Library page. Critical jobs are added later from Jobs Review.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={libraryType}
            onChange={(e) => setLibraryType(e.target.value as 'standard' | 'class')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200"
          >
            <option value="standard">Company SMS Jobs</option>
            <option value="class">CMS / Class Jobs</option>
          </select>
          <button
            onClick={() => runComparisonMutation.mutate()}
            disabled={runComparisonMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {runComparisonMutation.isPending ? 'Running...' : 'Run Comparison'}
          </button>
        </div>
      </div>

      {(actionMessage || actionError) && (
        <div className={`rounded-xl border px-4 py-3 text-sm ${actionError ? 'border-red-800 bg-red-950/30 text-red-300' : 'border-emerald-800 bg-emerald-950/30 text-emerald-300'}`}>
          {actionError || actionMessage}
        </div>
      )}

      {summary && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-sky-800 bg-sky-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-sky-300">{summary.library_total}</p>
            <p className="text-xs text-sky-200">Library Jobs In Scope</p>
          </div>
          <div className="rounded-xl border border-emerald-800 bg-emerald-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-emerald-300">{summary.added_to_review_total}</p>
            <p className="text-xs text-emerald-200">Added To Jobs Review</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 text-center">
            <p className="text-2xl font-bold text-slate-200">{summary.not_applicable_total}</p>
            <p className="text-xs text-slate-300">Marked Not Applicable</p>
          </div>
          <div className="rounded-xl border border-violet-800 bg-violet-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-violet-300">{summary.manual_linked_total}</p>
            <p className="text-xs text-violet-200">Linked To Manual Jobs</p>
          </div>
        </div>
      )}

      {visibleMatches.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-green-800 bg-green-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-green-400">{matchedCount}</p>
            <p className="text-xs text-green-300">Matched</p>
          </div>
          <div className="rounded-xl border border-amber-800 bg-amber-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-amber-400">{partialCount}</p>
            <p className="text-xs text-amber-300">Partial Match</p>
          </div>
          <div className="rounded-xl border border-red-800 bg-red-900/20 p-4 text-center">
            <p className="text-2xl font-bold text-red-400">{notFoundCount}</p>
            <p className="text-xs text-red-300">Not Matched</p>
          </div>
          <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-4 text-center">
            <p className="text-2xl font-bold text-slate-200">{notApplicableCount}</p>
            <p className="text-xs text-slate-300">Not Applicable</p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
        <select
          value={filterSociety}
          onChange={(e) => setFilterSociety(e.target.value)}
          disabled={libraryType !== 'class'}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 disabled:opacity-60"
        >
          <option value="">All Class Societies</option>
            {CLASS_SOCIETY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        <input
          type="text"
          value={filterMachinery}
          onChange={(e) => setFilterMachinery(e.target.value)}
          placeholder="Machinery type..."
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
        />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search standard jobs..."
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
        />
        <select
          value={filterMatchStatus}
          onChange={(e) => setFilterMatchStatus(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="">All Match Status</option>
          <option value="matched">Matched</option>
          <option value="partial">Partially Matched</option>
          <option value="not_found">Not Matched</option>
          <option value="not_applicable">Not Applicable</option>
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <select
          value={sortOrder}
          onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
          className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
        >
          <option value="asc">Sort A-Z / Low-High</option>
          <option value="desc">Sort Z-A / High-Low</option>
        </select>
      </div>

      <div className="rounded-xl border border-sky-900/50 bg-sky-950/20 px-4 py-3 text-xs text-sky-200">
        Use the Standard Jobs Library page to import or edit library jobs. On this page, compare them against instruction-manual jobs, choose component mappings, add selected class or company jobs into Jobs Review, then update CMS codes there before final export if needed.
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => importSelectedMutation.mutate({
            standard_job_ids: selectedJobIds,
            component_map: buildComponentMapPayload(selectedJobIds),
          })}
          disabled={selectedJobIds.length === 0 || importSelectedMutation.isPending}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          Add Selected To Jobs Review{selectedJobIds.length > 0 ? ` (${selectedJobIds.length})` : ''}
        </button>
        <button
          onClick={() => navigate(`/vessels/${vesselId}/jobs?source_kind=standard_library`)}
          className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700"
        >
          Open Jobs Review
        </button>
      </div>

      {selectedJobIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 p-3">
          <div className="text-sm text-slate-300">
            {selectedJobIds.length} selected
          </div>
          <select
            value={batchComponentId}
            onChange={(e) => setBatchComponentId(e.target.value)}
            className="w-[280px] rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200"
          >
            <option value="">Batch component mapping...</option>
            {components.map((component) => (
              <option key={component.id} value={component.id}>
                {component.component_name} ({component.main_machinery})
              </option>
            ))}
          </select>
          <button
            onClick={applyBatchComponentSelection}
            disabled={!batchComponentId}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            Apply Component To Selected
          </button>
          <button
            onClick={handleBatchMarkNA}
            disabled={selectedMatchIds.length === 0 || batchMarkNaMutation.isPending}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
          >
            Mark Selected Not Applicable
          </button>
          <button
            onClick={() => setSelectedJobIds([])}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            Clear selection
          </button>
          <div className="text-xs text-slate-500">
            {selectedMatchIds.length} selected row(s) already have comparison records.
          </div>
        </div>
      )}

      {standardJobsQuery.isError ? (
        <div className="rounded-xl border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {getApiErrorMessage(standardJobsQuery.error, 'Failed to load standard jobs library for comparison.')}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
        <table className="w-full min-w-[2150px] text-sm">
          <thead>
            <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
              <th className="px-4 py-3">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => setSelectedJobIds(e.target.checked ? visibleJobs.map((job) => job.id) : [])}
                />
              </th>
              <th className="px-4 py-3">Standard Job</th>
              <th className="px-4 py-3">Class Society</th>
              <th className="px-4 py-3">Machinery Type</th>
              <th className="px-4 py-3">Rank</th>
              <th className="px-4 py-3">Suggested Component</th>
              <th className="px-4 py-3">Frequency</th>
              <th className="px-4 py-3">Match Status</th>
              <th className="px-4 py-3">Matched Manual Job</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Standard Library Procedure</th>
              <th className="px-4 py-3">Instruction Manual Procedure</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {standardJobsQuery.isLoading ? (
              <tr>
                <td colSpan={13} className="py-12 text-center text-slate-500">
                  Loading comparison library...
                </td>
              </tr>
            ) : visibleJobs.length === 0 ? (
              <tr>
                <td colSpan={13} className="py-12 text-center text-slate-500">
                  No jobs found for the selected library and filters.
                </td>
              </tr>
            ) : (
              visibleJobs.map((job) => {
                const match = matchByStdJobId[job.id]
                const componentId = getMappedComponentId(job.id)
                return (
                  <tr key={job.id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedSet.has(job.id)}
                        onChange={() => toggleJobSelection(job.id)}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <p className="font-medium text-slate-200">{job.job_name}</p>
                      {job.library_reference && (
                        <p className="text-xs font-mono text-slate-500">{job.library_reference}</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-300">{displayClassSociety(job.class_society)}</td>
                    <td className="px-4 py-2.5 text-slate-400">{job.machinery_type}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">
                      {[job.performing_rank, job.verifying_rank].filter(Boolean).join(' / ') || '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={componentId}
                        onChange={(e) => setComponentSelections((prev) => ({ ...prev, [job.id]: e.target.value }))}
                        className="w-[260px] rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">Leave Unmapped For Review</option>
                        {components.map((component) => (
                          <option key={component.id} value={component.id}>
                            {component.component_name} ({component.main_machinery})
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-slate-400">
                      {job.frequency != null && job.frequency_type
                        ? `${job.frequency} ${job.frequency_type}`
                        : job.frequency_type ?? '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex flex-col gap-1">
                        <span className={`w-fit rounded-full px-2 py-0.5 text-xs font-medium ${MATCH_COLORS[match?.match_status ?? ''] ?? 'bg-slate-700 text-slate-300'}`}>
                          {match ? match.match_status.replace('_', ' ') : 'Not compared'}
                        </span>
                        {match?.jobs_review_job_id && (
                          <span className="w-fit rounded-full bg-emerald-900/40 px-2 py-0.5 text-xs font-medium text-emerald-300">
                            In Jobs Review
                          </span>
                        )}
                        <span className="text-xs text-slate-500">
                          {libraryType === 'class' ? 'CMS / Class' : 'Company SMS'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      {match ? (
                        <div className="min-w-[220px]">
                          <p className="text-slate-200">{match.matched_job_name ?? 'No manual job linked'}</p>
                          <p className="text-xs text-slate-500">
                            {[match.matched_job_code, match.matched_job_qc_status].filter(Boolean).join(' / ') || '-'}
                          </p>
                          {match.jobs_review_job_name && (
                            <p className="mt-1 text-xs text-emerald-300">
                              Jobs Review: {match.jobs_review_job_name}
                              {match.jobs_review_job_qc_status ? ` / ${match.jobs_review_job_qc_status}` : ''}
                            </p>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-600">Not compared</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">
                      {match?.match_score != null ? `${match.match_score}%` : '-'}
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      {renderProcedurePreview(job.job_description)}
                    </td>
                    <td className="px-4 py-2.5 align-top">
                      {renderProcedurePreview(match?.matched_job_description)}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        {!match?.jobs_review_job_id && (match?.match_status === 'not_found' || match?.match_status === 'partial' || !match) && (
                          <button
                            onClick={() => importSingleMutation.mutate({ standardJobId: job.id, componentId: componentId || undefined })}
                            className="rounded bg-sky-700 px-2 py-1 text-xs text-white hover:bg-sky-600"
                            title="Add this library job to Jobs Review"
                          >
                            <Download className="h-3 w-3" />
                          </button>
                        )}
                        {match?.jobs_review_job_id && (
                          <button
                            onClick={() => navigate(`/vessels/${vesselId}/jobs?job_ids=${match.jobs_review_job_id}`)}
                            className="rounded bg-emerald-700 px-2 py-1 text-xs text-white hover:bg-emerald-600"
                            title="Open linked Jobs Review record"
                          >
                            Open
                          </button>
                        )}
                        {match && match.match_status !== 'not_applicable' && (
                          <button
                            onClick={() => handleMarkNA(match.id)}
                            className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                            title="Mark not applicable"
                          >
                            <XCircle className="h-3 w-3" />
                          </button>
                        )}
                        {match?.not_applicable_reason && (
                          <span className="max-w-xs truncate text-xs text-slate-500">
                            {match.not_applicable_reason}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
        {total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-800 px-4 py-2.5">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>{total} total</span>
              <span>·</span>
              <span>Show</span>
              <select
                value={pageSize}
                onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
                className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
              >
                {PAGE_SIZE_OPTIONS.map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
              <span>per page</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={page === 1}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-400 hover:bg-slate-700 disabled:opacity-40"
              >
                {'<'} Prev
              </button>
              <span className="px-3 text-xs text-slate-500">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={page >= totalPages}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-400 hover:bg-slate-700 disabled:opacity-40"
              >
                Next {'>'}
              </button>
            </div>
          </div>
        )}
      </div>

      {showNaDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6">
            <h3 className="mb-3 text-lg font-semibold text-white">Mark Not Applicable</h3>
            <p className="mb-4 text-sm text-slate-400">
              Please provide a reason why this standard job is not applicable.
            </p>
            <textarea
              value={naReason}
              onChange={(e) => setNaReason(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. Vessel uses different class society requirements"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowNaDialog(false)
                  setNaReason('')
                }}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (naMatchIds.length > 0) {
                    batchMarkNaMutation.mutate({ matchIds: naMatchIds, reason: naReason })
                    return
                  }
                  if (naMatchId) markNaMutation.mutate({ matchId: naMatchId, reason: naReason })
                }}
                disabled={!naReason || markNaMutation.isPending || batchMarkNaMutation.isPending}
                className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {naMatchIds.length > 0 ? `Confirm (${naMatchIds.length})` : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StandardJobs
