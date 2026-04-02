import React, { useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle, FileSearch, ExternalLink, Plus, Pencil } from 'lucide-react'
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

interface Spare {
  id: string
  part_name: string
  part_number: string | null
  drawing_number: string | null
  drawing_position: string | null
  specification: string | null
  spare_maker: string | null
  spare_model?: string | null
  component_id: string | null
  component_name?: string | null
  component_maker?: string | null
  component_model?: string | null
  source_manual_id: string | null
  source_manual_name?: string | null
  pdf_reference?: string | null
  page_reference: number | null
  extraction_method: string
  is_critical: boolean
  confidence_score: number | null
  qc_status: string
  is_duplicate: boolean
}

interface SpareEditorModalProps {
  title: string
  submitLabel: string
  isPending: boolean
  components: ComponentOption[]
  initialValues?: Partial<Spare>
  onClose: () => void
  onSubmit: (payload: Record<string, unknown>) => void
}

function SpareEditorModal({ title, submitLabel, isPending, components, initialValues, onClose, onSubmit }: SpareEditorModalProps) {
  const [form, setForm] = useState({
    part_name: initialValues?.part_name ?? '',
    part_number: initialValues?.part_number ?? '',
    drawing_number: initialValues?.drawing_number ?? '',
    drawing_position: initialValues?.drawing_position ?? '',
    specification: initialValues?.specification ?? '',
    spare_maker: initialValues?.spare_maker ?? '',
    spare_model: initialValues?.spare_model ?? '',
    component_id: initialValues?.component_id ?? '',
    is_critical: Boolean(initialValues?.is_critical),
    qc_status: initialValues?.qc_status ?? 'pending',
  })

  const set = (key: keyof typeof form, value: string | boolean) => setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><XCircle className="h-5 w-5" /></button>
        </div>
        <div className="grid gap-4 px-6 py-4 md:grid-cols-2">
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
          <div className="flex items-center gap-2 pt-6">
            <input id="spare-critical" type="checkbox" checked={form.is_critical} onChange={(e) => set('is_critical', e.target.checked)} className="h-4 w-4 rounded" />
            <label htmlFor="spare-critical" className="text-sm text-slate-300">Critical spare</label>
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
        <div className="flex items-center justify-end gap-2 border-t border-slate-700 px-6 py-4">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
          <button
            onClick={() =>
              onSubmit({
                part_name: form.part_name,
                part_number: form.part_number || null,
                drawing_number: form.drawing_number || null,
                drawing_position: form.drawing_position || null,
                specification: form.specification || null,
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
}

const SparesReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [filterQC, setFilterQC] = useState('')
  const [filterMethod, setFilterMethod] = useState('')
  const [filterCritical, setFilterCritical] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectedSpare, setSelectedSpare] = useState<Spare | null>(null)
  const [editingSpare, setEditingSpare] = useState<Spare | null>(null)
  const [showCreateSpare, setShowCreateSpare] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['spares', vesselId, filterQC, filterMethod, filterCritical],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (filterQC) params.qc_status = filterQC
      if (filterMethod) params.extraction_method = filterMethod
      if (filterCritical) params.is_critical = filterCritical
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

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/spares/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setSelectedIds(new Set())
    },
  })

  const saveSpareMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      apiClient.patch(`/vessels/${vesselId}/spares/${id}`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setEditingSpare(null)
    },
  })

  const createSpareMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => apiClient.post(`/vessels/${vesselId}/spares`, payload).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['spares', vesselId] })
      setShowCreateSpare(false)
    },
  })

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const spares: Spare[] = data?.items ?? []
  const componentOptions: ComponentOption[] = (componentOptionsQuery.data?.items ?? []).filter((component: ComponentOption) => component.qc_status !== 'rejected')

  return (
    <div className="flex h-full gap-4">
      {showCreateSpare && (
        <SpareEditorModal
          title="Add Spare"
          submitLabel="Create Spare"
          isPending={createSpareMutation.isPending}
          components={componentOptions}
          onClose={() => setShowCreateSpare(false)}
          onSubmit={(payload) => createSpareMutation.mutate(payload)}
        />
      )}
      {editingSpare && (
        <SpareEditorModal
          title="Edit Spare"
          submitLabel="Save Changes"
          isPending={saveSpareMutation.isPending}
          components={componentOptions}
          initialValues={editingSpare}
          onClose={() => setEditingSpare(null)}
          onSubmit={(payload) => saveSpareMutation.mutate({ id: editingSpare.id, payload })}
        />
      )}
      {/* Left: Spare Grid */}
      <div className="flex flex-1 flex-col gap-4 overflow-hidden">
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
            <button
              onClick={() => setShowCreateSpare(true)}
              className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Spare
            </button>
          </div>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filterMethod}
            onChange={(e) => setFilterMethod(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-2 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            <option value="">All Methods</option>
            <option value="table">Table</option>
            <option value="text">Text</option>
            <option value="drawing">Drawing</option>
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
          {(filterQC || filterMethod || filterCritical) && (
            <button
              onClick={() => { setFilterQC(''); setFilterMethod(''); setFilterCritical('') }}
              className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              Clear filters
            </button>
          )}
        </div>

        <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-900">
          {isLoading ? (
            <div className="py-16 text-center text-slate-500">Loading...</div>
          ) : spares.length === 0 ? (
            <div className="py-16 text-center text-slate-500">
              No spares found yet. Extract from Manual Review after component matching is complete.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase">
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
                    className={`hover:bg-slate-800/50 transition-colors ${
                      selectedIds.has(spare.id) ? 'bg-sky-900/10' : ''
                    } ${selectedSpare?.id === spare.id ? 'bg-slate-800' : ''}`}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(spare.id)}
                        onChange={() => toggleSelect(spare.id)}
                        className="h-3.5 w-3.5 rounded"
                      />
                    </td>
                    <td className="px-4 py-2.5 text-slate-200 font-medium">{spare.part_name}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-400">
                      {spare.part_number ?? '-'}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-400">
                      {spare.drawing_number ?? '-'}
                    </td>
                    <td className="px-4 py-2.5 text-slate-400">{spare.drawing_position ?? '-'}</td>
                    <td className="px-4 py-2.5 text-slate-300">{spare.spare_maker ?? '-'}</td>
                    <td className="px-4 py-2.5">
                      {spare.component_name ? (
                        <div className="min-w-[180px]">
                          <p className="text-slate-200">{spare.component_name}</p>
                          <p className="text-xs text-slate-500">
                            {[spare.component_maker, spare.component_model].filter(Boolean).join(' - ') || 'Linked'}
                          </p>
                        </div>
                      ) : (
                        <span className="rounded-full bg-amber-900/40 px-2 py-0.5 text-xs text-amber-300">Unmapped</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      {spare.page_reference != null ? (
                        <div className="min-w-[170px] text-xs">
                          <div className="inline-flex items-center gap-1 text-sky-400" title={`${spare.pdf_reference ?? spare.source_manual_name ?? 'Manual'} - page ${spare.page_reference}`}>
                            <ExternalLink className="h-3 w-3" />
                            p.{spare.page_reference}
                          </div>
                          <p className="mt-1 truncate text-slate-500">{spare.source_manual_name ?? spare.pdf_reference ?? 'Manual'}</p>
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
                      {spare.is_critical ? (
                        <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">
                          Critical
                        </span>
                      ) : (
                        <span className="text-slate-600">-</span>
                      )}
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
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          QC_COLORS[spare.qc_status] ?? 'bg-slate-700 text-slate-300'
                        }`}
                      >
                        {spare.qc_status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => setSelectedSpare(spare)}
                        className="rounded bg-slate-700 p-1.5 text-slate-300 hover:bg-slate-600"
                        title="Preview manual pages"
                      >
                        <FileSearch className="h-3 w-3" />
                      </button>
                    </td>
                    <td className="px-4 py-2.5">
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
      </div>

      <ManualPagePreview
        vesselId={vesselId ?? ''}
        manualId={selectedSpare?.source_manual_id}
        manualName={selectedSpare?.source_manual_name ?? selectedSpare?.pdf_reference}
        title="Spare Source Preview"
        subtitle={
          selectedSpare
            ? [
                selectedSpare.part_name,
                selectedSpare.part_number,
                selectedSpare.component_name,
                selectedSpare.component_maker,
                selectedSpare.component_model,
              ]
                .filter(Boolean)
                .join(' • ')
            : null
        }
        defaultPages={selectedSpare?.page_reference}
      />
    </div>
  )
}

export default SparesReview
