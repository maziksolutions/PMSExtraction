import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, Save, XCircle, FileSearch, ExternalLink, Plus, Pencil, Scissors, Download, Trash2 } from 'lucide-react'
import apiClient from '@/api/client'
import { SearchableSelect } from '@/components/SearchableSelect'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'

import SnipExtractModal from '@/components/spares/SnipExtractModal'

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

interface Spare {
  id: string
  part_name: string
  part_number: string | null
  drawing_number: string | null
  drawing_position: string | null
  specification: string | null
  spare_assembly?: string | null
  assembly_description?: string | null
  spare_maker: string | null
  spare_model?: string | null
  component_id: string | null
  component_name?: string | null
  component_maker?: string | null
  component_model?: string | null
  source_manual_id: string | null
  source_manual_name?: string | null
  pdf_reference?: string | null
  source_reference?: string | null
  page_reference: number | null
  extraction_method: string
  is_critical: boolean
  confidence_score: number | null
  qc_status: string
  is_duplicate: boolean
}

type InlineSpareEdit = Partial<{
  part_name: string
  part_number: string
  drawing_number: string
  drawing_position: string
  specification: string
  spare_assembly: string
  assembly_description: string
  spare_maker: string
  spare_model: string
  component_id: string
  qc_status: string
  is_critical: boolean
}>

type BatchSpareFields = {
  part_name?: string
  part_number?: string
  drawing_number?: string
  drawing_position?: string
  component_id?: string
  spare_assembly?: string
  assembly_description?: string
  spare_maker?: string
  spare_model?: string
  qc_status?: string
  is_critical?: string
}

function getApiErrorMessage(error: unknown): string {
  const maybeError = error as { response?: { data?: { detail?: unknown } }; message?: string }
  const detail = maybeError?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return maybeError?.message ?? 'Request failed.'
}

function buildSparePayload(edit: InlineSpareEdit | BatchSpareFields): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  if ('part_name' in edit) payload.part_name = edit.part_name ?? ''
  if ('part_number' in edit) payload.part_number = edit.part_number ? edit.part_number : null
  if ('drawing_number' in edit) payload.drawing_number = edit.drawing_number ? edit.drawing_number : null
  if ('drawing_position' in edit) payload.drawing_position = edit.drawing_position ? edit.drawing_position : null
  if ('specification' in edit) payload.specification = edit.specification ? edit.specification : null
  if ('spare_assembly' in edit) payload.spare_assembly = edit.spare_assembly ? edit.spare_assembly : null
  if ('assembly_description' in edit) payload.assembly_description = edit.assembly_description ? edit.assembly_description : null
  if ('spare_maker' in edit) payload.spare_maker = edit.spare_maker ? edit.spare_maker : null
  if ('spare_model' in edit) payload.spare_model = edit.spare_model ? edit.spare_model : null
  if ('component_id' in edit) payload.component_id = edit.component_id ? edit.component_id : null
  if ('qc_status' in edit && edit.qc_status) payload.qc_status = edit.qc_status
  if ('is_critical' in edit) {
    payload.is_critical =
      typeof edit.is_critical === 'string'
        ? edit.is_critical === 'true'
        : Boolean(edit.is_critical)
  }
  return payload
}

interface SpareEditorModalProps {
  title: string
  submitLabel: string
  isPending: boolean
  components: ComponentOption[]
  initialValues?: Partial<Spare>
  onCancel?: () => void
  onSubmit: (payload: Record<string, unknown>) => void
  embedded?: boolean
  openManualInNewTab?: (
    manualId: string | null | undefined,
    name: string | null | undefined,
    pages: string | number | null | undefined
  ) => void
}

function SpareEditorModal({
  title,
  submitLabel,
  isPending,
  components,
  initialValues,
  onCancel,
  onSubmit,
  embedded = false,
  openManualInNewTab,
}: SpareEditorModalProps) {
  const [form, setForm] = useState({
    part_name: initialValues?.part_name ?? '',
    part_number: initialValues?.part_number ?? '',
    drawing_number: initialValues?.drawing_number ?? '',
    drawing_position: initialValues?.drawing_position ?? '',
    specification: initialValues?.specification ?? '',
    spare_assembly: initialValues?.spare_assembly ?? initialValues?.spare_model ?? '',
    assembly_description: initialValues?.assembly_description ?? initialValues?.spare_assembly ?? initialValues?.spare_model ?? '',
    spare_maker: initialValues?.spare_maker ?? '',
    spare_model: initialValues?.spare_model ?? '',
    component_id: initialValues?.component_id ?? '',
    is_critical: Boolean(initialValues?.is_critical),
    qc_status: initialValues?.qc_status ?? 'pending',
  })

  const set = (key: keyof typeof form, value: string | boolean) => setForm((prev) => ({ ...prev, [key]: value }))

  React.useEffect(() => {
    setForm({
      part_name: initialValues?.part_name ?? '',
      part_number: initialValues?.part_number ?? '',
      drawing_number: initialValues?.drawing_number ?? '',
      drawing_position: initialValues?.drawing_position ?? '',
      specification: initialValues?.specification ?? '',
      spare_assembly: initialValues?.spare_assembly ?? initialValues?.spare_model ?? '',
      assembly_description: initialValues?.assembly_description ?? initialValues?.spare_assembly ?? initialValues?.spare_model ?? '',
      spare_maker: initialValues?.spare_maker ?? '',
      spare_model: initialValues?.spare_model ?? '',
      component_id: initialValues?.component_id ?? '',
      is_critical: Boolean(initialValues?.is_critical),
      qc_status: initialValues?.qc_status ?? 'pending',
    })
  }, [initialValues])

  const formBody = (
    <>
      <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
        <h3 className="text-base font-semibold text-white">{title}</h3>
        <div className="flex items-center gap-2">
          {initialValues?.source_manual_id && openManualInNewTab && (
            <button
              onClick={() => {
                openManualInNewTab(
                  initialValues.source_manual_id,
                  initialValues.source_manual_name || initialValues.pdf_reference,
                  initialValues.page_reference
                )
              }}
              type="button"
              className="flex items-center gap-1.5 rounded-lg border border-sky-700 px-3 py-1.5 text-xs text-sky-300 hover:bg-slate-800"
              title="Open manual in a new tab"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              <span>Open PDF</span>
            </button>
          )}
          {onCancel && (
            <button
              onClick={onCancel}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
              title="Close editor"
            >
              <XCircle className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Part Name</label>
            <input value={form.part_name} onChange={(e) => set('part_name', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Part Number</label>
            <input value={form.part_number} onChange={(e) => set('part_number', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Drawing Number</label>
            <input value={form.drawing_number} onChange={(e) => set('drawing_number', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Drawing Position</label>
            <input value={form.drawing_position} onChange={(e) => set('drawing_position', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Spare Maker</label>
            <input value={form.spare_maker} onChange={(e) => set('spare_maker', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Spare Model</label>
            <input value={form.spare_model} onChange={(e) => set('spare_model', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Spare Assembly</label>
            <input value={form.spare_assembly} onChange={(e) => set('spare_assembly', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Assembly Description</label>
            <input value={form.assembly_description} onChange={(e) => set('assembly_description', e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
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
            <label className="mb-1 block text-xs text-slate-400">Criticality</label>
            <select value={form.is_critical ? 'true' : 'false'} onChange={(e) => set('is_critical', e.target.value === 'true')} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none">
              <option value="false">Non-Critical</option>
              <option value="true">Critical</option>
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs text-slate-400">Specification</label>
            <textarea value={form.specification} onChange={(e) => set('specification', e.target.value)} rows={4} className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none" />
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
      <div className="flex items-center justify-end gap-2 border-t border-slate-700 pt-4">
          {onCancel ? <button onClick={onCancel} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button> : null}
          <button
            onClick={() =>
              onSubmit({
                part_name: form.part_name,
                part_number: form.part_number || null,
                drawing_number: form.drawing_number || null,
                drawing_position: form.drawing_position || null,
                specification: form.specification || null,
                spare_assembly: form.spare_assembly || null,
                assembly_description: form.assembly_description || null,
                spare_maker: form.spare_maker || null,
                spare_model: form.spare_model || null,
                component_id: form.component_id || null,
                is_critical: form.is_critical,
                qc_status: form.qc_status,
              })
            }
            disabled={!form.part_name || isPending}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {submitLabel}
          </button>
      </div>
    </>
  )

  if (embedded) {
    return formBody
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="px-6 py-4">{formBody}</div>
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

const METHOD_COLORS: Record<string, string> = {
  table: 'bg-blue-700 text-blue-100',
  text: 'bg-purple-700 text-purple-100',
  drawing: 'bg-amber-700 text-amber-100',
  manual: 'bg-teal-700 text-teal-100',
}

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200]
const SORT_OPTIONS = [
  { value: 'page_order', label: 'Page Order' },
  { value: 'part_name', label: 'Part Name' },
  { value: 'part_number', label: 'Part Number' },
  { value: 'drawing_number', label: 'Drawing #' },
  { value: 'drawing_position', label: 'Drawing Position' },
  { value: 'spare_maker', label: 'Spare Maker' },
  { value: 'component', label: 'Component' },
  { value: 'extraction_method', label: 'Method' },
  { value: 'criticality', label: 'Criticality' },
  { value: 'qc_status', label: 'QC Status' },
  { value: 'page_reference', label: 'Page Reference' },
]

const SparesReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterQC, setFilterQC] = useState('')
  const [filterMethod, setFilterMethod] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [filterSourceFile, setFilterSourceFile] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('page_order')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedSpare, setSelectedSpare] = useState<Spare | null>(null)
  const [editingSpare, setEditingSpare] = useState<Spare | null>(null)
  const [createDraft, setCreateDraft] = useState<Partial<Spare> | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [edits, setEdits] = useState<Record<string, InlineSpareEdit>>({})
  const [showBatchPanel, setShowBatchPanel] = useState(false)
  const [batchFields, setBatchFields] = useState<BatchSpareFields>({})
  const [showSnipModal, setShowSnipModal] = useState(false)

  const openManualInNewTab = (
    manualId: string | null | undefined,
    name: string | null | undefined,
    pages: string | number | null | undefined
  ) => {
    if (!manualId) return
    const pagesStr = pages == null ? '' : String(pages)
    const nameStr = name || ''
    const url = `/vessels/${vesselId}/manual-preview/${manualId}?name=${encodeURIComponent(nameStr)}&pages=${encodeURIComponent(pagesStr)}`
    window.open(url, '_blank')
  }

  const sourceFilesQuery = useQuery({
    queryKey: ['spare-source-files', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/spares/source-files`).then((r) => r.data.items as string[]),
    enabled: !!vesselId,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['spares', vesselId, filterQC, filterMethod, filterCritical, filterSourceFile, search, sortBy, sortOrder, page, pageSize],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterMethod) params.extraction_method = filterMethod
      if (filterCritical) params.is_critical = filterCritical
      if (filterSourceFile) params.pdf_reference = filterSourceFile
      if (search) params.search = search
      params.sort_by = sortBy
      params.sort_order = sortOrder
      params.page = String(page)
      params.page_size = String(pageSize)
      return apiClient.get(`/vessels/${vesselId}/spares`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const componentOptionsQuery = useQuery({
    queryKey: ['spare-components', vesselId],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/components`, { params: { page_size: 5000, is_unmapped: 'false' } })
        .then((r) => r.data),
    enabled: !!vesselId,
  })

  const setEdit = useCallback((id: string, key: keyof InlineSpareEdit, value: string | boolean) => {
    setEdits((prev) => ({
      ...prev,
      [id]: {
        ...(prev[id] ?? {}),
        [key]: value,
      },
    }))
  }, [])

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected spares were accepted.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected spares were rejected.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-delete`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
      setActionError(null)
      setActionMessage('Selected spares were deleted.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const saveSpareMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiClient.patch(`/vessels/${vesselId}/spares/${id}`, payload).then((r) => r.data),
    onSuccess: (spare) => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setEditingSpare(null)
      setSelectedSpare(spare)
      setActionError(null)
      setActionMessage('Spare changes were saved.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const createSpareMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiClient.post(`/vessels/${vesselId}/spares`, payload).then((r) => r.data),
    onSuccess: (spare) => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setCreateDraft(null)
      setEditingSpare(null)
      setSelectedSpare(spare)
      setActionError(null)
      setActionMessage('New spare was created.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const saveInlineEditsMutation = useMutation({
    mutationFn: async (nextEdits: Record<string, InlineSpareEdit>) => {
      const entries = Object.entries(nextEdits).filter(([, value]) => Object.keys(value).length > 0)
      await Promise.all(
        entries.map(([id, value]) =>
          apiClient.patch(`/vessels/${vesselId}/spares/${id}`, buildSparePayload(value))
        )
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setEdits({})
      setActionError(null)
      setActionMessage('Inline spare edits were saved.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const bulkUpdateMutation = useMutation({
    mutationFn: ({ ids, updates }: { ids: string[]; updates: BatchSpareFields }) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-update`, { ids, updates: buildSparePayload(updates) }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
      setShowBatchPanel(false)
      setBatchFields({})
      setActionError(null)
      setActionMessage('Selected spares were updated.')
    },
    onError: (error: unknown) => setActionError(getApiErrorMessage(error)),
  })

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const spares: Spare[] = data?.items ?? []
  const total = data?.total ?? spares.length
  const totalPages = data?.total_pages ?? 1
  const componentOptions: ComponentOption[] = (componentOptionsQuery.data?.items ?? []).filter((component: ComponentOption) => component.qc_status !== 'rejected')

  React.useEffect(() => {
    if (!spares.length) {
      setSelectedSpare(null)
      setEditingSpare(null)
      return
    }

    if (selectedSpare) {
      const refreshed = spares.find((spare) => spare.id === selectedSpare.id)
      if (refreshed) setSelectedSpare(refreshed)
    }

    if (editingSpare) {
      const refreshed = spares.find((spare) => spare.id === editingSpare.id)
      if (refreshed) setEditingSpare(refreshed)
    }
  }, [spares, selectedSpare, editingSpare])

  React.useEffect(() => {
    setPage(1)
  }, [filterQC, filterMethod, filterCritical, filterSourceFile, search, sortBy, sortOrder, pageSize])

  React.useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages)
    }
  }, [page, totalPages])

  const handleQcExport = async () => {
    try {
      const res = await apiClient.get(`/vessels/${vesselId}/spares/qc-export`, { responseType: 'blob' })
      const disposition = res.headers['content-disposition'] ?? ''
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : 'Spares_QC.xlsx'
      const url = URL.createObjectURL(res.data)
      const a = document.createElement('a')
      a.href = url; a.download = filename
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(url)
    } catch { /* silent */ }
  }

  return (
    <>
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Spares Review</h1>
            <p className="mt-1 text-sm text-slate-400">Review extracted spare parts.</p>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 && (
              <>
                <button
                  onClick={() => bulkAcceptMutation.mutate(Array.from(selectedIds))}
                  disabled={bulkAcceptMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-green-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-600 disabled:opacity-50"
                >
                  <CheckCircle className="h-3.5 w-3.5" />
                  Accept ({selectedIds.size})
                </button>
                <button
                  onClick={() => bulkRejectMutation.mutate(Array.from(selectedIds))}
                  disabled={bulkRejectMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-red-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50"
                >
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
                <button
                  onClick={() => {
                    if (window.confirm(`Delete ${selectedIds.size} spare(s)? This cannot be undone.`)) {
                      bulkDeleteMutation.mutate(Array.from(selectedIds))
                    }
                  }}
                  disabled={bulkDeleteMutation.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-rose-900 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-800 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete ({selectedIds.size})
                </button>
              </>
            )}
            <button
              onClick={handleQcExport}
              title="Download Spares QC Review sheet (with Reviewer QC / Notes columns for offline review)"
              className="flex items-center gap-1.5 rounded-lg border border-violet-700 px-3 py-1.5 text-xs font-medium text-violet-300 hover:bg-slate-800"
            >
              <Download className="h-3.5 w-3.5" />
              QC Export
            </button>
            <button
              onClick={() => setShowSnipModal(true)}
              className="flex items-center gap-1.5 rounded-lg border border-sky-700 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-slate-800"
            >
              <Scissors className="h-3.5 w-3.5" />
              Snip &amp; Extract
            </button>
            <button
              onClick={() => { setCreateDraft({ qc_status: 'pending' }); setEditingSpare(null) }}
              className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Spare
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
              <p className="text-sm font-semibold text-violet-300">Batch Update - {selectedIds.size} selected spare(s)</p>
              <button onClick={() => { setShowBatchPanel(false); setBatchFields({}) }} className="text-slate-500 hover:text-white">
                <XCircle className="h-4 w-4" />
              </button>
            </div>
            <p className="text-xs text-slate-400">Fill only the fields you want to update. Empty fields are ignored.</p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
              <input value={batchFields.part_name ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, part_name: e.target.value }))} placeholder="Part name" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.part_number ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, part_number: e.target.value }))} placeholder="Part number" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.drawing_number ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, drawing_number: e.target.value }))} placeholder="Drawing number" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.drawing_position ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, drawing_position: e.target.value }))} placeholder="POS" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <select value={batchFields.component_id ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, component_id: e.target.value }))} className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none">
                <option value="">Component - no change</option>
                <option value="__unmapped__">Unmapped</option>
                {componentOptions.map((component) => (
                  <option key={component.id} value={component.id}>{component.component_name}</option>
                ))}
              </select>
              <input value={batchFields.spare_assembly ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, spare_assembly: e.target.value }))} placeholder="Spare assembly" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.assembly_description ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, assembly_description: e.target.value }))} placeholder="Assembly description" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.spare_maker ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, spare_maker: e.target.value }))} placeholder="Spare maker" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
              <input value={batchFields.spare_model ?? ''} onChange={(e) => setBatchFields((prev) => ({ ...prev, spare_model: e.target.value }))} placeholder="Spare model" className="rounded border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-violet-500 focus:outline-none" />
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
                  const cleaned: BatchSpareFields = { ...batchFields }
                  if (cleaned.component_id === '__unmapped__') cleaned.component_id = ''
                  const hasAny = Object.values(cleaned).some((value) => value !== undefined && value !== '')
                  if (!hasAny) return
                  bulkUpdateMutation.mutate({ ids: Array.from(selectedIds), updates: cleaned })
                }}
                disabled={bulkUpdateMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50"
              >
                <Save className="h-4 w-4" />
                Apply to {selectedIds.size} spare(s)
              </button>
              <button onClick={() => setBatchFields({})} className="text-xs text-slate-500 hover:text-slate-300">
                Clear fields
              </button>
            </div>
          </div>
        ) : null}

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search spares..."
            className="w-52 rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          />
          <select
            value={filterMethod}
            onChange={(e) => setFilterMethod(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Methods</option>
            <option value="table">Table</option>
            <option value="text">Text</option>
            <option value="drawing">Drawing</option>
            <option value="manual">Manual (Snip)</option>
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
          <div className="w-56">
            <SearchableSelect
              options={sourceFilesQuery.data ?? []}
              value={filterSourceFile}
              onChange={setFilterSourceFile}
              placeholder="All Source Files"
              allowCustom
            />
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                Sort: {option.label}
              </option>
            ))}
          </select>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as 'asc' | 'desc')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
          {(filterQC || filterMethod || filterCritical || filterSourceFile || search || sortBy !== 'page_order' || sortOrder !== 'asc') && (
            <button
              onClick={() => {
                setFilterQC('')
                setFilterMethod('')
                setFilterCritical('')
                setFilterSourceFile('')
                setSearch('')
                setSortBy('part_name')
                setSortOrder('asc')
              }}
              className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              Clear
            </button>
          )}
        </div>

        <div className="overflow-auto max-h-[65vh] rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading...</div>
          ) : spares.length === 0 ? (
            <div className="py-16 text-center text-slate-500">
              No spares found yet. Extract from Manual Review after component matching is complete.
            </div>
          ) : (
            <table className="min-w-[2380px] w-full text-sm">
              <thead>
                <tr className="sticky top-0 z-10 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase">
                  <th className="px-4 py-3 w-8">
                    <input
                      type="checkbox"
                      onChange={(e) =>
                        e.target.checked
                          ? setSelectedIds(new Set(spares.map((s) => s.id)))
                          : setSelectedIds(new Set())
                      }
                      checked={selectedIds.size === spares.length && spares.length > 0}
                      className="h-3.5 w-3.5 rounded"
                    />
                  </th>
                  <th className="px-4 py-3">Part Name</th>
                  <th className="px-4 py-3">Part #</th>
                  <th className="px-4 py-3">Drawing #</th>
                  <th className="px-4 py-3">Pos</th>
                  <th className="px-4 py-3">Maker</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Specification / Particulars</th>
                  <th className="px-4 py-3">Assembly</th>
                  <th className="px-4 py-3">Assembly Description</th>
                  <th className="px-4 py-3">Component</th>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Method</th>
                  <th className="px-4 py-3">Critical</th>
                  <th className="px-4 py-3">Conf</th>
                  <th className="px-4 py-3">QC</th>
                  <th className="px-4 py-3">View</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {spares.map((spare) => (
                  <tr
                    key={spare.id}
                    onClick={() => {
                      toggleSelect(spare.id)
                      setSelectedSpare(spare)
                    }}
                    onDoubleClick={() => {
                      setSelectedSpare(spare)
                      setEditingSpare(spare)
                      setCreateDraft(null)
                    }}
                    className={`cursor-pointer hover:bg-slate-800/50 transition-colors ${
                      selectedIds.has(spare.id) ? 'bg-sky-900/10' : ''
                    } ${selectedSpare?.id === spare.id ? 'bg-slate-800' : ''}`}
                  >
                    <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(spare.id)}
                        onChange={() => toggleSelect(spare.id)}
                        className="h-3.5 w-3.5 rounded"
                      />
                    </td>
                    <td className="px-4 py-2.5 text-slate-200 font-medium">
                      <input
                        value={edits[spare.id]?.part_name ?? spare.part_name}
                        onChange={(e) => setEdit(spare.id, 'part_name', e.target.value)}
                        className="w-[260px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-100 focus:border-sky-500 focus:outline-none"
                        title={spare.part_name}
                      />
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap font-mono text-xs text-slate-400">
                      <input
                        value={edits[spare.id]?.part_number ?? (spare.part_number ?? '')}
                        onChange={(e) => setEdit(spare.id, 'part_number', e.target.value)}
                        className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap font-mono text-xs text-slate-400">
                      <input
                        value={edits[spare.id]?.drawing_number ?? (spare.drawing_number ?? '')}
                        onChange={(e) => setEdit(spare.id, 'drawing_number', e.target.value)}
                        className="w-28 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-slate-400">
                      <input
                        value={edits[spare.id]?.drawing_position ?? (spare.drawing_position ?? '')}
                        onChange={(e) => setEdit(spare.id, 'drawing_position', e.target.value)}
                        className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        value={edits[spare.id]?.spare_maker ?? (spare.spare_maker ?? '')}
                        onChange={(e) => setEdit(spare.id, 'spare_maker', e.target.value)}
                        className="w-40 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        title={spare.spare_maker ?? ''}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        value={edits[spare.id]?.spare_model ?? (spare.spare_model ?? '')}
                        onChange={(e) => setEdit(spare.id, 'spare_model', e.target.value)}
                        className="w-[180px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        title={spare.spare_model ?? ''}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <textarea
                        value={edits[spare.id]?.specification ?? (spare.specification ?? '')}
                        onChange={(e) => setEdit(spare.id, 'specification', e.target.value)}
                        rows={2}
                        className="w-[280px] resize-y rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        title={spare.specification ?? ''}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        value={edits[spare.id]?.spare_assembly ?? (spare.spare_assembly ?? spare.spare_model ?? '')}
                        onChange={(e) => setEdit(spare.id, 'spare_assembly', e.target.value)}
                        className="w-[240px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        title={spare.spare_assembly ?? spare.spare_model ?? ''}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        value={edits[spare.id]?.assembly_description ?? (spare.assembly_description ?? spare.spare_assembly ?? spare.spare_model ?? '')}
                        onChange={(e) => setEdit(spare.id, 'assembly_description', e.target.value)}
                        className="w-[260px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                        title={spare.assembly_description ?? spare.spare_assembly ?? spare.spare_model ?? ''}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={edits[spare.id]?.component_id ?? (spare.component_id ?? '')}
                        onChange={(e) => setEdit(spare.id, 'component_id', e.target.value)}
                        className="w-[220px] rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="">Unmapped</option>
                        {componentOptions.map((component) => (
                          <option key={component.id} value={component.id}>{component.component_name}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.page_reference != null ? (
                        <div className="min-w-[240px] text-xs">
                          <button
                            onClick={() => {
                              setSelectedSpare(spare)
                              openManualInNewTab(spare.source_manual_id, spare.pdf_reference ?? spare.source_manual_name, spare.page_reference)
                            }}
                            disabled={!spare.source_manual_id}
                            className="inline-flex items-center gap-1 whitespace-nowrap text-sky-400 hover:underline disabled:opacity-40 disabled:no-underline"
                            title={spare.source_reference ?? `${spare.pdf_reference ?? spare.source_manual_name ?? 'Manual'} - page ${spare.page_reference}`}
                          >
                            <ExternalLink className="h-3 w-3" />
                            p.{spare.page_reference}
                          </button>
                          <p className="mt-1 truncate whitespace-nowrap text-slate-500" title={spare.pdf_reference ?? spare.source_manual_name ?? 'Manual'}>
                            {spare.pdf_reference ?? spare.source_manual_name ?? 'Manual'}
                          </p>
                          {spare.source_reference ? (
                            <p className="mt-1 truncate whitespace-nowrap text-slate-600" title={spare.source_reference}>
                              {spare.source_reference}
                            </p>
                          ) : null}
                        </div>
                      ) : <span className="text-slate-600">-</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                          METHOD_COLORS[spare.extraction_method] ?? 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {spare.extraction_method}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={String(edits[spare.id]?.is_critical ?? spare.is_critical)}
                        onChange={(e) => setEdit(spare.id, 'is_critical', e.target.value === 'true')}
                        className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="false">Non-Critical</option>
                        <option value="true">Critical</option>
                      </select>
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.confidence_score != null ? (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            spare.confidence_score >= 85
                              ? 'bg-green-700 text-green-100'
                              : spare.confidence_score >= 60
                              ? 'bg-amber-700 text-amber-100'
                              : 'bg-red-700 text-red-100'
                          }`}
                        >
                          {spare.confidence_score}%
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={edits[spare.id]?.qc_status ?? spare.qc_status}
                        onChange={(e) => setEdit(spare.id, 'qc_status', e.target.value)}
                        className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                      >
                        <option value="pending">Pending</option>
                        <option value="accepted">Accepted</option>
                        <option value="modified">Modified</option>
                        <option value="rejected">Rejected</option>
                      </select>
                    </td>
                    <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => {
                          setSelectedSpare(spare)
                          openManualInNewTab(spare.source_manual_id, spare.pdf_reference ?? spare.source_manual_name, spare.page_reference)
                        }}
                        disabled={!spare.source_manual_id}
                        className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
                        title="Preview manual pages"
                      >
                        <FileSearch className="h-3 w-3" />
                      </button>
                    </td>
                    <td className="px-4 py-2.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => {
                          setSelectedSpare(spare)
                          setEditingSpare(spare)
                        }}
                        className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600"
                        title="Edit spare"
                      >
                        <Pencil className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900 px-4 py-2.5 shrink-0">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>{total} total</span>
            <span>·</span>
            <span>Show</span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-white text-xs"
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            <span>per page</span>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page === 1}
              className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40"
            >
              ← Prev
            </button>
            <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
            <button
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages}
              className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600 disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      </div>

      {/* Scroll Modal overlay for Spare Editor */}
      {(editingSpare || createDraft) && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm p-4 flex justify-center items-start">
          <div className="relative w-full max-w-4xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl my-8">
            {editingSpare ? (
              <SpareEditorModal
                title="Edit Spare"
                submitLabel="Save Changes"
                isPending={saveSpareMutation.isPending}
                components={componentOptions}
                initialValues={editingSpare}
                embedded={true}
                onCancel={() => setEditingSpare(null)}
                onSubmit={(payload) => saveSpareMutation.mutate({ id: editingSpare.id, payload })}
                openManualInNewTab={openManualInNewTab}
              />
            ) : (
              <SpareEditorModal
                title="Add Spare"
                submitLabel="Create Spare"
                isPending={createSpareMutation.isPending}
                components={componentOptions}
                initialValues={createDraft!}
                embedded={true}
                onCancel={() => setCreateDraft(null)}
                onSubmit={(payload) => createSpareMutation.mutate(payload)}
                openManualInNewTab={openManualInNewTab}
              />
            )}
          </div>
        </div>
      )}

      {showSnipModal && vesselId && (
        <SnipExtractModal
          vesselId={vesselId}
          onClose={() => setShowSnipModal(false)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
            queryClient.invalidateQueries({ queryKey: ['spare-source-files', vesselId] })
          }}
        />
      )}
    </>
  )
}

export default SparesReview
