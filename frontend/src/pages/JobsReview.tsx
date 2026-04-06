import React, { useMemo, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle, Copy, ExternalLink, FileSearch, GitMerge, Pencil, Plus, Upload, XCircle } from 'lucide-react'
import apiClient from '@/api/client'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'

interface ComponentOption {
  id: string
  component_name: string
  group1: string
  main_machinery: string
  qc_status?: string
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

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

const FREQUENCY_OPTIONS = ['daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'half_yearly', 'yearly', 'biannual', 'running_hours']

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
  isPending,
  onSubmit,
  onCancel,
  onSplit,
}: {
  title: string
  submitLabel: string
  initial?: Partial<Job>
  components: ComponentOption[]
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
          <input value={form.performing_rank} onChange={(e) => set('performing_rank', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Verifying Rank</label>
          <input value={form.verifying_rank} onChange={(e) => set('verifying_rank', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
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
        <div className="flex items-center gap-2 pt-6">
          <input id="job-critical" type="checkbox" checked={form.is_critical} onChange={(e) => set('is_critical', e.target.checked)} className="h-4 w-4 rounded" />
          <label htmlFor="job-critical" className="text-sm text-slate-300">Critical job</label>
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
  const queryClient = useQueryClient()
  const [filterQC, setFilterQC] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [filterUnmapped, setFilterUnmapped] = useState(false)
  const [filterFreqType, setFilterFreqType] = useState('')
  const [filterNoCMS, setFilterNoCMS] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [editingJob, setEditingJob] = useState<Job | null>(null)
  const [createDraft, setCreateDraft] = useState<Partial<Job> | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['jobs', vesselId, filterQC, filterCritical, filterUnmapped, filterFreqType, filterNoCMS],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterCritical) params.is_critical = filterCritical
      if (filterUnmapped) params.is_unmapped = 'true'
      if (filterFreqType) params.frequency_type = filterFreqType
      return apiClient.get(`/vessels/${vesselId}/jobs`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const componentOptionsQuery = useQuery({
    queryKey: ['job-components', vesselId],
    queryFn: () => apiClient.get(`/vessels/${vesselId}/components`, { params: { page_size: 5000, is_unmapped: 'false' } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const refreshJobs = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
  }, [queryClient, vesselId])

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) => apiClient.post(`/vessels/${vesselId}/jobs/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      refreshJobs()
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected jobs were accepted.')
    },
    onError: (error: Error) => setActionError(error.message),
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
    onError: (error: Error) => setActionError(error.message),
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
    onError: (error: Error) => setActionError(error.message),
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
    onError: (error: Error) => setActionError(error.message),
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
    onError: (error: Error) => setActionError(error.message),
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
      setActionError((error as Error).message)
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
    <div className="flex h-full gap-4">
      <div className="flex flex-1 flex-col gap-6 overflow-hidden">
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

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => setFilterUnmapped(!filterUnmapped)} className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors ${filterUnmapped ? 'border-amber-600 bg-amber-900/20 text-amber-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}>
            <AlertCircle className="h-3 w-3" />
            Unmapped
          </button>
          <button onClick={() => setFilterNoCMS(!filterNoCMS)} className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${filterNoCMS ? 'border-sky-600 bg-sky-900/20 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'}`}>
            CMS Codes Pending
          </button>
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
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading jobs...</div>
          ) : jobs.length === 0 ? (
            <div className="py-16 text-center text-slate-500">No jobs found yet. Extract from Manual Review after component matching is complete.</div>
          ) : (
            <table className="min-w-[1600px] w-full text-sm">
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
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">QC</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {jobs.map((job) => {
                  const pageRef = job.source_page_number ?? job.page_reference
                  const sourceLabel = job.source_manual_name ?? job.pdf_reference ?? 'Manual'
                  return (
                    <tr key={job.id} className={`cursor-pointer transition-colors hover:bg-slate-800/60 ${selectedIds.has(job.id) ? 'bg-sky-900/10' : ''} ${selectedJob?.id === job.id ? 'bg-slate-800/70' : ''} ${job.is_unmapped ? 'border-l-2 border-amber-600' : ''}`} onClick={() => { setSelectedJob(job); setEditingJob(null); setCreateDraft(null) }}>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selectedIds.has(job.id)} onChange={() => toggleSelect(job.id)} className="h-3.5 w-3.5 rounded" /></td>
                      <td className="px-4 py-3"><div className="max-w-[320px] truncate whitespace-nowrap font-medium text-slate-100" title={job.job_name}>{job.job_name}</div></td>
                      <td className="px-4 py-3">{job.component_name ? <div className="max-w-[250px] truncate whitespace-nowrap text-slate-200" title={`${job.component_name} ${job.component_maker ?? ''} ${job.component_model ?? ''}`.trim()}>{job.component_name}</div> : <span className="rounded-full bg-amber-900/40 px-2 py-0.5 text-xs text-amber-300">Unmapped</span>}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-mono text-xs text-slate-400">{job.job_code ?? '-'}</td>
                      <td className="px-4 py-3"><div className="max-w-[360px] truncate whitespace-nowrap text-xs text-slate-400" title={job.job_description ?? ''}>{job.job_description ?? '-'}</div></td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-300">{job.frequency != null && job.frequency_type ? `${job.frequency} ${job.frequency_type.replace('_', ' ')}` : '-'}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-slate-400">{[job.performing_rank, job.verifying_rank].filter(Boolean).join(' / ') || '-'}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs">{job.cms_id ? <span className="font-mono text-green-400">{job.cms_id}</span> : <span className="text-amber-500">Pending</span>}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{job.is_critical ? <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">Critical</span> : <span className="text-slate-600">-</span>}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{job.confidence_score != null ? <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${job.confidence_score >= 85 ? 'bg-green-700 text-green-100' : job.confidence_score >= 60 ? 'bg-amber-700 text-amber-100' : 'bg-red-700 text-red-100'}`}>{job.confidence_score}%</span> : '-'}</td>
                      <td className="px-4 py-3"><div className="max-w-[220px] text-xs"><div className="inline-flex items-center gap-1 whitespace-nowrap text-sky-400" title={`${sourceLabel} page ${pageRef ?? '-'}`}><ExternalLink className="h-3 w-3" />{pageRef != null ? `p.${pageRef}` : 'No page'}</div><div className="mt-1 truncate whitespace-nowrap text-slate-500" title={sourceLabel}>{sourceLabel}</div></div></td>
                      <td className="px-4 py-3 whitespace-nowrap"><span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${QC_COLORS[job.qc_status] ?? 'bg-slate-700 text-slate-300'}`}>{job.qc_status}</span></td>
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
      </div>

      <ManualPagePreview
        vesselId={vesselId ?? ''}
        manualId={selectedJob?.source_manual_id}
        manualName={selectedJob?.source_manual_name ?? selectedJob?.pdf_reference}
        title="Job Source Preview"
        subtitle={selectedJob ? [selectedJob.job_name, selectedJob.component_name, selectedJob.component_maker, selectedJob.component_model].filter(Boolean).join(' • ') : null}
        defaultPages={selectedJob?.source_page_number ?? selectedJob?.page_reference}
        panelClassName="w-[56rem]"
        headerContent={editorContent}
        showTextSnippet={false}
      />
    </div>
  )
}

export default JobsReview
