import React, { useMemo, useState, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, Copy, ExternalLink, FileSearch, GitMerge, Pencil, Plus, Save, Upload, XCircle } from 'lucide-react'
import apiClient from '@/api/client'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'
import ResizableSplitView from '@/components/layout/ResizableSplitView'

interface ComponentOption {
  id: string
  component_name: string
  group1: string
  main_machinery: string
  qc_status?: string
}

interface RankOption {
  id: string
  rank_name: string
}

interface Job {
  id: string
  job_name: string
  job_code: string | null
  component_id: string | null
  component_name?: string | null
  component_maker?: string | null
  component_model?: string | null
  job_description: string | null
  safety_precaution?: string | null
  tools_required?: string | null
  frequency: number | null
  frequency_type: string | null
  verifying_rank?: string | null
  initial_due?: number | null
  initial_frequency_type?: string | null
  performing_rank: string | null
  cms_id: string | null
  is_critical: boolean
  confidence_score: number | null
  qc_status: string
  is_unmapped: boolean
  source_manual_id: string | null
  source_manual_name?: string | null
  page_reference: number | null
  source_page_number: number | null
  pdf_reference: string | null
  source_reference?: string | null
  source_kinds?: string[]
  source_summary?: string | null
}

type JobForm = {
  job_name: string
  job_code: string
  component_id: string
  job_description: string
  safety_precaution: string
  tools_required: string
  performing_rank: string
  verifying_rank: string
  frequency: string
  frequency_type: string
  initial_due: string
  initial_frequency_type: string
  cms_id: string
  is_critical: boolean
  qc_status: string
}

type InlineJobEdit = Partial<{
  job_name: string
  component_id: string
  job_code: string
  performing_rank: string
  verifying_rank: string
  frequency: string
  frequency_type: string
  cms_id: string
  qc_status: string
  is_critical: boolean
}>

type BatchJobFields = {
  component_id?: string
  performing_rank?: string
  verifying_rank?: string
  frequency?: string
  frequency_type?: string
  cms_id?: string
  qc_status?: string
  is_critical?: string
}

function RankSelect({
  value,
  options,
  onChange,
  placeholder,
  className,
}: {
  value: string
  options: RankOption[]
  onChange: (value: string) => void
  placeholder: string
  className: string
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={className}>
      <option value="">{placeholder}</option>
      {options.map((option) => (
        <option key={option.id} value={option.rank_name}>
          {option.rank_name}
        </option>
      ))}
    </select>
  )
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

const FREQUENCY_OPTIONS = ['daily', 'weekly', 'monthly', 'yearly', 'hourly']
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
const SORT_OPTIONS = [
  { value: 'job_name', label: 'Job Name' },
  { value: 'component', label: 'Component' },
  { value: 'job_code', label: 'Code' },
  { value: 'frequency', label: 'Frequency' },
  { value: 'frequency_type', label: 'Frequency Type' },
  { value: 'criticality', label: 'Criticality' },
  { value: 'qc_status', label: 'QC Status' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'source_reference', label: 'Source Reference' },
  { value: 'page_reference', label: 'Page Reference' },
  { value: 'created_at', label: 'Created At' },
]

const SOURCE_FILTER_OPTIONS = [
  { value: '', label: 'All Sources' },
  { value: 'instruction_manual', label: 'Instruction Manual' },
  { value: 'standard_library', label: 'Standard Library' },
  { value: 'critical_library', label: 'Critical Jobs Library' },
  { value: 'cms_file', label: 'CMS File' },
]

function getApiErrorMessage(error: unknown): string {
  const maybeError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = maybeError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return maybeError?.message ?? 'Request failed.'
}

function buildJobPayload(edit: InlineJobEdit | BatchJobFields): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if ('job_name' in edit) payload.job_name = edit.job_name ?? ''
  if ('component_id' in edit) payload.component_id = edit.component_id ? edit.component_id : null
  if ('job_code' in edit) payload.job_code = edit.job_code ? edit.job_code : null
  if ('performing_rank' in edit) payload.performing_rank = edit.performing_rank ? edit.performing_rank : null
  if ('verifying_rank' in edit) payload.verifying_rank = edit.verifying_rank ? edit.verifying_rank : null
  if ('frequency' in edit) payload.frequency = edit.frequency ? Number(edit.frequency) : null
  if ('frequency_type' in edit) payload.frequency_type = edit.frequency_type ? edit.frequency_type : null
  if ('cms_id' in edit) payload.cms_id = edit.cms_id ? edit.cms_id : null
  if ('qc_status' in edit && edit.qc_status) payload.qc_status = edit.qc_status
  if ('is_critical' in edit) {
    payload.is_critical =
      typeof edit.is_critical === 'string'
        ? edit.is_critical === 'true'
        : Boolean(edit.is_critical)
  }
  return payload
}

function toForm(initial?: Partial<Job>): JobForm {
  return {
    job_name: initial?.job_name ?? '',
    job_code: initial?.job_code ?? '',
    component_id: initial?.component_id ?? '',
    job_description: initial?.job_description ?? '',
    safety_precaution: initial?.safety_precaution ?? '',
    tools_required: initial?.tools_required ?? '',
    performing_rank: initial?.performing_rank ?? '',
    verifying_rank: initial?.verifying_rank ?? '',
    frequency: initial?.frequency != null ? String(initial.frequency) : '',
    frequency_type: initial?.frequency_type ?? '',
    initial_due: initial?.initial_due != null ? String(initial.initial_due) : '',
    initial_frequency_type: initial?.initial_frequency_type ?? '',
    cms_id: initial?.cms_id ?? '',
    is_critical: Boolean(initial?.is_critical),
    qc_status: initial?.qc_status ?? 'pending',
  }
}

function JobEditor({
  title,
  submitLabel,
  initial,
  components,
  rankOptions,
  isPending,
  onSubmit,
  onCancel,
  onSplit,
}: {
  title: string
  submitLabel: string
  initial?: Partial<Job>
  components: ComponentOption[]
  rankOptions: RankOption[]
  isPending: boolean
  onSubmit: (payload: Record<string, unknown>) => void
  onCancel?: () => void
  onSplit?: () => void
}) {
  const [form, setForm] = useState<JobForm>(() => toForm(initial))
  React.useEffect(() => setForm(toForm(initial)), [initial])
  const set = (key: keyof JobForm, value: string | boolean) => setForm((p) => ({ ...p, [key]: value }))

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className="mt-1 text-xs text-slate-500">Review against the PDF page shown below.</p>
        </div>
        <div className="flex items-center gap-2">
          {onSplit ? <button onClick={onSplit} className="rounded-lg border border-sky-700 px-3 py-1.5 text-xs text-sky-300 hover:bg-slate-800">Split To New</button> : null}
          {onCancel ? <button onClick={onCancel} className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">Cancel</button> : null}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs text-slate-400">Job Name</label>
          <input value={form.job_name} onChange={(e) => set('job_name', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Component</label>
          <select value={form.component_id} onChange={(e) => set('component_id', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
            <option value="">Unmapped</option>
            {components.map((component) => <option key={component.id} value={component.id}>{component.component_name} ({component.group1} / {component.main_machinery})</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Job Code</label>
          <input value={form.job_code} onChange={(e) => set('job_code', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Frequency</label>
          <input value={form.frequency} onChange={(e) => set('frequency', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Frequency Type</label>
          <select value={form.frequency_type} onChange={(e) => set('frequency_type', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
            <option value="">Select</option>
            {FREQUENCY_OPTIONS.map((option) => <option key={option} value={option}>{option.replace('_', ' ')}</option>)}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Performing Rank</label>
          <RankSelect
            value={form.performing_rank}
            options={rankOptions}
            onChange={(value) => set('performing_rank', value)}
            placeholder="Select rank"
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Verifying Rank</label>
          <RankSelect
            value={form.verifying_rank}
            options={rankOptions}
            onChange={(value) => set('verifying_rank', value)}
            placeholder="Select rank"
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Initial Due</label>
          <input value={form.initial_due} onChange={(e) => set('initial_due', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Initial Frequency Type</label>
          <select value={form.initial_frequency_type} onChange={(e) => set('initial_frequency_type', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
            <option value="">Select</option>
            {FREQUENCY_OPTIONS.map((option) => <option key={option} value={option}>{option.replace('_', ' ')}</option>)}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs text-slate-400">Job Procedure</label>
          <textarea value={form.job_description} onChange={(e) => set('job_description', e.target.value)} rows={5} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs text-slate-400">Safety Precaution</label>
          <textarea value={form.safety_precaution} onChange={(e) => set('safety_precaution', e.target.value)} rows={3} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div className="md:col-span-2">
          <label className="mb-1 block text-xs text-slate-400">Tools Required</label>
          <input value={form.tools_required} onChange={(e) => set('tools_required', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">CMS ID</label>
          <input value={form.cms_id} onChange={(e) => set('cms_id', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Criticality</label>
          <select value={form.is_critical ? 'true' : 'false'} onChange={(e) => set('is_critical', e.target.value === 'true')} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
            <option value="false">Non-Critical</option>
            <option value="true">Critical</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">QC Status</label>
          <select value={form.qc_status} onChange={(e) => set('qc_status', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="modified">Modified</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>
      <div className="flex items-center justify-end border-t border-slate-700 pt-4">
        <button
          onClick={() => onSubmit({
            job_name: form.job_name,
            job_code: form.job_code || null,
            component_id: form.component_id || null,
            job_description: form.job_description || null,
            safety_precaution: form.safety_precaution || null,
            tools_required: form.tools_required || null,
            performing_rank: form.performing_rank || null,
            verifying_rank: form.verifying_rank || null,
            frequency: form.frequency ? Number(form.frequency) : null,
            frequency_type: form.frequency_type || null,
            initial_due: form.initial_due ? Number(form.initial_due) : null,
            initial_frequency_type: form.initial_frequency_type || null,
            cms_id: form.cms_id || null,
            is_critical: form.is_critical,
            qc_status: form.qc_status,
            page_reference: initial?.page_reference ?? null,
            pdf_reference: initial?.pdf_reference ?? null,
            source_reference: initial?.source_reference ?? null,
            source_manual_id: initial?.source_manual_id ?? null,
          })}
          disabled={!form.job_name || isPending}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {submitLabel}
        </button>
      </div>
    </div>
  )
}

const JobsReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [filterQC, setFilterQC] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [filterSourceFile, setFilterSourceFile] = useState('')
  const [filterUnmapped, setFilterUnmapped] = useState(false)
  const [filterFreqType, setFilterFreqType] = useState('')
  const [filterNoCMS, setFilterNoCMS] = useState(false)
  const [filterSourceKind, setFilterSourceKind] = useState(searchParams.get('source_kind') ?? '')
  const [filterJobIds, setFilterJobIds] = useState(searchParams.get('job_ids') ?? '')
  const normalizedJobIds = useMemo(() => {
    if (!filterJobIds) return ''
    const unique = Array.from(new Set(filterJobIds.split(',').map((id) => id.trim()).filter(Boolean)))
    return unique.join(',')
  }, [filterJobIds])
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('job_name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [editingJob, setEditingJob] = useState<Job | null>(null)
  const [createDraft, setCreateDraft] = useState<Partial<Job> | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [edits, setEdits] = useState<Record<string, InlineJobEdit>>({})
  const [showBatchPanel, setShowBatchPanel] = useState(false)
  const [batchFields, setBatchFields] = useState<BatchJobFields>({})

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', vesselId, filterQC, filterCritical, filterSourceFile, filterUnmapped, filterFreqType, filterNoCMS, filterSourceKind, filterJobIds, search, sortBy, sortOrder, page, pageSize],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterCritical) params.is_critical = filterCritical
      if (filterSourceFile) params.pdf_reference = filterSourceFile
      if (filterUnmapped) params.is_unmapped = 'true'
      if (filterFreqType) params.frequency_type = filterFreqType
      if (filterSourceKind && !normalizedJobIds) params.source_kind = filterSourceKind
      if (normalizedJobIds) params.job_ids = normalizedJobIds
      if (search) params.search = search
      params.sort_by = sortBy
      params.sort_order = sortOrder
      params.page = String(page)
      params.page_size = String(pageSize)
      return apiClient.get(`/vessels/${vesselId}/jobs`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const sourceFilesQuery = useQuery({
    queryKey: ['job-source-files', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/jobs/source-files`).then((r) => r.data.items as string[]),
    enabled: !!vesselId,
  })

  const componentOptionsQuery = useQuery({
    queryKey: ['job-components', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/components`, { params: { page_size: 5000, is_unmapped: 'false' } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const rankOptionsQuery = useQuery({
    queryKey: ['job-ranks'],
    queryFn: () => apiClient.get('/job-ranks', { params: { page: 1, page_size: 1000, sort_by: 'rank_name', sort_order: 'asc' } }).then((r) => r.data),
  })
  const rankOptions: RankOption[] = rankOptionsQuery.data?.items ?? []

  const refreshJobs = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
  }, [queryClient, vesselId])

  const setEdit = useCallback((id: string, key: keyof InlineJobEdit, value: string | boolean) => {
    setEdits((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] ?? {}),
        [key]: value,
      },
    }))
  }, [])

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) => apiClient.post(`/vessels/${vesselId}/jobs/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      refreshJobs()
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected jobs were accepted.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) => apiClient.post(`/vessels/${vesselId}/jobs/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      refreshJobs()
      setSelectedIds(new Set())
      setEditingJob(null)
      setActionError(null)
      setActionMessage('Selected jobs were rejected.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const mergeJobsMutation = useMutation({
    mutationFn: ({ ids, targetId }: { ids: string[]; targetId?: string }) =>
      apiClient.post(`/vessels/${vesselId}/jobs/merge`, { ids, target_id: targetId }).then((r) => r.data),
    onSuccess: (job) => {
      refreshJobs()
      setSelectedIds(new Set([job.id]))
      setSelectedJob(job)
      setEditingJob(job)
      setCreateDraft(null)
      setActionError(null)
      setActionMessage('Selected jobs were merged.')
    },
    onError: (error: unknown) => setActionError(`Merge failed: ${getApiErrorMessage(error)}`),
  })

  const saveJobMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiClient.patch(`/vessels/${vesselId}/jobs/${id}`, payload).then((r) => r.data),
    onSuccess: (job) => {
      refreshJobs()
      setSelectedJob(job)
      setEditingJob(job)
      setActionError(null)
      setActionMessage('Job changes were saved.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const createJobMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiClient.post(`/vessels/${vesselId}/jobs`, payload).then((r) => r.data),
    onSuccess: (job) => {
      refreshJobs()
      setSelectedJob(job)
      setEditingJob(job)
      setCreateDraft(null)
      setActionError(null)
      setActionMessage('New job was created.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const saveInlineEditsMutation = useMutation({
    mutationFn: async (nextEdits: Record<string, InlineJobEdit>) => {
      const entries = Object.entries(nextEdits).filter(([, value]) => Object.keys(value).length > 0)
      await Promise.all(
        entries.map(([id, value]) =>
          apiClient.patch(`/vessels/${vesselId}/jobs/${id}`, buildJobPayload(value))
        )
      )
    },
    onSuccess: () => {
      refreshJobs()
      setEdits({})
      setActionError(null)
      setActionMessage('Inline job edits were saved.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const bulkUpdateMutation = useMutation({
    mutationFn: ({ ids, updates }: { ids: string[]; updates: BatchJobFields }) =>
      apiClient.post(`/vessels/${vesselId}/jobs/bulk-update`, { ids, updates: buildJobPayload(updates) }).then((r) => r.data),
    onSuccess: () => {
      refreshJobs()
      setShowBatchPanel(false)
      setBatchFields({})
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected jobs were updated.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const addCriticalJobsMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/add-critical-jobs`).then((r) => r.data),
    onSuccess: (result) => {
      refreshJobs()
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      setActionError(null)
      setActionMessage(
        `Critical jobs sync completed. Added ${result.added ?? 0}, updated ${result.updated ?? 0}, skipped ${result.skipped ?? 0}.`
      )
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const undoCriticalJobsMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/standard-jobs/remove-critical-jobs`).then((r) => r.data),
    onSuccess: (result) => {
      refreshJobs()
      queryClient.invalidateQueries({ queryKey: ['std-job-matches', vesselId] })
      setActionError(null)
      setActionMessage(
        `Critical jobs undo completed. Removed ${result.removed ?? 0}, unmarked ${result.unmarked ?? 0}, skipped ${result.skipped ?? 0}.`
      )
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const handleCMSUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      await apiClient.post(`/vessels/${vesselId}/jobs/upload-cms-mapping`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      refreshJobs()
      setActionError(null)
      setActionMessage('CMS mapping upload completed.')
    } catch (error) {
      setActionError(getApiErrorMessage(error))
    }
  }, [vesselId, refreshJobs])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const jobs: Job[] = useMemo(
    () => (data?.items ?? []).filter((job: Job) => !(filterNoCMS && job.cms_id)),
    [data?.items, filterNoCMS]
  )
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const hasActiveFilters = Boolean(
    filterQC ||
    filterCritical ||
    filterSourceFile ||
    filterUnmapped ||
    filterFreqType ||
    filterNoCMS ||
    filterSourceKind ||
    normalizedJobIds ||
    search.trim()
  )
  const activeSourceFilterLabel =
    SOURCE_FILTER_OPTIONS.find((option) => option.value === filterSourceKind)?.label ?? filterSourceKind

  const clearFilters = useCallback(() => {
    setFilterQC('')
    setFilterCritical('')
    setFilterSourceFile('')
    setFilterUnmapped(false)
    setFilterFreqType('')
    setFilterNoCMS(false)
    setFilterSourceKind('')
    setFilterJobIds('')
    setSearch('')
    setPage(1)
  }, [])

  React.useEffect(() => {
    setPage(1)
  }, [filterQC, filterCritical, filterSourceFile, filterUnmapped, filterFreqType, filterNoCMS, filterSourceKind, filterJobIds, search, sortBy, sortOrder, pageSize])

  React.useEffect(() => {
    const sourceKindParam = searchParams.get('source_kind') ?? ''
    if (sourceKindParam !== filterSourceKind) {
      setFilterSourceKind(sourceKindParam)
    }
    const jobIdsParam = searchParams.get('job_ids') ?? ''
    if (jobIdsParam !== filterJobIds) {
      setFilterJobIds(jobIdsParam)
    }
  }, [searchParams])

  React.useEffect(() => {
    const next = new URLSearchParams(searchParams)
    if (filterJobIds) {
      next.set('job_ids', filterJobIds)
    } else {
      next.delete('job_ids')
    }
    if (filterSourceKind) {
      next.set('source_kind', filterSourceKind)
    } else {
      next.delete('source_kind')
    }
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true })
    }
  }, [filterSourceKind, filterJobIds, searchParams, setSearchParams])

  React.useEffect(() => {
    if (page > totalPages) setPage(totalPages)
  }, [page, totalPages])

  React.useEffect(() => {
    if (!jobs.length) {
      setSelectedJob(null)
      setEditingJob(null)
      return
    }

    if (selectedJob) {
      const refreshed = jobs.find((job) => job.id === selectedJob.id)
      if (refreshed) setSelectedJob(refreshed)
    }

    if (editingJob) {
      const refreshed = jobs.find((job) => job.id === editingJob.id)
      if (refreshed) setEditingJob(refreshed)
    }
  }, [jobs, selectedJob, editingJob])

  const componentOptions: ComponentOption[] = useMemo(
    () => (componentOptionsQuery.data?.items ?? []).filter((component: ComponentOption) => component.qc_status !== 'rejected'),
    [componentOptionsQuery.data?.items]
  )

  const mergeTargetId = useMemo(() => {
    if (selectedJob && selectedIds.has(selectedJob.id)) return selectedJob.id
    return Array.from(selectedIds)[0]
  }, [selectedIds, selectedJob])

  const editorContent = editingJob ? (
    <JobEditor
      title="Edit Job"
      submitLabel="Save Changes"
      initial={editingJob}
      components={componentOptions}
      rankOptions={rankOptions}
      isPending={saveJobMutation.isPending}
      onCancel={() => setEditingJob(null)}
      onSplit={() => setCreateDraft(editingJob)}
      onSubmit={(payload) => saveJobMutation.mutate({ id: editingJob.id, payload })}
    />
  ) : createDraft ? (
    <JobEditor
      title="Add Job"
      submitLabel="Create Job"
      initial={createDraft}
      components={componentOptions}
      rankOptions={rankOptions}
      isPending={createJobMutation.isPending}
      onCancel={() => setCreateDraft(null)}
      onSubmit={(payload) => createJobMutation.mutate(payload)}
    />
  ) : selectedJob ? (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-white">{selectedJob.job_name}</h3>
          <p className="mt-1 text-xs text-slate-500">Select pages below, then edit, merge, or split while reviewing the PDF.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setCreateDraft(selectedJob)} className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
            <Copy className="mr-1 inline h-3.5 w-3.5" />
            Split To New
          </button>
          <button onClick={() => setEditingJob(selectedJob)} className="rounded-lg border border-sky-700 px-3 py-1.5 text-xs text-sky-300 hover:bg-slate-800">
            <Pencil className="mr-1 inline h-3.5 w-3.5" />
            Edit
          </button>
        </div>
      </div>
      <div className="grid gap-2 text-xs text-slate-400 md:grid-cols-2">
        <div>Component: <span className="text-slate-200">{selectedJob.component_name ?? 'Unmapped'}</span></div>
        <div>Code: <span className="text-slate-200">{selectedJob.job_code ?? '-'}</span></div>
        <div>Frequency: <span className="text-slate-200">{selectedJob.frequency != null && selectedJob.frequency_type ? `${selectedJob.frequency} ${selectedJob.frequency_type.replace('_', ' ')}` : '-'}</span></div>
        <div>CMS ID: <span className="text-slate-200">{selectedJob.cms_id ?? '-'}</span></div>
      </div>
    </div>
  ) : (
    <div className="text-sm text-slate-500">Select a job to review it side by side with the PDF preview.</div>
  )

  return (
    <>
      <ResizableSplitView
      storageKey={`jobs-review-layout:${vesselId ?? 'default'}`}
      initialLeftPercent={58}
      left={
      <div className="flex h-full flex-col gap-6 overflow-hidden">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Jobs Review</h1>
            <p className="mt-1 text-sm text-slate-400">Review, merge, split, and correct extracted maintenance jobs.</p>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 ? (
              <>
                <button onClick={() => bulkAcceptMutation.mutate(Array.from(selectedIds))} disabled={bulkAcceptMutation.isPending} className="flex items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-50">
                  <CheckCircle className="h-3.5 w-3.5" />
                  Accept ({selectedIds.size})
                </button>
                <button onClick={() => bulkRejectMutation.mutate(Array.from(selectedIds))} disabled={bulkRejectMutation.isPending} className="flex items-center gap-1.5 rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50">
                  <XCircle className="h-3.5 w-3.5" />
                  Reject ({selectedIds.size})
                </button>
                <button
                  onClick={() => setShowBatchPanel((value) => !value)}
                  className="flex items-center gap-1.5 rounded-lg border border-violet-700 px-3 py-1.5 text-xs font-medium text-violet-300 hover:bg-slate-800"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Batch Edit ({selectedIds.size})
                </button>
              </>
            ) : null}
            {selectedIds.size >= 2 ? (
                <button onClick={() => mergeJobsMutation.mutate({ ids: Array.from(selectedIds), targetId: mergeTargetId })} disabled={mergeJobsMutation.isPending} className="flex items-center gap-1.5 rounded-lg border border-sky-700 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-slate-800 disabled:opacity-50">
                  <GitMerge className="h-3.5 w-3.5" />
                  Merge Selected
                </button>
            ) : null}
            <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
              <Upload className="h-3.5 w-3.5" />
              Upload CMS Mapping
              <input type="file" accept=".csv" className="hidden" onChange={handleCMSUpload} />
            </label>
            <button onClick={() => { setCreateDraft({ qc_status: 'pending' }); setEditingJob(null) }} className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500">
              <Plus className="h-3.5 w-3.5" />
              Add Job
            </button>
            <button
              onClick={() => addCriticalJobsMutation.mutate()}
              disabled={addCriticalJobsMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-amber-700 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-slate-800 disabled:opacity-50"
            >
              <AlertCircle className="h-3.5 w-3.5" />
              {addCriticalJobsMutation.isPending ? 'Adding Critical...' : 'Add Critical Jobs'}
            </button>
            <button
              onClick={() => undoCriticalJobsMutation.mutate()}
              disabled={undoCriticalJobsMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-rose-700 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-slate-800 disabled:opacity-50"
            >
              <XCircle className="h-3.5 w-3.5" />
              {undoCriticalJobsMutation.isPending ? 'Undoing Critical...' : 'Undo Critical Jobs'}
            </button>
            {Object.keys(edits).length > 0 ? (
              <button
                onClick={() => saveInlineEditsMutation.mutate(edits)}
                disabled={saveInlineEditsMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                Save {Object.keys(edits).length} edit(s)
              </button>
            ) : null}
          </div>
        </div>

        {actionError ? (
          <div className="rounded-xl border border-red-900/60 bg-red-950/40 px-4 py-3 text-sm text-red-200">
            {actionError}
          </div>
        ) : null}

        {actionMessage ? (
          <div className="rounded-xl border border-green-900/60 bg-green-950/30 px-4 py-3 text-sm text-green-200">
            {actionMessage}
          </div>
        ) : null}

        {showBatchPanel && selectedIds.size > 0 ? (
          <div className="rounded-xl border border-violet-700 bg-violet-900/20 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-violet-300">Batch Update - {selectedIds.size} selected job(s)</p>
              <button onClick={() => { setShowBatchPanel(false); setBatchFields({}) }} className="text-slate-500 hover:text-white">
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <p className="text-xs text-slate-400">Fill only the fields you want to update. Empty fields are ignored.</p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <select value={batchFields.component_id ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, component_id: e.target.value }))} className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none">
                <option value="">Component - no change</option>
                <option value="__unmapped__">Unmapped</option>
                {componentOptions.map((component) => (
                  <option key={component.id} value={component.id}>{component.component_name}</option>
                ))}
              </select>
              <input value={batchFields.frequency ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, frequency: e.target.value }))} placeholder="Frequency" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <select value={batchFields.frequency_type ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, frequency_type: e.target.value }))} className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none">
                <option value="">Frequency Type - no change</option>
                {FREQUENCY_OPTIONS.map((option) => <option key={option} value={option}>{option.replace('_', ' ')}</option>)}
              </select>
              <RankSelect
                value={batchFields.performing_rank ?? ''}
                options={rankOptions}
                onChange={(value) => setBatchFields((prev) => ({ ...prev, performing_rank: value }))}
                placeholder="Performing Rank - no change"
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none"
              />
              <RankSelect
                value={batchFields.verifying_rank ?? ''}
                options={rankOptions}
                onChange={(value) => setBatchFields((prev) => ({ ...prev, verifying_rank: value }))}
                placeholder="Verifying Rank - no change"
                className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none"
              />
              <input value={batchFields.cms_id ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, cms_id: e.target.value }))} placeholder="CMS ID" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <select value={batchFields.qc_status ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, qc_status: e.target.value }))} className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none">
                <option value="">QC - no change</option>
                <option value="pending">Pending</option>
                <option value="accepted">Accepted</option>
                <option value="modified">Modified</option>
                <option value="rejected">Rejected</option>
              </select>
              <select value={batchFields.is_critical ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, is_critical: e.target.value }))} className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none">
                <option value="">Criticality - no change</option>
                <option value="true">Critical</option>
                <option value="false">Non-Critical</option>
              </select>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  const cleaned: BatchJobFields = { ...batchFields }
                  if (cleaned.component_id === '__unmapped__') cleaned.component_id = ''
                  const hasAny = Object.values(cleaned).some((value) => value !== undefined && value !== '')
                  if (!hasAny) return
                  bulkUpdateMutation.mutate({ ids: Array.from(selectedIds), updates: cleaned })
                }}
                disabled={bulkUpdateMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
              >
                <Save className="h-4 w-4" />
                Apply to {selectedIds.size} job(s)
              </button>
              <button onClick={() => setBatchFields({})} className="text-xs text-slate-500 hover:text-slate-300">
                Clear fields
              </button>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setFilterUnmapped(!filterUnmapped)} className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors ${filterUnmapped ? 'border-amber-600 bg-amber-900/20 text-amber-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}>
            <AlertCircle className="h-3 w-3" />
            Unmapped
          </button>
          <button onClick={() => setFilterNoCMS(!filterNoCMS)} className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${filterNoCMS ? 'border-sky-600 bg-sky-900/20 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}>
            CMS Codes Pending
          </button>
          <select value={filterSourceKind} onChange={(e) => { setFilterJobIds(''); setFilterSourceKind(e.target.value) }} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            {SOURCE_FILTER_OPTIONS.map((option) => (
              <option key={option.value || 'all'} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select value={filterFreqType} onChange={(e) => setFilterFreqType(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            <option value="">All Frequency</option>
            {FREQUENCY_OPTIONS.map((option) => <option key={option} value={option}>{option.replace('_', ' ')}</option>)}
          </select>
          <select value={filterCritical} onChange={(e) => setFilterCritical(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            <option value="">All Criticality</option>
            <option value="true">Critical</option>
            <option value="false">Non-Critical</option>
          </select>
          <select value={filterQC} onChange={(e) => setFilterQC(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            <option value="">All QC</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="modified">Modified</option>
          </select>
          <select value={filterSourceFile} onChange={(e) => setFilterSourceFile(e.target.value)} className="max-w-xs rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            <option value="">All Source Files</option>
            {(sourceFilesQuery.data ?? []).map((filename) => (
              <option key={filename} value={filename}>{filename}</option>
            ))}
          </select>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search jobs..."
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          />
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            {SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')} className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none">
            <option value="asc">Sort A-Z / Low-High</option>
            <option value="desc">Sort Z-A / High-Low</option>
          </select>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading jobs...</div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
              {hasActiveFilters ? (
                <>
                  <div className="text-slate-400">
                    No jobs match the current filters.
                    {filterSourceKind ? (
                      <div className="mt-1 text-xs text-slate-500">
                        Active source filter: {activeSourceFilterLabel}
                      </div>
                    ) : null}
                  </div>
                  <button
                    onClick={clearFilters}
                    className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 hover:bg-slate-700"
                  >
                    Clear filters
                  </button>
                </>
              ) : (
                <div className="text-slate-500">
                  No jobs found yet. Extract from Manual Review after component matching is complete.
                </div>
              )}
            </div>
          ) : (
            <table className="min-w-[2250px] w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs uppercase text-slate-500">
                  <th className="w-8 px-4 py-3"><input type="checkbox" checked={selectedIds.size === jobs.length && jobs.length > 0} onChange={(e) => setSelectedIds(e.target.checked ? new Set(jobs.map((job) => job.id)) : new Set())} className="h-3.5 w-3.5 rounded" /></th>
                  <th className="px-4 py-3">Job Name</th>
                  <th className="px-4 py-3">Component</th>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Procedure</th>
                  <th className="px-4 py-3">Frequency</th>
                  <th className="px-4 py-3">Ranks</th>
                  <th className="px-4 py-3">CMS ID</th>
                  <th className="px-4 py-3">Critical</th>
                  <th className="px-4 py-3">Confidence</th>
                  <th className="px-4 py-3">Source Type</th>
                  <th className="px-4 py-3">Source Reference</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">QC</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {jobs.map((job) => {
                  const pageRef = job.source_page_number ?? job.page_reference
                  const sourceLabel = job.source_manual_name ?? job.pdf_reference ?? 'Manual'
                  const sourceKinds = job.source_kinds ?? []
                  return (
                    <tr key={job.id} className={`cursor-pointer transition-colors hover:bg-slate-800/60 ${selectedIds.has(job.id) ? 'bg-sky-900/10' : ''} ${selectedJob?.id === job.id ? 'bg-slate-800/70' : ''} ${job.is_unmapped ? 'border-l-2 border-amber-600' : ''}`} onClick={() => { setSelectedJob(job); setEditingJob(null); setCreateDraft(null) }}>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selectedIds.has(job.id)} onChange={() => toggleSelect(job.id)} className="h-3.5 w-3.5 rounded" /></td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <input
                          value={edits[job.id]?.job_name ?? job.job_name}
                          onChange={(e) => setEdit(job.id, 'job_name', e.target.value)}
                          className="w-[320px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 focus:border-sky-500 focus:outline-none"
                          title={job.job_name}
                        />
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <select
                          value={edits[job.id]?.component_id ?? (job.component_id ?? '')}
                          onChange={(e) => setEdit(job.id, 'component_id', e.target.value)}
                          className="w-[240px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        >
                          <option value="">Unmapped</option>
                          {componentOptions.map((component) => (
                            <option key={component.id} value={component.id}>{component.component_name}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-mono text-xs text-slate-400" onClick={(e) => e.stopPropagation()}>
                        <input
                          value={edits[job.id]?.job_code ?? (job.job_code ?? '')}
                          onChange={(e) => setEdit(job.id, 'job_code', e.target.value)}
                          className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                      </td>
                      <td className="px-4 py-3"><div className="max-w-[360px] truncate whitespace-nowrap text-xs text-slate-400" title={job.job_description ?? ''}>{job.job_description ?? '-'}</div></td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-300" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-2">
                          <input
                            value={edits[job.id]?.frequency ?? (job.frequency != null ? String(job.frequency) : '')}
                            onChange={(e) => setEdit(job.id, 'frequency', e.target.value)}
                            className="w-16 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                          />
                          <select
                            value={edits[job.id]?.frequency_type ?? (job.frequency_type ?? '')}
                            onChange={(e) => setEdit(job.id, 'frequency_type', e.target.value)}
                            className="w-36 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                          >
                            <option value="">-</option>
                            {FREQUENCY_OPTIONS.map((option) => <option key={option} value={option}>{option.replace('_', ' ')}</option>)}
                          </select>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs" onClick={(e) => e.stopPropagation()}>
                        <div className="flex flex-col gap-1">
                          <RankSelect
                            value={edits[job.id]?.performing_rank ?? (job.performing_rank ?? '')}
                            options={rankOptions}
                            onChange={(value) => setEdit(job.id, 'performing_rank', value)}
                            placeholder="Performing"
                            className="w-40 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                          />
                          <RankSelect
                            value={edits[job.id]?.verifying_rank ?? (job.verifying_rank ?? '')}
                            options={rankOptions}
                            onChange={(value) => setEdit(job.id, 'verifying_rank', value)}
                            placeholder="Verifying"
                            className="w-40 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                          />
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs" onClick={(e) => e.stopPropagation()}>
                        <input
                          value={edits[job.id]?.cms_id ?? (job.cms_id ?? '')}
                          onChange={(e) => setEdit(job.id, 'cms_id', e.target.value)}
                          className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        />
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        <select
                          value={String(edits[job.id]?.is_critical ?? job.is_critical)}
                          onChange={(e) => setEdit(job.id, 'is_critical', e.target.value === 'true')}
                          className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        >
                          <option value="false">Non-Critical</option>
                          <option value="true">Critical</option>
                        </select>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{job.confidence_score != null ? <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${job.confidence_score >= 85 ? 'bg-green-700 text-green-100' : job.confidence_score >= 60 ? 'bg-amber-700 text-amber-100' : 'bg-red-700 text-red-100'}`}>{job.confidence_score}%</span> : '-'}</td>
                      <td className="px-4 py-3">
                        <div className="flex max-w-[210px] flex-wrap gap-1">
                          {sourceKinds.length > 0 ? sourceKinds.map((kind) => (
                            <span key={kind} className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
                              {SOURCE_FILTER_OPTIONS.find((option) => option.value === kind)?.label ?? kind}
                            </span>
                          )) : <span className="text-xs text-slate-500">-</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="max-w-[280px] truncate whitespace-nowrap text-xs text-slate-400" title={job.source_reference ?? ''}>
                          {job.source_reference ?? '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3"><div className="max-w-[220px] text-xs"><div className="inline-flex items-center gap-1 whitespace-nowrap text-sky-400" title={`${sourceLabel} page ${pageRef ?? '-'}`}><ExternalLink className="h-3 w-3" />{pageRef != null ? `p.${pageRef}` : 'No page'}</div><div className="mt-1 truncate whitespace-nowrap text-slate-500" title={sourceLabel}>{sourceLabel}</div></div></td>
                      <td className="px-4 py-3 whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                        <select
                          value={edits[job.id]?.qc_status ?? job.qc_status}
                          onChange={(e) => setEdit(job.id, 'qc_status', e.target.value)}
                          className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        >
                          <option value="pending">Pending</option>
                          <option value="accepted">Accepted</option>
                          <option value="modified">Modified</option>
                          <option value="rejected">Rejected</option>
                        </select>
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-2">
                          <button onClick={() => { setSelectedJob(job); setEditingJob(job); setCreateDraft(null) }} className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600" title="Edit job"><Pencil className="h-3.5 w-3.5" /></button>
                          <button onClick={() => { setSelectedJob(job); setCreateDraft(job); setEditingJob(null) }} className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600" title="Split to new job"><Copy className="h-3.5 w-3.5" /></button>
                          <button onClick={() => setSelectedJob(job)} disabled={!job.source_manual_id} className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-40" title="Preview manual pages"><FileSearch className="h-3.5 w-3.5" /></button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
        {total > 0 ? (
          <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 px-4 py-2.5">
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
        ) : null}
      </div>

      }
      right={
      <ManualPagePreview
        vesselId={vesselId ?? ''}
        manualId={selectedJob?.source_manual_id}
        manualName={selectedJob?.source_manual_name ?? selectedJob?.pdf_reference}
        title="Job Source Preview"
        subtitle={selectedJob ? [selectedJob.job_name, selectedJob.component_name, selectedJob.component_maker, selectedJob.component_model].filter(Boolean).join(' / ') : null}
        defaultPages={selectedJob?.source_page_number ?? selectedJob?.page_reference}
        panelClassName="h-full w-full min-w-0"
        headerContent={editorContent}
        showTextSnippet={false}
      />
      }
      />
    </>
  )
}

export default JobsReview
