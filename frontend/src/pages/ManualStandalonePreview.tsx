import React, { useState, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search, FileText, ExternalLink, RefreshCw } from 'lucide-react'
import apiClient from '@/api/client'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'
import ResizableRowSplitView from '@/components/layout/ResizableRowSplitView'
import AddComponentModal from '@/components/components/AddComponentModal'

const QC_COLORS: Record<string, string> = {
  pending: 'bg-slate-700 text-slate-300',
  accepted: 'bg-green-900/60 text-green-300',
  rejected: 'bg-red-900/60 text-red-300',
  modified: 'bg-amber-900/60 text-amber-300',
}

const ManualStandalonePreview: React.FC = () => {
  const { vesselId, manualId } = useParams<{ vesselId: string; manualId: string }>()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const name = searchParams.get('name') || 'Manual Preview'
  const initialPages = searchParams.get('pages') || ''
  const mode = searchParams.get('mode') || ''

  const [activePages, setActivePages] = useState(initialPages)
  const [tableSearch, setTableSearch] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)

  // Fetch all components for this vessel
  const { data: componentsData, isLoading } = useQuery({
    queryKey: ['manual-components', vesselId, manualId, name],
    queryFn: () =>
      apiClient.get(`/vessels/${vesselId}/components`, { params: { page_size: 5000 } }).then((r) => r.data),
    enabled: !!vesselId,
  })

  // Filter components belonging to this manual
  const manualComponents = useMemo(() => {
    const all: any[] = componentsData?.items ?? []
    const qName = name.toLowerCase().trim()
    return all.filter((c) => {
      if (manualId && c.source_manual_id === manualId) return true
      if (qName && c.pdf_reference && c.pdf_reference.toLowerCase().trim() === qName) return true
      return false
    })
  }, [componentsData, manualId, name])

  // Filter components by search query
  const filteredComponents = useMemo(() => {
    if (!tableSearch.trim()) return manualComponents
    const q = tableSearch.toLowerCase()
    return manualComponents.filter(
      (c) =>
        c.component_name?.toLowerCase().includes(q) ||
        c.group1?.toLowerCase().includes(q) ||
        c.group2?.toLowerCase().includes(q) ||
        c.main_machinery?.toLowerCase().includes(q) ||
        c.maker?.toLowerCase().includes(q) ||
        c.model?.toLowerCase().includes(q)
    )
  }, [manualComponents, tableSearch])

  // Main machinery options for AddComponentModal
  const mainMachineryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const c of componentsData?.items ?? []) {
      if (c.main_machinery) set.add(c.main_machinery)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [componentsData])

  // Project manual options for AddComponentModal
  const projectManualOptions = useMemo(() => [name], [name])

  const handlePageJump = (pageStr: string | number | null | undefined) => {
    if (!pageStr) return
    setActivePages(String(pageStr))
  }

  return (
    <div className="h-screen w-screen bg-slate-950 p-2 overflow-hidden flex flex-col">
      <ResizableRowSplitView
        storageKey="manual_preview_split_pos"
        initialTopPercent={55}
        minTopPercent={25}
        minBottomPercent={20}
        top={
          <ManualPagePreview
            vesselId={vesselId ?? ''}
            manualId={manualId}
            manualName={name}
            title="Manual Preview"
            defaultPages={activePages}
            panelClassName="h-full w-full min-w-0"
            showTextSnippet={true}
            hideHeader={true}
            enableSnipPush={mode === 'snip'}
          />
        }
        bottom={
          <div className="h-full min-h-0 flex flex-col bg-slate-900 border border-slate-800 rounded-xl overflow-hidden p-3">
            {/* Header & Controls */}
            <div className="flex items-center justify-between flex-wrap gap-2 pb-2.5 border-b border-slate-800 shrink-0">
              <div>
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  Components from this Manual
                  <span className="text-xs font-normal text-sky-400 bg-sky-950 border border-sky-800/80 px-2 py-0.5 rounded-full">
                    {manualComponents.length} total
                  </span>
                </h2>
                <p className="text-[11px] text-slate-400 truncate max-w-md">{name}</p>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {/* Search table */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={tableSearch}
                    onChange={(e) => setTableSearch(e.target.value)}
                    placeholder="Filter components..."
                    className="w-48 rounded-lg border border-slate-700 bg-slate-800 py-1 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                {/* Add Component Button */}
                {vesselId && (
                  <button
                    onClick={() => setShowAddModal(true)}
                    className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 shadow-sm transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    Add Component
                  </button>
                )}
              </div>
            </div>

            {/* Components Table */}
            <div className="flex-1 min-h-0 overflow-auto pt-2">
              {isLoading ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-400 gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin text-sky-400" />
                  Loading components...
                </div>
              ) : filteredComponents.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-slate-500 py-8">
                  <FileText className="h-8 w-8 text-slate-700" />
                  <span>
                    {tableSearch ? 'No components match your search query.' : 'No components found for this manual yet.'}
                  </span>
                </div>
              ) : (
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 z-10 bg-slate-900 border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider">
                    <tr>
                      <th className="px-3 py-2">Component Name</th>
                      <th className="px-3 py-2">Hierarchy (Group › Sub-Group › Machinery)</th>
                      <th className="px-3 py-2 text-center">Page Ref</th>
                      <th className="px-3 py-2">Job Pages</th>
                      <th className="px-3 py-2">Spare Pages</th>
                      <th className="px-3 py-2">Maker & Model</th>
                      <th className="px-3 py-2">Criticality</th>
                      <th className="px-3 py-2">QC Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80 text-slate-300">
                    {filteredComponents.map((c) => (
                      <tr key={c.id} className="hover:bg-slate-800/60 transition-colors">
                        <td className="px-3 py-2 font-medium text-white max-w-xs truncate">{c.component_name}</td>
                        <td className="px-3 py-2 text-slate-400 truncate max-w-sm">
                          {c.group1} › {c.group2} › {c.main_machinery}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {c.page_reference ? (
                            <button
                              onClick={() => handlePageJump(c.page_reference)}
                              className="inline-flex items-center gap-1 rounded border border-sky-800 bg-sky-950 px-2 py-0.5 font-mono text-[11px] text-sky-300 hover:bg-sky-900 hover:text-white transition-colors"
                              title={`Jump to page ${c.page_reference} in PDF`}
                            >
                              <ExternalLink className="h-3 w-3" />
                              p.{c.page_reference}
                            </button>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {c.job_pages ? (
                            <button
                              onClick={() => handlePageJump(c.job_pages)}
                              className="text-sky-400 hover:underline font-mono"
                              title="Jump to job pages in PDF"
                            >
                              {c.job_pages}
                            </button>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {c.spare_pages ? (
                            <button
                              onClick={() => handlePageJump(c.spare_pages)}
                              className="text-sky-400 hover:underline font-mono"
                              title="Jump to spare pages in PDF"
                            >
                              {c.spare_pages}
                            </button>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-400 truncate">
                          {[c.maker, c.model].filter(Boolean).join(' ') || '—'}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-block rounded px-2 py-0.5 text-[10px] font-medium ${
                              c.criticality === 'critical'
                                ? 'bg-red-900/60 text-red-300'
                                : c.criticality === 'essential'
                                ? 'bg-amber-900/60 text-amber-300'
                                : 'bg-slate-800 text-slate-400'
                            }`}
                          >
                            {c.criticality || 'non_critical'}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${
                              QC_COLORS[c.qc_status] ?? 'bg-slate-800 text-slate-300'
                            }`}
                          >
                            {c.qc_status || 'pending'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        }
      />

      {/* Add Component Modal */}
      {showAddModal && vesselId && (
        <AddComponentModal
          vesselId={vesselId}
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['manual-components', vesselId] })
          }}
          initialPdfReference={name}
          mainMachineryOptions={mainMachineryOptions}
          projectManualOptions={projectManualOptions}
        />
      )}
    </div>
  )
}

export default ManualStandalonePreview
