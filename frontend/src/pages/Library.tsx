import React, { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Upload,
  Plus,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Layers,
  BookOpen,
  GitMerge,
  RefreshCw,
} from 'lucide-react'
import apiClient from '@/api/client'

// ─── Interfaces ───────────────────────────────────────────────────────────────

interface ComponentStructureNode {
  id: string
  group1_code: string
  group1_name: string
  group2_code: string
  group2_name: string
  machinery_code: string
  machinery_name: string
  component_code?: string
  component_name?: string
  component_type?: string
  is_critical: boolean
  status: 'active' | 'pending_approval'
}

interface ApprovalRequest {
  id: string
  node: ComponentStructureNode
  requested_by: string
  requested_at: string
  reason?: string
}

interface GlobalLibraryEntry {
  id: string
  canonical_data: Record<string, unknown>
  occurrence_count: number
  source_vessels: string[]
  first_seen_at: string
}

interface ImportResult {
  imported: number
  version: string
}

interface PopulateResult {
  added: number
  duplicates: number
}

interface AddNodeForm {
  group1_code: string
  group1_name: string
  group2_code: string
  group2_name: string
  machinery_code: string
  machinery_name: string
  component_code: string
  component_name: string
  component_type: string
  is_critical: boolean
}

const EMPTY_NODE_FORM: AddNodeForm = {
  group1_code: '',
  group1_name: '',
  group2_code: '',
  group2_name: '',
  machinery_code: '',
  machinery_name: '',
  component_code: '',
  component_name: '',
  component_type: '',
  is_critical: false,
}

type MainTab = 'structure' | 'global' | 'matches'
type GlobalEntity = 'component' | 'job' | 'spare'

// ─── Component Structure Tab ──────────────────────────────────────────────────

const ComponentStructureTab: React.FC = () => {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [addForm, setAddForm] = useState<AddNodeForm>(EMPTY_NODE_FORM)
  const [addSuccess, setAddSuccess] = useState(false)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const { data: nodes = [], isLoading } = useQuery<ComponentStructureNode[]>({
    queryKey: ['library', 'component-structure'],
    queryFn: async () => {
      const res = await apiClient.get('/library/component-structure')
      return res.data
    },
  })

  const pendingNodes = nodes.filter((n) => n.status === 'pending_approval')

  const { data: approvalRequests = [] } = useQuery<ApprovalRequest[]>({
    queryKey: ['library', 'component-structure', 'approval-requests'],
    queryFn: async () => {
      const res = await apiClient.get('/library/component-structure/approval-requests')
      return res.data
    },
    enabled: pendingNodes.length > 0,
  })

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post('/library/component-structure/import', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data as ImportResult
    },
    onSuccess: (data) => {
      setImportResult(data)
      setImportError(null)
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] })
    },
    onError: () => {
      setImportError('Import failed. Please check the file format and try again.')
    },
  })

  const addNodeMutation = useMutation({
    mutationFn: async (payload: AddNodeForm) => {
      const res = await apiClient.post('/library/component-structure/nodes', payload)
      return res.data
    },
    onSuccess: () => {
      setAddSuccess(true)
      setAddForm(EMPTY_NODE_FORM)
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] })
      setTimeout(() => {
        setAddSuccess(false)
        setShowAddModal(false)
      }, 2000)
    },
  })

  const approveMutation = useMutation({
    mutationFn: async (requestId: string) => {
      await apiClient.post(`/library/component-structure/approval-requests/${requestId}/approve`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] })
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure', 'approval-requests'] })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: async ({ requestId, reason }: { requestId: string; reason: string }) => {
      await apiClient.post(`/library/component-structure/approval-requests/${requestId}/reject`, { reason })
    },
    onSuccess: () => {
      setRejectingId(null)
      setRejectReason('')
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] })
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure', 'approval-requests'] })
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      importMutation.mutate(file)
      e.target.value = ''
    }
  }

  const handleAddFormChange = (field: keyof AddNodeForm, value: string | boolean) => {
    setAddForm((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white">Component Structure Library</h2>
          <p className="text-sm text-slate-400 mt-1">Organisation-wide shared component hierarchy</p>
        </div>
        <div className="flex gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.csv"
            className="hidden"
            onChange={handleFileChange}
          />
          <div className="flex flex-col items-end gap-1">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={importMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              {importMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              Import Excel
            </button>
            <p className="text-xs text-slate-500">
              Columns: <span className="text-slate-400">ShipComponentName | HierarchyComponentCode | ShipComponentCode | ComponentType | Priority | Status | Quantity | Category</span>
            </p>
          </div>
          <button
            onClick={() => { setShowAddModal(true); setAddSuccess(false) }}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Node
          </button>
        </div>
      </div>

      {/* Import result banner */}
      {importResult && (
        <div className="flex items-center gap-3 p-4 bg-emerald-900/40 border border-emerald-600/50 rounded-lg">
          <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span className="text-emerald-300">
            Successfully imported <strong>{importResult.imported}</strong> nodes (version {importResult.version})
          </span>
          <button onClick={() => setImportResult(null)} className="ml-auto text-emerald-400 hover:text-emerald-300">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}
      {importError && (
        <div className="flex items-center gap-3 p-4 bg-red-900/40 border border-red-600/50 rounded-lg">
          <XCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-300">{importError}</span>
          <button onClick={() => setImportError(null)} className="ml-auto text-red-400 hover:text-red-300">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Tree Table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-900/50">
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Hierarchy Code</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Category</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Component Type</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Component Code</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Component Name</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Type</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Critical</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />
                    Loading component structure...
                  </td>
                </tr>
              ) : nodes.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    No nodes found. Import an Excel file or add a node manually.
                  </td>
                </tr>
              ) : (
                nodes.map((node) => (
                  <tr key={node.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                    <td className="px-4 py-3 text-slate-300 font-mono text-xs">{node.machinery_code || node.group1_code}</td>
                    <td className="px-4 py-3 text-slate-200">{node.group1_name}</td>
                    <td className="px-4 py-3 text-slate-300">{node.group2_name}</td>
                    <td className="px-4 py-3 text-slate-300 font-mono text-xs">{node.component_code || '—'}</td>
                    <td className="px-4 py-3 text-slate-400">{node.component_name || '—'}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs">{node.component_type || '—'}</td>
                    <td className="px-4 py-3">
                      {node.is_critical ? (
                        <span className="text-amber-400 text-xs font-medium">Critical</span>
                      ) : (
                        <span className="text-slate-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {node.status === 'active' ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-900/40 text-emerald-400 text-xs rounded-full border border-emerald-600/40">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-900/40 text-amber-400 text-xs rounded-full border border-amber-600/40">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                          Pending
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Approval Requests */}
      {approvalRequests.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            Approval Requests ({approvalRequests.length})
          </h3>
          <div className="space-y-3">
            {approvalRequests.map((req) => (
              <div key={req.id} className="bg-slate-800 border border-amber-600/30 rounded-xl p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1 text-sm">
                    <p className="text-white font-medium">
                      {req.node.group1_name} / {req.node.group2_name} / {req.node.machinery_name}
                      {req.node.component_name ? ` / ${req.node.component_name}` : ''}
                    </p>
                    <p className="text-slate-400">
                      Requested by <span className="text-slate-300">{req.requested_by}</span> ·{' '}
                      {new Date(req.requested_at).toLocaleDateString()}
                    </p>
                    {req.reason && <p className="text-slate-400 italic">"{req.reason}"</p>}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {rejectingId === req.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          placeholder="Reason for rejection..."
                          className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-sm text-white placeholder-slate-500 w-48 focus:outline-none focus:border-sky-500"
                        />
                        <button
                          onClick={() => rejectMutation.mutate({ requestId: req.id, reason: rejectReason })}
                          disabled={rejectMutation.isPending}
                          className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => { setRejectingId(null); setRejectReason('') }}
                          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-lg transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => approveMutation.mutate(req.id)}
                          disabled={approveMutation.isPending}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                        >
                          <CheckCircle className="w-4 h-4" />
                          Approve
                        </button>
                        <button
                          onClick={() => setRejectingId(req.id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-900/50 hover:bg-red-800 text-red-300 text-sm rounded-lg border border-red-700/50 transition-colors"
                        >
                          <XCircle className="w-4 h-4" />
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Node Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-white">Add Component Structure Node</h3>
              <button
                onClick={() => { setShowAddModal(false); setAddSuccess(false); setAddForm(EMPTY_NODE_FORM) }}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {addSuccess ? (
              <div className="flex flex-col items-center gap-3 py-8">
                <CheckCircle className="w-12 h-12 text-emerald-400" />
                <p className="text-emerald-300 font-medium">Submitted for approval</p>
                <p className="text-slate-400 text-sm">The node will appear once approved by an administrator.</p>
              </div>
            ) : (
              <form
                onSubmit={(e) => { e.preventDefault(); addNodeMutation.mutate(addForm) }}
                className="space-y-4"
              >
                <div className="grid grid-cols-2 gap-4">
                  {(
                    [
                      ['group1_code', 'Group 1 Code', true],
                      ['group1_name', 'Group 1 Name', true],
                      ['group2_code', 'Group 2 Code', true],
                      ['group2_name', 'Group 2 Name', true],
                      ['machinery_code', 'Machinery Code', true],
                      ['machinery_name', 'Machinery Name', true],
                      ['component_code', 'Component Code', false],
                      ['component_name', 'Component Name', false],
                      ['component_type', 'Component Type', false],
                    ] as [keyof AddNodeForm, string, boolean][]
                  ).map(([field, label, required]) => (
                    <div key={field} className={field === 'component_type' ? 'col-span-2' : ''}>
                      <label className="block text-sm font-medium text-slate-400 mb-1">
                        {label} {required && <span className="text-red-400">*</span>}
                      </label>
                      <input
                        type="text"
                        value={addForm[field] as string}
                        onChange={(e) => handleAddFormChange(field, e.target.value)}
                        required={required}
                        className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm"
                      />
                    </div>
                  ))}
                </div>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={addForm.is_critical}
                    onChange={(e) => handleAddFormChange('is_critical', e.target.checked)}
                    className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-sky-600 focus:ring-sky-500"
                  />
                  <span className="text-sm text-slate-300">Mark as Critical</span>
                </label>
                <div className="flex gap-3 pt-2">
                  <button
                    type="submit"
                    disabled={addNodeMutation.isPending}
                    className="flex items-center gap-2 px-5 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50"
                  >
                    {addNodeMutation.isPending && <RefreshCw className="w-4 h-4 animate-spin" />}
                    Submit for Approval
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowAddModal(false); setAddForm(EMPTY_NODE_FORM) }}
                    className="px-5 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Global Libraries Tab ─────────────────────────────────────────────────────

const GLOBAL_ENTITY_LABELS: Record<GlobalEntity, string> = {
  component: 'Components',
  job: 'Jobs',
  spare: 'Spares',
}

const GlobalLibrariesTab: React.FC = () => {
  const [activeEntity, setActiveEntity] = useState<GlobalEntity>('component')
  const [populateVesselId, setPopulateVesselId] = useState('')
  const [populateResult, setPopulateResult] = useState<PopulateResult | null>(null)
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

  const { data: entries = [], isLoading } = useQuery<GlobalLibraryEntry[]>({
    queryKey: ['library', 'global', activeEntity],
    queryFn: async () => {
      const res = await apiClient.get(`/library/global/${activeEntity}`)
      return res.data
    },
  })

  const populateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/library/global/${activeEntity}/populate`, {
        vessel_id: populateVesselId,
      })
      return res.data as PopulateResult
    },
    onSuccess: (data) => {
      setPopulateResult(data)
    },
  })

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-6">
      {/* Sub-tabs */}
      <div className="flex gap-1 bg-slate-900/50 p-1 rounded-lg w-fit">
        {(Object.keys(GLOBAL_ENTITY_LABELS) as GlobalEntity[]).map((entity) => (
          <button
            key={entity}
            onClick={() => { setActiveEntity(entity); setPopulateResult(null) }}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeEntity === entity
                ? 'bg-sky-600 text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            {GLOBAL_ENTITY_LABELS[entity]}
          </button>
        ))}
      </div>

      {/* Populate from Vessel */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-slate-300 mb-3">Populate from Vessel</h3>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={populateVesselId}
            onChange={(e) => setPopulateVesselId(e.target.value)}
            placeholder="Enter Vessel ID..."
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 text-sm w-60"
          />
          <button
            onClick={() => { setPopulateResult(null); populateMutation.mutate() }}
            disabled={!populateVesselId.trim() || populateMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50 text-sm"
          >
            {populateMutation.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Populate
          </button>
          {populateResult && (
            <div className="flex items-center gap-4 text-sm">
              <span className="text-emerald-400">
                <strong>{populateResult.added}</strong> added
              </span>
              <span className="text-slate-400">
                <strong>{populateResult.duplicates}</strong> duplicates skipped
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 bg-slate-900/50">
                <th className="text-left px-4 py-3 text-slate-400 font-medium w-8" />
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Canonical Data</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Occurrences</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">Source Vessels</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">First Seen</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />
                    Loading {GLOBAL_ENTITY_LABELS[activeEntity].toLowerCase()}...
                  </td>
                </tr>
              ) : entries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                    No {GLOBAL_ENTITY_LABELS[activeEntity].toLowerCase()} found in global library.
                  </td>
                </tr>
              ) : (
                entries.map((entry) => {
                  const isExpanded = expandedRows.has(entry.id)
                  const dataKeys = Object.keys(entry.canonical_data)
                  const previewKey = dataKeys[0]
                  const previewValue = previewKey ? String(entry.canonical_data[previewKey]) : ''

                  return (
                    <React.Fragment key={entry.id}>
                      <tr className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                        <td className="px-4 py-3">
                          <button
                            onClick={() => toggleRow(entry.id)}
                            className="text-slate-500 hover:text-slate-300 transition-colors"
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          </button>
                        </td>
                        <td className="px-4 py-3">
                          {isExpanded ? (
                            <div className="space-y-1">
                              {dataKeys.map((key) => (
                                <div key={key} className="flex gap-2 text-xs">
                                  <span className="text-slate-500 font-medium w-32 flex-shrink-0">{key}:</span>
                                  <span className="text-slate-300">{String(entry.canonical_data[key])}</span>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-300">
                              {previewKey && (
                                <>
                                  <span className="text-slate-500 text-xs">{previewKey}: </span>
                                  <span className="text-slate-200">{previewValue.slice(0, 80)}{previewValue.length > 80 ? '…' : ''}</span>
                                </>
                              )}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center px-2 py-0.5 bg-sky-900/40 text-sky-400 text-xs rounded-full border border-sky-600/40">
                            {entry.occurrence_count}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-xs">{entry.source_vessels.length} vessels</td>
                        <td className="px-4 py-3 text-slate-400 text-xs">
                          {new Date(entry.first_seen_at).toLocaleDateString()}
                        </td>
                      </tr>
                    </React.Fragment>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─── Manual Matches Tab ───────────────────────────────────────────────────────

const ManualMatchesTab: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center py-20 space-y-4">
      <GitMerge className="w-16 h-16 text-slate-600" />
      <h3 className="text-lg font-semibold text-slate-400">No Vessel Context</h3>
      <p className="text-slate-500 text-center max-w-md">
        Select a vessel from the <strong className="text-slate-400">Manuals</strong> page to view
        cross-project manual matches and similarity scores for that vessel's documents.
      </p>
    </div>
  )
}

// ─── Main Library Page ────────────────────────────────────────────────────────

const TAB_CONFIG: { key: MainTab; label: string; icon: React.ReactNode }[] = [
  { key: 'structure', label: 'Component Structure', icon: <Layers className="w-4 h-4" /> },
  { key: 'global', label: 'Global Libraries', icon: <BookOpen className="w-4 h-4" /> },
  { key: 'matches', label: 'Manual Matches', icon: <GitMerge className="w-4 h-4" /> },
]

const Library: React.FC = () => {
  const [activeTab, setActiveTab] = useState<MainTab>('structure')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Library Management</h1>
        <p className="text-slate-400 mt-1">
          Manage component structure hierarchy, global libraries, and manual cross-project matches
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 border-b border-slate-700">
        {TAB_CONFIG.map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeTab === key
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-white hover:border-slate-500'
            }`}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'structure' && <ComponentStructureTab />}
        {activeTab === 'global' && <GlobalLibrariesTab />}
        {activeTab === 'matches' && <ManualMatchesTab />}
      </div>
    </div>
  )
}

export default Library
