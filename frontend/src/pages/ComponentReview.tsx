import React, { useState, useCallback, useMemo, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  AlertCircle,
  Upload,
  Plus,
  Save,
  X,
  Link2,
  FileText,
  FolderPlus,
  Wrench,
  RefreshCw,
  Layers,
  FileDown,
} from 'lucide-react'
import apiClient from '@/api/client'

interface Component {
  id: string
  group1: string
  group2: string
  main_machinery: string
  component_name: string
  maker: string | null
  model: string | null
  specification: string | null
  serial_number: string | null
  source_manual_id: string | null
  page_reference: number | null
  confidence_score: number | null
  is_critical: boolean
  qc_status: string
  is_unmapped: boolean
  job_pages: string | null
  spare_pages: string | null
  pdf_reference: string | null
}

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-600 text-slate-200',
  accepted: 'bg-green-700 text-green-100',
  rejected: 'bg-red-700 text-red-100',
  modified: 'bg-blue-700 text-blue-100',
}

interface TreeNode {
  group1: string
  group2s: Record<string, { mainMachineries: Record<string, number>; count: number }>
  count: number
}

// ---- Add Component Modal ----
interface AddModalProps {
  vesselId: string
  onClose: () => void
  onCreated: () => void
  initialGroup1?: string
  initialGroup2?: string
  initialMachinery?: string
}

function AddComponentModal({ vesselId, onClose, onCreated, initialGroup1, initialGroup2, initialMachinery }: AddModalProps) {
  const [form, setForm] = useState({
    group1: initialGroup1 ?? '',
    group2: initialGroup2 ?? '',
    main_machinery: initialMachinery ?? '',
    component_name: '',
    maker: '',
    model: '',
    serial_number: '',
    specification: '',
    is_critical: false,
    job_pages: '',
    spare_pages: '',
    pdf_reference: '',
  })

  const mutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/vessels/${vesselId}/components`, {
        ...form,
        maker: form.maker || null,
        model: form.model || null,
        serial_number: form.serial_number || null,
        specification: form.specification || null,
        job_pages: form.job_pages || null,
        spare_pages: form.spare_pages || null,
        pdf_reference: form.pdf_reference || null,
      }).then(r => r.data),
    onSuccess: () => { onCreated(); onClose() },
  })

  const set = (k: string, v: string | boolean) => setForm(p => ({ ...p, [k]: v }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Add Component</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-4 max-h-[70vh] overflow-y-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Hierarchy</p>
          <div className="grid grid-cols-3 gap-3">
            {[['group1','Group'], ['group2','Sub-Group'], ['main_machinery','Main Machinery']].map(([k,label]) => (
              <div key={k}>
                <label className="mb-1 block text-xs text-slate-400">{label}</label>
                <input
                  value={(form as any)[k]}
                  onChange={e => set(k, e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                  placeholder={label}
                />
              </div>
            ))}
          </div>

          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 pt-2">Component Details</p>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Component Name *</label>
            <input
              value={form.component_name}
              onChange={e => set('component_name', e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
              placeholder="e.g. Main Seawater Pump"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[['maker','Maker / Manufacturer'], ['model','Model'], ['serial_number','Serial Number'], ['specification','Specification']].map(([k,label]) => (
              <div key={k}>
                <label className="mb-1 block text-xs text-slate-400">{label}</label>
                <input
                  value={(form as any)[k]}
                  onChange={e => set(k, e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                  placeholder={label}
                />
              </div>
            ))}
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_critical}
              onChange={e => set('is_critical', e.target.checked)}
              className="h-4 w-4 rounded"
            />
            <span className="text-sm text-slate-300">Mark as Critical Equipment</span>
          </label>

          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 pt-2">Page References</p>
          <div className="grid grid-cols-3 gap-3">
            {[['job_pages','Job Pages','e.g. 21-50'], ['spare_pages','Spare Pages','e.g. 51-80'], ['pdf_reference','PDF Reference','Filename or link']].map(([k,label,ph]) => (
              <div key={k}>
                <label className="mb-1 block text-xs text-slate-400">{label}</label>
                <input
                  value={(form as any)[k]}
                  onChange={e => set(k, e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white focus:border-sky-500 focus:outline-none"
                  placeholder={ph}
                />
              </div>
            ))}
          </div>
        </div>
        <div className="flex justify-end gap-3 border-t border-slate-700 px-6 py-4">
          <button onClick={onClose} className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800">Cancel</button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!form.component_name || mutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-sky-600 px-5 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {mutation.isPending ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Add Component
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- Edit row inline ----
interface InlineEdit {
  job_pages?: string
  spare_pages?: string
  pdf_reference?: string
  maker?: string
  model?: string
  qc_status?: string
}

const ComponentReview: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const queryClient = useQueryClient()

  const [selectedGroup1, setSelectedGroup1] = useState<string | null>(null)
  const [selectedGroup2, setSelectedGroup2] = useState<string | null>(null)
  const [selectedMachinery, setSelectedMachinery] = useState<string | null>(null)
  const [showUnmapped, setShowUnmapped] = useState(false)
  const [expandedG1, setExpandedG1] = useState<Set<string>>(new Set())
  const [expandedG2, setExpandedG2] = useState<Set<string>>(new Set())
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [filterQC, setFilterQC] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [addContext, setAddContext] = useState<{ group1?: string; group2?: string; machinery?: string }>({})
  const [edits, setEdits] = useState<Record<string, InlineEdit>>({})
  const [importResult, setImportResult] = useState<string | null>(null)
  const [autoLinkLoading, setAutoLinkLoading] = useState(false)
  const [libraryLoading, setLibraryLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['components', vesselId, selectedGroup1, selectedGroup2, selectedMachinery, filterQC, showUnmapped],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (selectedGroup1) params.group1 = selectedGroup1
      if (selectedGroup2) params.group2 = selectedGroup2
      if (selectedMachinery) params.main_machinery = selectedMachinery
      if (filterQC) params.qc_status = filterQC
      if (showUnmapped) params.is_unmapped = 'true'
      return apiClient.get(`/vessels/${vesselId}/components`, { params }).then((r) => r.data)
    },
    enabled: !!vesselId,
  })

  const allComponentsQuery = useQuery({
    queryKey: ['components-all', vesselId],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/components`, { params: { page_size: 500 } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  const bulkAcceptMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-accept`, { ids }).then((r) => r.data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['components', vesselId] }); setSelectedIds(new Set()) },
  })

  const bulkRejectMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiClient.post(`/vessels/${vesselId}/components/bulk-reject`, { ids }).then((r) => r.data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['components', vesselId] }); setSelectedIds(new Set()) },
  })

  const saveMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: InlineEdit }) =>
      apiClient.patch(`/vessels/${vesselId}/components/${id}`, data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      setEdits({})
    },
  })

  const handleAutoLink = async () => {
    setAutoLinkLoading(true)
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/components/auto-link-pages`)
      setImportResult(`Auto-linked page references for ${res.data.updated} components.`)
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
    } catch { setImportResult('Auto-link failed.') }
    setAutoLinkLoading(false)
  }

  const handleLoadFromLibrary = async () => {
    setLibraryLoading(true)
    try {
      const res = await apiClient.post('/library/component-structure/push-to-vessel', { vessel_id: vesselId })
      setImportResult(`Loaded ${res.data.added} standard components from library (${res.data.skipped} already existed).`)
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
    } catch (err: any) {
      setImportResult(`Load from library failed: ${err?.response?.data?.detail ?? err?.message}`)
    }
    setLibraryLoading(false)
  }

  const handleExcelImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiClient.post(`/vessels/${vesselId}/components/import-excel`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setImportResult(`Imported ${res.data.imported} components (${res.data.skipped} skipped).`)
      queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
      queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
    } catch (err: any) {
      setImportResult(`Import failed: ${err?.response?.data?.detail ?? err?.message}`)
    }
    e.target.value = ''
  }

  const toggleG1 = useCallback((key: string) => {
    setExpandedG1(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }, [])
  const toggleG2 = useCallback((key: string) => {
    setExpandedG2(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }, [])

  const setEdit = (id: string, field: keyof InlineEdit, value: string) => {
    setEdits(prev => ({ ...prev, [id]: { ...prev[id], [field]: value } }))
  }

  // Build 3-level tree: group1 → group2 → main_machinery
  const tree = useMemo<Record<string, TreeNode>>(() => {
    const allComponents: Component[] = allComponentsQuery.data?.items ?? []
    const nodes: Record<string, TreeNode> = {}
    for (const comp of allComponents) {
      if (!nodes[comp.group1]) nodes[comp.group1] = { group1: comp.group1, group2s: {}, count: 0 }
      nodes[comp.group1].count++
      if (!nodes[comp.group1].group2s[comp.group2])
        nodes[comp.group1].group2s[comp.group2] = { mainMachineries: {}, count: 0 }
      nodes[comp.group1].group2s[comp.group2].count++
      const mm = comp.main_machinery
      nodes[comp.group1].group2s[comp.group2].mainMachineries[mm] =
        (nodes[comp.group1].group2s[comp.group2].mainMachineries[mm] ?? 0) + 1
    }
    return nodes
  }, [allComponentsQuery.data])

  const components: Component[] = data?.items ?? []

  return (
    <div className="flex h-full gap-4">
      {showAddModal && vesselId && (
        <AddComponentModal
          vesselId={vesselId}
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['components', vesselId] })
            queryClient.invalidateQueries({ queryKey: ['components-all', vesselId] })
          }}
          initialGroup1={addContext.group1}
          initialGroup2={addContext.group2}
          initialMachinery={addContext.machinery}
        />
      )}

      {/* Left Panel: 3-level Tree */}
      <aside className="w-64 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-3">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Component Hierarchy</p>
          <button
            onClick={() => { setAddContext({}); setShowAddModal(true) }}
            title="Add component"
            className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-sky-400"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* All Components */}
        <button
          onClick={() => { setSelectedGroup1(null); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(false) }}
          className={`mb-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${!selectedGroup1 && !showUnmapped ? 'bg-sky-600/20 text-sky-300' : 'text-slate-300 hover:bg-slate-800'}`}
        >
          All Components
          <span className="ml-auto rounded-full bg-slate-700 px-1.5 text-xs text-slate-400">
            {allComponentsQuery.data?.items?.length ?? 0}
          </span>
        </button>

        {Object.values(tree).map((node) => (
          <div key={node.group1}>
            {/* Group 1 */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => toggleG1(node.group1)}
                className="flex items-center p-1 text-slate-400 hover:text-white"
              >
                {expandedG1.has(node.group1) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              </button>
              <button
                onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(false) }}
                className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm transition-colors ${selectedGroup1 === node.group1 && !selectedGroup2 ? 'bg-sky-600/20 text-sky-300' : 'text-slate-300 hover:bg-slate-800'}`}
              >
                <FolderPlus className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span className="flex-1 truncate text-left">{node.group1}</span>
                <span className="rounded-full bg-slate-700 px-1.5 text-xs text-slate-400">{node.count}</span>
              </button>
              <button
                onClick={() => { setAddContext({ group1: node.group1 }); setShowAddModal(true) }}
                title="Add to this group"
                className="rounded p-1 text-slate-600 hover:text-sky-400"
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>

            {/* Group 2 */}
            {expandedG1.has(node.group1) && Object.entries(node.group2s).map(([g2, g2data]) => (
              <div key={g2} className="ml-5">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => toggleG2(`${node.group1}::${g2}`)}
                    className="flex items-center p-1 text-slate-500 hover:text-white"
                  >
                    {expandedG2.has(`${node.group1}::${g2}`) ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </button>
                  <button
                    onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(g2); setSelectedMachinery(null); setShowUnmapped(false) }}
                    className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-colors ${selectedGroup2 === g2 && !selectedMachinery ? 'bg-sky-600/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'}`}
                  >
                    <span className="flex-1 truncate text-left">{g2}</span>
                    <span className="text-slate-500">{g2data.count}</span>
                  </button>
                  <button
                    onClick={() => { setAddContext({ group1: node.group1, group2: g2 }); setShowAddModal(true) }}
                    title="Add to this sub-group"
                    className="rounded p-0.5 text-slate-600 hover:text-sky-400"
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                </div>

                {/* Main Machinery */}
                {expandedG2.has(`${node.group1}::${g2}`) && Object.entries(g2data.mainMachineries).map(([mm, count]) => (
                  <div key={mm} className="ml-5 flex items-center gap-1">
                    <button
                      onClick={() => { setSelectedGroup1(node.group1); setSelectedGroup2(g2); setSelectedMachinery(mm); setShowUnmapped(false) }}
                      className={`flex flex-1 items-center gap-1.5 rounded-lg px-2 py-1 text-xs transition-colors ${selectedMachinery === mm ? 'bg-sky-600/20 text-sky-300' : 'text-slate-500 hover:bg-slate-800'}`}
                    >
                      <Wrench className="h-3 w-3 shrink-0 text-slate-500" />
                      <span className="flex-1 truncate text-left">{mm}</span>
                      <span className="text-slate-600">{count}</span>
                    </button>
                    <button
                      onClick={() => { setAddContext({ group1: node.group1, group2: g2, machinery: mm }); setShowAddModal(true) }}
                      title="Add component here"
                      className="rounded p-0.5 text-slate-600 hover:text-sky-400"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            ))}
          </div>
        ))}

        <button
          onClick={() => { setSelectedGroup1(null); setSelectedGroup2(null); setSelectedMachinery(null); setShowUnmapped(true) }}
          className={`mt-2 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors ${showUnmapped ? 'bg-amber-600/20 text-amber-300' : 'text-amber-400 hover:bg-slate-800'}`}
        >
          <AlertCircle className="h-3.5 w-3.5" />
          Unmapped
        </button>
      </aside>

      {/* Right Panel */}
      <div className="flex flex-1 flex-col gap-4 overflow-hidden">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold text-white mr-2">Components</h1>

          {/* Import Excel */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white"
          >
            <Upload className="h-3.5 w-3.5" />
            Import Excel
          </button>
          <input ref={fileInputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={handleExcelImport} />
          <a
            href={`${apiClient.defaults.baseURL}/vessels/components/import-template`}
            download="components_import_template.xlsx"
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white"
          >
            <FileDown className="h-3.5 w-3.5" />
            Template
          </a>

          {/* Load from Library */}
          <button
            onClick={handleLoadFromLibrary}
            disabled={libraryLoading}
            className="flex items-center gap-1.5 rounded-lg border border-sky-700 bg-sky-900/30 px-3 py-1.5 text-xs font-medium text-sky-300 hover:bg-sky-800/40 hover:text-white disabled:opacity-50"
          >
            {libraryLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            Load from Library
          </button>

          {/* Auto-link pages */}
          <button
            onClick={handleAutoLink}
            disabled={autoLinkLoading}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-white disabled:opacity-50"
          >
            {autoLinkLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
            Auto-Link Pages
          </button>

          {/* Add Component */}
          <button
            onClick={() => { setAddContext({}); setShowAddModal(true) }}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Component
          </button>

          <div className="ml-auto flex items-center gap-2">
            {/* Bulk actions */}
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

            {/* Save all inline edits */}
            {Object.keys(edits).length > 0 && (
              <button
                onClick={() => Object.entries(edits).forEach(([id, data]) => saveMutation.mutate({ id, data }))}
                disabled={saveMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-500 disabled:opacity-50"
              >
                <Save className="h-3.5 w-3.5" />
                Save {Object.keys(edits).length} edit(s)
              </button>
            )}

            <select
              value={filterQC}
              onChange={(e) => setFilterQC(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              <option value="">All QC Status</option>
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
              <option value="modified">Modified</option>
            </select>
          </div>
        </div>

        {/* Import / auto-link result banner */}
        {importResult && (
          <div className="flex items-center gap-2 rounded-xl border border-sky-700 bg-sky-900/20 px-4 py-2.5 text-sm text-sky-300">
            <FileText className="h-4 w-4 shrink-0" />
            {importResult}
            <button onClick={() => setImportResult(null)} className="ml-auto text-slate-500 hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Excel format hint when empty */}
        {!isLoading && components.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900 p-6 text-center space-y-3">
            <Upload className="mx-auto h-10 w-10 text-slate-600" />
            <p className="text-slate-300 font-medium">No components yet</p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              Import an Excel file or add components manually.<br />
              <strong className="text-slate-400">Excel columns:</strong> Group | Sub-Group | Main Machinery | Component Name | Maker | Model | Serial Number | Specification | Critical | Job Pages | Spare Pages | PDF Reference
            </p>
            <div className="flex justify-center gap-3 pt-1 flex-wrap">
              <button
                onClick={handleLoadFromLibrary}
                disabled={libraryLoading}
                className="flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {libraryLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Layers className="h-4 w-4" />}
                Load from Library
              </button>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                <Upload className="h-4 w-4" /> Import Excel / CSV
              </button>
              <button
                onClick={() => { setAddContext({}); setShowAddModal(true) }}
                className="flex items-center gap-2 rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                <Plus className="h-4 w-4" /> Add Manually
              </button>
            </div>
          </div>
        )}

        {/* Table */}
        {(isLoading || components.length > 0) && (
          <div className="flex-1 overflow-auto rounded-xl border border-slate-800 bg-slate-900">
            {isLoading ? (
              <div className="py-16 text-center text-slate-500">Loading...</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="sticky top-0 border-b border-slate-700 bg-slate-900 text-left text-xs text-slate-500 uppercase">
                    <th className="px-3 py-3 w-8">
                      <input
                        type="checkbox"
                        onChange={e => e.target.checked ? setSelectedIds(new Set(components.map(c => c.id))) : setSelectedIds(new Set())}
                        checked={selectedIds.size === components.length && components.length > 0}
                        className="h-3.5 w-3.5 rounded"
                      />
                    </th>
                    <th className="px-3 py-3">Component</th>
                    <th className="px-3 py-3">Maker</th>
                    <th className="px-3 py-3">Model</th>
                    <th className="px-3 py-3">Job Pages</th>
                    <th className="px-3 py-3">Spare Pages</th>
                    <th className="px-3 py-3">PDF Reference</th>
                    <th className="px-3 py-3">Critical</th>
                    <th className="px-3 py-3">QC</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {components.map((comp) => {
                    const edit = edits[comp.id] ?? {}
                    const changed = Object.keys(edit).length > 0
                    return (
                      <tr
                        key={comp.id}
                        className={`transition-colors hover:bg-slate-800/50 ${changed ? 'bg-violet-900/10' : ''} ${selectedIds.has(comp.id) ? 'bg-sky-900/10' : ''}`}
                      >
                        <td className="px-3 py-2.5">
                          <input type="checkbox" checked={selectedIds.has(comp.id)} onChange={() => toggleSelect(comp.id)} className="h-3.5 w-3.5 rounded" />
                        </td>
                        <td className="px-3 py-2.5 max-w-xs">
                          <p className="font-medium text-slate-200">{comp.component_name}</p>
                          <p className="text-xs text-slate-500 truncate">{comp.group1} › {comp.group2} › {comp.main_machinery}</p>
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            value={edit.maker ?? comp.maker ?? ''}
                            onChange={e => setEdit(comp.id, 'maker', e.target.value)}
                            className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                            placeholder="—"
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            value={edit.model ?? comp.model ?? ''}
                            onChange={e => setEdit(comp.id, 'model', e.target.value)}
                            className="w-24 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                            placeholder="—"
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            value={edit.job_pages ?? comp.job_pages ?? ''}
                            onChange={e => setEdit(comp.id, 'job_pages', e.target.value)}
                            className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                            placeholder="e.g. 21-50"
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            value={edit.spare_pages ?? comp.spare_pages ?? ''}
                            onChange={e => setEdit(comp.id, 'spare_pages', e.target.value)}
                            className="w-20 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                            placeholder="e.g. 81-120"
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            value={edit.pdf_reference ?? comp.pdf_reference ?? ''}
                            onChange={e => setEdit(comp.id, 'pdf_reference', e.target.value)}
                            className="w-32 rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
                            placeholder="filename"
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          {comp.is_critical ? (
                            <span className="rounded-full bg-red-900/50 px-2 py-0.5 text-xs text-red-300">Critical</span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <select
                            value={edit.qc_status ?? comp.qc_status}
                            onChange={e => setEdit(comp.id, 'qc_status', e.target.value)}
                            className={`rounded-full px-2 py-0.5 text-xs font-medium cursor-pointer border-0 ${QC_COLORS[edit.qc_status ?? comp.qc_status] ?? 'bg-slate-700 text-slate-300'}`}
                          >
                            <option value="pending">pending</option>
                            <option value="accepted">accepted</option>
                            <option value="rejected">rejected</option>
                            <option value="modified">modified</option>
                          </select>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ComponentReview
