import React, { useState, useEffect } from 'react'
import { Download, RefreshCw, AlertTriangle, CheckCircle, X, FileSpreadsheet, Clock } from 'lucide-react'

interface ExportProgressModalProps {
  isOpen: boolean
  title?: string
  entityName?: string
  activeFiltersSummary?: string
  onClose: () => void
  isError?: boolean
  errorMessage?: string | null
  isSuccess?: boolean
}

export function ExportProgressModal({
  isOpen,
  title = 'Exporting QC Review Sheet',
  entityName = 'Spares',
  activeFiltersSummary,
  onClose,
  isError = false,
  errorMessage = null,
  isSuccess = false,
}: ExportProgressModalProps) {
  const [seconds, setSeconds] = useState(0)

  // Timer tick
  useEffect(() => {
    if (!isOpen || isError || isSuccess) return
    setSeconds(0)
    const interval = setInterval(() => {
      setSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [isOpen, isError, isSuccess])

  if (!isOpen) return null

  // Format seconds to mm:ss
  const formatTime = (totalSecs: number) => {
    const mins = Math.floor(totalSecs / 60)
    const secs = totalSecs % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  // Determine current step description and progress percentage based on elapsed time
  let stepText = 'Initializing export request...'
  let progressPercent = 15

  if (seconds >= 1 && seconds < 3) {
    stepText = `Applying active filters & querying ${entityName.toLowerCase()}...`
    progressPercent = 35
  } else if (seconds >= 3 && seconds < 8) {
    stepText = 'Generating Excel workbook & formatting QC review columns...'
    progressPercent = 65
  } else if (seconds >= 8 && seconds < 15) {
    stepText = 'Styling cell borders, data validation & auto-fitting columns...'
    progressPercent = 85
  } else if (seconds >= 15) {
    stepText = 'Finalizing file stream and transferring payload...'
    progressPercent = 95
  }

  if (isSuccess) {
    stepText = 'Export complete! Downloading file...'
    progressPercent = 100
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 shadow-2xl p-6 text-slate-100 flex flex-col">
        {/* Close Button if error or success */}
        {(isError || isSuccess) && (
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        )}

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-violet-950/60 border border-violet-800/50 text-violet-400">
            {isError ? (
              <AlertTriangle className="h-5 w-5 text-red-400" />
            ) : isSuccess ? (
              <CheckCircle className="h-5 w-5 text-emerald-400" />
            ) : (
              <FileSpreadsheet className="h-5 w-5 text-violet-400" />
            )}
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-100">{title}</h3>
            <p className="text-xs text-slate-400 mt-0.5">Please keep this window open while the file is being generated.</p>
          </div>
        </div>

        {/* Active Filters Summary Banner */}
        {activeFiltersSummary && (
          <div className="mt-4 rounded-lg bg-slate-950/70 border border-slate-800 p-3 text-xs text-slate-300">
            <span className="font-semibold text-slate-400 block mb-0.5 uppercase tracking-wider text-[10px]">Filter Context:</span>
            <p className="truncate text-sky-400 font-medium">{activeFiltersSummary}</p>
          </div>
        )}

        {/* Main Status Area */}
        <div className="mt-5 space-y-4">
          {isError ? (
            <div className="rounded-lg bg-red-950/40 border border-red-900/60 p-3.5 text-xs text-red-300">
              <p className="font-semibold text-red-200 mb-1">Export Error</p>
              <p>{errorMessage || 'An error occurred while generating the export file. Please try again.'}</p>
            </div>
          ) : (
            <>
              {/* Progress Bar */}
              <div>
                <div className="flex justify-between items-center text-xs mb-1.5 font-medium">
                  <span className="text-slate-300 flex items-center gap-1.5">
                    {!isSuccess && <RefreshCw className="h-3.5 w-3.5 animate-spin text-violet-400" />}
                    {stepText}
                  </span>
                  <span className="text-slate-400 font-mono">{progressPercent}%</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 rounded-full ${
                      isSuccess ? 'bg-emerald-500' : 'bg-gradient-to-r from-violet-500 to-sky-500'
                    }`}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>

              {/* Timer Counter */}
              <div className="flex items-center justify-between text-xs pt-1 border-t border-slate-800/60 text-slate-400">
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5 text-slate-500" />
                  Elapsed Time:
                </span>
                <span className="font-mono text-slate-200 font-semibold">{formatTime(seconds)}</span>
              </div>
            </>
          )}
        </div>

        {/* Actions */}
        <div className="mt-6 flex justify-end gap-2">
          {isError || isSuccess ? (
            <button
              onClick={onClose}
              className="w-full rounded-lg bg-slate-800 hover:bg-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 transition-colors"
            >
              Close
            </button>
          ) : (
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              Dismiss Overlay
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
