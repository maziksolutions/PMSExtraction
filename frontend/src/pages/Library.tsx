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
  FileDown,
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

const PAGE_SIZE_OPTIONS = [100, 200, 500, 1000]

const ComponentStructureTab: React.FC = () => {
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [selectedVesselTypeId, setSelectedVesselTypeId] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(100)
  const [showAddTypeModal, setShowAddTypeModal] = useState(false)
  const [newTypeName, setNewTypeName] = useState('')
  const [addTypeError, setAddTypeError] = useState('')

  // Vessel types list
  const { data: vtData, isLoading: vtLoading } = useQuery({
    queryKey: ['library', 'vessel-types'],
    queryFn: async () => {
      const res = await apiClient.get('/library/vessel-types')
      return res.data
    },
  })
  const vesselTypes: { id: string; name: string; is_system: boolean; component_count: number }[] = vtData?.items ?? []

  // Auto-select first vessel type
  React.useEffect(() => {
    if (!selectedVesselTypeId && vesselTypes.length > 0) {
      setSelectedVesselTypeId(vesselTypes[0].id)
    }
  }, [vesselTypes])

  // Components for selected vessel type
  const { data: pageData, isLoading } = useQuery({
    queryKey: ['library', 'component-structure', selectedVesselTypeId, page, pageSize],
    queryFn: async () => {
      if (!selectedVesselTypeId) return { items: [], total: 0 }
      const res = await apiClient.get('/library/component-structure', {
        params: { vessel_type_id: selectedVesselTypeId, page, page_size: pageSize },
      })
      return res.data
    },
    enabled: !!selectedVesselTypeId,
  })
  const nodes: ComponentStructureNode[] = pageData?.items ?? []
  const total: number = pageData?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post(
        `/library/component-structure/import?vessel_type_id=${selectedVesselTypeId ?? ''}`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return res.data as ImportResult
    },
    onSuccess: (data) => {
      setImportResult(data)
      setImportError(null)
      queryClient.invalidateQueries({ queryKey: ['library', 'component-structure'] }); setPage(1)
      queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Unknown error'
      setImportError(`Import failed: ${detail}`)
    },
  })

  const createVesselTypeMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await apiClient.post('/library/vessel-types', { name })
      return res.data
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['library', 'vessel-types'] })
      setSelectedVesselTypeId(data.id)
      setShowAddTypeModal(false)
      setNewTypeName('')
      setAddTypeError('')
    },
    onError: (err: any) => {
      setAddTypeError(err?.response?.data?.detail ?? 'Failed to create vessel type')
    },
  })

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!selectedVesselTypeId) { setImportError('Please select a vessel type first'); return }
    const file = e.target.files?.[0]
    if (file) { importMutation.mutate(file); e.target.value = '' }
  }

  const selectedType = vesselTypes.find(vt => vt.id === selectedVesselTypeId)

  return (
    <div className="flex gap-4 h-full min-h-0">
      {/* Left: Vessel Type list */}
      <div className="w-60 shrink-0 rounded-xl border border-slate-800 bg-slate-900 flex flex-col">
        <div className="flex items-center justify-between px-3 py-3 border-b border-slate-800">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Vessel Types</p>
          <button
            onClick={() => setShowAddTypeModal(true)}
            className="rounded p-1 text-slate-500 hover:text-sky-400 hover:bg-slate-800"
            title="Add vessel type"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {vtLoading ? (
            <div className="py-8 text-center text-slate-600 text-xs">Loading...</div>
          ) : vesselTypes.map((vt) => (
            <button
              key={vt.id}
              onClick={() => { setSelectedVesselTypeId(vt.id); setPage(1) }}
              className={`w-full flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm text-left transition-colors ${
                selectedVesselTypeId === vt.id
                  ? 'bg-sky-600/20 text-sky-300 border border-sky-600/30'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              <span className="flex-1 truncate">{vt.name}</span>
              <span className="text-xs text-slate-500 bg-slate-800 rounded-full px-1.5 py-0.5 shrink-0">
                {vt.component_count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Right: Components for selected vessel type */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        {/* Header row */}
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-white">
              {selectedType ? selectedType.name : 'Select a vessel type'}
            </h2>
            {selectedType && (
              <p className="text-xs text-slate-500">{total} components</p>
            )}
          </div>
          {selectedVesselTypeId && (
            <div className="flex items-center gap-2">
              <input ref={fileInputRef} type="file" accept=".xlsx,.csv" className="hidden" onChange={handleFileChange} />
              <a
                href={`${apiClient.defaults.baseURL}/library/component-structure/template`}
                download="component_library_template.xlsx"
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-600 text-slate-300 hover:text-white rounded-lg transition-colors text-sm"
              >
                <FileDown className="w-3.5 h-3.5" />
                Template
              </a>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={importMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50 text-sm"
              >
                {importMutation.isPending ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                Import Excel
              </button>
            </div>
          )}
        </div>

        {/* Banners */}
        {importResult && (
          <div className="flex items-center gap-3 p-3 bg-emerald-900/40 border border-emerald-600/50 rounded-lg text-sm">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <span className="text-emerald-300">Successfully imported <strong>{importResult.imported}</strong> components (version {importResult.version})</span>
            <button onClick={() => setImportResult(null)} className="ml-auto text-emerald-600 hover:text-emerald-300"><XCircle className="w-4 h-4" /></button>
          </div>
        )}
        {importError && (
          <div className="flex items-center gap-3 p-3 bg-red-900/40 border border-red-600/50 rounded-lg text-sm">
            <XCircle className="w-4 h-4 text-red-400 shrink-0" />
            <span className="text-red-300">{importError}</span>
            <button onClick={() => setImportError(null)} className="ml-auto text-red-600 hover:text-red-300"><XCircle className="w-4 h-4" /></button>
          </div>
        )}

        {/* Table */}
        {!selectedVesselTypeId ? (
          <div className="flex-1 flex items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900">
            <p className="text-slate-500 text-sm">Select a vessel type from the left panel</p>
          </div>
        ) : (
          <div className="flex-1 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden flex flex-col">
            <div className="flex-1 overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-900/50 sticky top-0">
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Hierarchy Code</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Category</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Type</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Code</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Component Name</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Critical</th>
                    <th className="text-left px-4 py-3 text-slate-400 font-medium text-xs">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                      <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />Loading...
                    </td></tr>
                  ) : nodes.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                      No components yet. Import an Excel file to populate this vessel type.
                    </td></tr>
                  ) : (
                    nodes.map((node) => (
                      <tr key={node.id} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors">
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{(node as any).machinery_code || (node as any).group1_code || '—'}</td>
                        <td className="px-4 py-2.5 text-slate-200 text-xs">{node.group1_name}</td>
                        <td className="px-4 py-2.5 text-slate-300 text-xs">{node.group2_name}</td>
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{node.component_code || '—'}</td>
                        <td className="px-4 py-2.5 text-slate-200 text-sm">{node.component_name || '—'}</td>
                        <td className="px-4 py-2.5">
                          {node.is_critical
                            ? <span className="text-amber-400 text-xs font-medium">Critical</span>
                            : <span className="text-slate-600 text-xs">—</span>}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${
                            node.status === 'active'
                              ? 'bg-emerald-900/40 text-emerald-400 border-emerald-600/40'
                              : 'bg-amber-900/40 text-amber-400 border-amber-600/40'
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${node.status === 'active' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                            {node.status === 'active' ? 'Active' : 'Pending'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
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
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">← Prev</button>
                <span className="px-3 text-xs text-slate-400">Page {page} of {totalPages}</span>
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                  className="px-2 py-1 rounded text-xs bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-40">Next →</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Add Vessel Type Modal */}
      {showAddTypeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 space-y-4">
            <h3 className="text-lg font-semibold text-white">Add Vessel Type</h3>
            <input
              autoFocus
              type="text"
              value={newTypeName}
              onChange={(e) => setNewTypeName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && newTypeName.trim()) createVesselTypeMutation.mutate(newTypeName.trim()) }}
              placeholder="e.g. VLCC, Container Ship, RoRo..."
              className="w-full px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            {addTypeError && <p className="text-red-400 text-sm">{addTypeError}</p>}
            <div className="flex justify-end gap-2">
              <button onClick={() => { setShowAddTypeModal(false); setNewTypeName(''); setAddTypeError('') }}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white">Cancel</button>
              <button
                onClick={() => { if (newTypeName.trim()) createVesselTypeMutation.mutate(newTypeName.trim()) }}
                disabled={!newTypeName.trim() || createVesselTypeMutation.isPending}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-sm disabled:opacity-50"
              >
                {createVesselTypeMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
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
      return res.data.items ?? res.data
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
