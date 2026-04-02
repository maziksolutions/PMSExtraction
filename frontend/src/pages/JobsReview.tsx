import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, Upload, AlertCircle, ExternalLink, FileSearch, Plus, Pencil } from 'lucide-react'
import apiClient from '@/api/client'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'

interface ComponentOption {
  id: string
  component_name: string
  group1: string
  group2: string
  main_machinery: string
  maker?: string | null
  model?: string | null
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

interface JobEditorModalProps {
  title: string
  submitLabel: string
  isPending: boolean
  components: ComponentOption[]
  initialValues?: Partial<Job>
  onClose: () => void
  onSubmit: (payload: Record<string, unknown>) => void
}

function JobEditorModal({ title, submitLabel, isPending, components, initialValues, onClose, onSubmit }: JobEditorModalProps) {
  const [form, setForm] = useState({
    job_name: initialValues?.job_name ?? '',
    job_code: initialValues?.job_code ?? '',
    component_id: initialValues?.component_id ?? '',
    job_description: initialValues?.job_description ?? '',
    safety_precaution: initialValues?.safety_precaution ?? '',
    tools_required: initialValues?.tools_required ?? '',
    performing_rank: initialValues?.performing_rank ?? '',
    verifying_rank: initialValues?.verifying_rank ?? '',
    frequency: initialValues?.frequency != null ? String(initialValues.frequency) : '',
    frequency_type: initialValues?.frequency_type ?? '',
    initial_due: initialValues?.initial_due != null ? String(initialValues.initial_due) : '',
    initial_frequency_type: initialValues?.initial_frequency_type ?? '',
    cms_id: initialValues?.cms_id ?? '',
    is_critical: Boolean(initialValues?.is_critical),
    qc_status: initialValues?.qc_status ?? 'pending',
  })

  const set = (key: keyof typeof form, value: string | boolean) => setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><XCircle className="h-5 w-5" /></button>
        </div>
        <div className="grid gap-4 px-6 py-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Job Name</label>
            <input value={form.job_name} onChange={(e) => set('job_name', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Component</label>
            <select value={form.component_id} onChange={(e) => set('component_id', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
              <option value="">Unmapped</option>
              {components.map((component) => (
                <option key={component.id} value={component.id}>
                  {component.component_name} ({component.group1} / {component.main_machinery})
                </option>
              ))}
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
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Biweekly</option>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="half_yearly">Half Yearly</option>
              <option value="yearly">Yearly</option>
              <option value="biannual">Biannual</option>
              <option value="running_hours">Running Hours</option>
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
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="biweekly">Biweekly</option>
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="half_yearly">Half Yearly</option>
              <option value="yearly">Yearly</option>
              <option value="biannual">Biannual</option>
              <option value="running_hours">Running Hours</option>
            </select>
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
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Job Procedure</label>
            <textarea value={form.job_description} onChange={(e) => set('job_description', e.target.value)} rows={4} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Safety Precaution</label>
            <textarea value={form.safety_precaution} onChange={(e) => set('safety_precaution', e.target.value)} rows={3} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Tools Required</label>
            <input value={form.tools_required} onChange={(e) => set('tools_required', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-700 px-6 py-4">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
          <button
            onClick={() =>
              onSubmit({
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
              })
            }
            disabled={!form.job_name || isPending}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
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
  const [showCreateJob, setShowCreateJob] = useState(false)

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
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/components`, { params: { page_size: 5000, is_unmapped: 'false' } })
        .then((r) => r.data),
    enabled: !!vesselId,
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/jobs/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/jobs/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const saveJobMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiClient.patch(`/vessels/${vesselId}/jobs/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setEditingJob(null)
    },
  })

  const createJobMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiClient.post(`/vessels/${vesselId}/jobs`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
      setShowCreateJob(false)
    },
  })

  const handleCMSUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const formData = new FormData()
      formData.append('file', file)
      await apiClient.post(`/vessels/${vesselId}/jobs/upload-cms-mapping`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      queryClient.invalidateQueries({ queryKey: ['jobs', vesselId] })
    },
    [vesselId, queryClient]
  )

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const jobs: Job[] = (data?.items ?? []).filter((j: Job) => {
    if (filterNoCMS && j.cms_id) return false
    return true
  })
  const componentOptions: ComponentOption[] = (componentOptionsQuery.data?.items ?? []).filter((component: ComponentOption) => component.qc_status !== 'rejected')

  return (
    <div className="flex h-full gap-4">
      {showCreateJob && (
        <JobEditorModal
          title="Add Job"
          submitLabel="Create Job"
          isPending={createJobMutation.isPending}
          components={componentOptions}
          onClose={() => setShowCreateJob(false)}
          onSubmit={(payload) => createJobMutation.mutate(payload)}
        />
      )}
      {editingJob && (
        <JobEditorModal
          title="Edit Job"
          submitLabel="Save Changes"
          isPending={saveJobMutation.isPending}
          components={componentOptions}
          initialValues={editingJob}
          onClose={() => setEditingJob(null)}
          onSubmit={(payload) => saveJobMutation.mutate({ id: editingJob.id, payload })}
        />
      )}
      <div className="flex flex-1 flex-col gap-6 overflow-hidden">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Jobs Review</h1>
            <p className="mt-1 text-sm text-slate-400">Review and correct extracted maintenance jobs.</p>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 && (
              <>
                <button
                  onClick={() => bulkAcceptMutation.mutate(Array.from(selectedIds))}
                  className="flex items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600"
                >
                  <CheckCircle className="h-3.5 w-3.5" />
                  Accept ({selectedIds.size})
                </button>
                <button
                  onClick={() => bulkRejectMutation.mutate(Array.from(selectedIds))}
                  className="flex items-center gap-1.5 rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Reject ({selectedIds.size})
                </button>
              </>
            )}
            <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800">
              <Upload className="h-3.5 w-3.5" />
              Upload CMS Mapping
              <input type="file" accept=".csv" className="hidden" onChange={handleCMSUpload} />
            </label>
            <button
              onClick={() => setShowCreateJob(true)}
              className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Job
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setFilterUnmapped(!filterUnmapped)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs transition-colors ${
              filterUnmapped ? 'border-amber-600 bg-amber-900/20 text-amber-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            <AlertCircle className="h-3 w-3" />
            Unmapped
          </button>
          <button
            onClick={() => setFilterNoCMS(!filterNoCMS)}
            className={`rounded-lg border px-3 py-1.5 text-xs transition-colors ${
              filterNoCMS ? 'border-sky-600 bg-sky-900/20 text-sky-300' : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            CMS Codes Pending
          </button>
          <select
            value={filterFreqType}
            onChange={(e) => setFilterFreqType(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Frequency</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="biweekly">Biweekly (2 weeks)</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="half_yearly">Half Yearly</option>
            <option value="yearly">Yearly</option>
            <option value="biannual">Biannual (2 years)</option>
            <option value="running_hours">Running Hours</option>
          </select>
          <select
            value={filterCritical}
            onChange={(e) => setFilterCritical(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Criticality</option>
            <option value="true">Critical</option>
            <option value="false">Non-Critical</option>
          </select>
          <select
            value={filterQC}
            onChange={(e) => setFilterQC(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All QC</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
          </select>
          {(filterQC || filterCritical || filterFreqType) && (
            <button
              onClick={() => { setFilterQC(''); setFilterCritical(''); setFilterFreqType('') }}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading jobs...</div>
          ) : jobs.length === 0 ? (
            <div className="py-16 text-center text-slate-500">No jobs found yet. Extract from Manual Review after component matching is complete.</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-500 uppercase">
                  <th className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      onChange={(e) =>
                        e.target.checked
                          ? setSelectedIds(new Set(jobs.map((j) => j.id)))
                          : setSelectedIds(new Set())
                      }
                      checked={selectedIds.size === jobs.length && jobs.length > 0}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </th>
                  <th className="px-4 py-3">Job Name</th>
                  <th className="px-4 py-3">Component</th>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3">Frequency</th>
                  <th className="px-4 py-3">Rank</th>
                  <th className="px-4 py-3">CMS ID</th>
                  <th className="px-4 py-3">Critical</th>
                  <th className="px-4 py-3">Confidence</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">QC Status</th>
                  <th className="px-4 py-3">Preview</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {jobs.map((job) => (
                  <tr
                    key={job.id}
                    className={`hover:bg-slate-800/50 transition-colors ${
                      selectedIds.has(job.id) ? 'bg-sky-900/10' : ''
                    } ${job.is_unmapped ? 'border-l-2 border-amber-600' : ''}`}
                  >
                  <td className="px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(job.id)}
                      onChange={() => toggleSelect(job.id)}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </td>
                  <td className="px-4 py-2.5 text-slate-200 font-medium">{job.job_name}</td>
                  <td className="px-4 py-2.5">
                    {job.component_name ? (
                      <div className="min-w-[180px]">
                        <p className="text-slate-200">{job.component_name}</p>
                        <p className="text-xs text-slate-500">
                          {[job.component_maker, job.component_model].filter(Boolean).join(' • ') || 'Linked'}
                        </p>
                      </div>
                    ) : (
                      <span className="rounded-full bg-amber-900/40 px-2 py-0.5 text-xs text-amber-300">Unmapped</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 font-mono text-xs">{job.job_code ?? '—'}</td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate text-xs">
                    {job.job_description?.slice(0, 80) ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-slate-300 whitespace-nowrap">
                    {job.frequency != null && job.frequency_type
                      ? `${job.frequency} ${job.frequency_type.replace('_', ' ')}`
                      : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-slate-400 text-xs">{job.performing_rank ?? '—'}</td>
                  <td className="px-4 py-2.5">
                    {job.cms_id ? (
                      <span className="font-mono text-xs text-green-400">{job.cms_id}</span>
                    ) : (
                      <span className="text-xs text-amber-500">Pending</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {job.is_critical ? (
                      <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">Critical</span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {job.confidence_score != null ? (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          job.confidence_score >= 85
                            ? 'bg-green-700 text-green-100'
                            : job.confidence_score >= 60
                            ? 'bg-amber-700 text-amber-100'
                            : 'bg-red-700 text-red-100'
                        }`}
                      >
                        {job.confidence_score}%
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {(job.source_page_number ?? job.page_reference) != null ? (
                      <div className="min-w-[170px] text-xs">
                        <div
                          title={`${job.pdf_reference ?? job.source_manual_name ?? 'Manual'} — page ${job.source_page_number ?? job.page_reference}`}
                          className="inline-flex items-center gap-1 text-sky-400"
                        >
                          <ExternalLink className="h-3 w-3" />
                          p.{job.source_page_number ?? job.page_reference}
                        </div>
                        <p className="mt-1 truncate text-slate-500">{job.source_manual_name ?? job.pdf_reference ?? 'Manual'}</p>
                      </div>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        QC_COLORS[job.qc_status] ?? 'bg-slate-700 text-slate-300'
                      }`}
                    >
                      {job.qc_status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => setSelectedJob(job)}
                      disabled={!job.source_manual_id}
                      className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
                      title="Preview manual pages"
                    >
                      <FileSearch className="h-3.5 w-3.5" />
                    </button>
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => {
                        setSelectedJob(job)
                        setEditingJob(job)
                      }}
                      className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600"
                      title="Edit job"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  </td>
                  </tr>
                ))}
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
        subtitle={
          selectedJob
            ? [selectedJob.job_name, selectedJob.component_name, selectedJob.component_maker, selectedJob.component_model]
                .filter(Boolean)
                .join(' • ')
            : null
        }
        defaultPages={selectedJob?.source_page_number ?? selectedJob?.page_reference}
      />
    </div>
  )
}

export default JobsReview
