import React from 'react'
import { X, AlertTriangle, FileText } from 'lucide-react'

interface NoExtractedManual {
  manual_id: string
  original_filename: string
  missing_components_pages: number[]
  missing_jobs_pages: number[]
  missing_spares_pages: number[]
  missing_components_count: number
  missing_jobs_count: number
  missing_spares_count: number
  total_missing_pages_count: number
}

interface NoExtractedRecordsModalProps {
  isOpen: boolean
  onClose: () => void
  data: {
    manuals: NoExtractedManual[]
    total_no_extracted_pages: number
  } | null
}

export function NoExtractedRecordsModal({
  isOpen,
  onClose,
  data,
}: NoExtractedRecordsModalProps) {
  if (!isOpen) return null

  const manuals = data?.manuals || []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl rounded-xl border border-slate-800 bg-slate-900 shadow-2xl p-6 text-slate-100 max-h-[85vh] flex flex-col m-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            <div>
              <h2 className="text-lg font-bold text-slate-100">Specified Pages with No Extracted Records</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                The pages listed below were entered for extraction but returned 0 records.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-auto mt-4 pr-1">
          {manuals.length === 0 ? (
            <div className="py-12 text-center text-slate-500">
              <FileText className="mx-auto h-12 w-12 opacity-30 mb-3" />
              <p className="text-sm font-medium">All specified pages have at least one extracted record!</p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-slate-850 bg-slate-950">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-900/60 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    <th className="py-3 px-4 w-[40%]">Manual File</th>
                    <th className="py-3 px-4 w-[17%]">Components (No Recs)</th>
                    <th className="py-3 px-4 w-[17%]">Jobs (No Recs)</th>
                    <th className="py-3 px-4 w-[17%]">Spares (No Recs)</th>
                    <th className="py-3 px-4 text-center w-[9%]">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {manuals.map((manual) => (
                    <tr key={manual.manual_id} className="hover:bg-slate-900/40 transition-colors">
                      {/* Filename */}
                      <td className="py-3.5 px-4 font-semibold text-slate-300 break-all">
                        {manual.original_filename}
                      </td>

                      {/* Component pages */}
                      <td className="py-3.5 px-4">
                        {manual.missing_components_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.missing_components_pages.map((p) => (
                              <span
                                key={p}
                                className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-red-950/60 text-red-300 border border-red-900/50"
                              >
                                p. {p}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-600 text-xs italic">None</span>
                        )}
                      </td>

                      {/* Job pages */}
                      <td className="py-3.5 px-4">
                        {manual.missing_jobs_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.missing_jobs_pages.map((p) => (
                              <span
                                key={p}
                                className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-red-950/60 text-red-300 border border-red-900/50"
                              >
                                p. {p}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-600 text-xs italic">None</span>
                        )}
                      </td>

                      {/* Spare pages */}
                      <td className="py-3.5 px-4">
                        {manual.missing_spares_pages.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {manual.missing_spares_pages.map((p) => (
                              <span
                                key={p}
                                className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-semibold bg-red-950/60 text-red-300 border border-red-900/50"
                              >
                                p. {p}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-slate-600 text-xs italic">None</span>
                        )}
                      </td>

                      {/* Total */}
                      <td className="py-3.5 px-4 text-center font-bold text-amber-500">
                        {manual.total_missing_pages_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 border-t border-slate-800 pt-4 mt-4">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
