import React, { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileSearch, Maximize2, RefreshCw, X } from 'lucide-react'
import apiClient from '@/api/client'

interface PreviewPage {
  page_number: number
  text_excerpt?: string | null
  image_data_url?: string | null
  error?: string | null
}

interface PreviewResponse {
  manual_id: string
  file_name: string
  file_extension: string | null
  page_count: number | null
  pages: PreviewPage[]
}

interface ManualPagePreviewProps {
  vesselId: string
  manualId: string | null | undefined
  manualName?: string | null
  title: string
  subtitle?: string | null
  defaultPages?: string | number | null
  panelClassName?: string
  headerContent?: React.ReactNode
  showTextSnippet?: boolean
}

const ManualPagePreview: React.FC<ManualPagePreviewProps> = ({
  vesselId,
  manualId,
  manualName,
  title,
  subtitle,
  defaultPages,
  panelClassName,
  headerContent,
  showTextSnippet = true,
}) => {
  const [pageInput, setPageInput] = useState('')
  const [requestedPages, setRequestedPages] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    const nextValue = defaultPages == null ? '' : String(defaultPages)
    setPageInput(nextValue)
    setRequestedPages(nextValue)
  }, [defaultPages, manualId])

  const { data, isFetching, isError, refetch, error } = useQuery<PreviewResponse>({
    queryKey: ['manual-preview', vesselId, manualId, requestedPages],
    queryFn: () =>
      apiClient
        .get(`/vessels/${vesselId}/manuals/${manualId}/page-preview`, {
          params: { pages: requestedPages },
        })
        .then((response) => response.data),
    enabled: !!manualId && !!requestedPages,
    retry: false,
  })

  const renderPageCards = (fullscreen = false) => (
    <div className="space-y-4">
      {!requestedPages ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          Enter page numbers to load a manual preview.
        </div>
      ) : null}

      {requestedPages && !isFetching && !data?.pages?.length ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          No preview pages were returned for this selection.
        </div>
      ) : null}

      {isFetching && !data?.pages?.length ? (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-10 text-center text-sm text-slate-500">
          Loading preview pages...
        </div>
      ) : null}

      {data?.pages?.map((page) => (
        <section key={page.page_number} className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
          <div className="border-b border-slate-800 px-3 py-2">
            <div className="text-sm font-medium text-slate-100">Physical Page {page.page_number}</div>
            {page.error ? <div className="mt-1 text-xs text-red-300">{page.error}</div> : null}
          </div>
          <div className="space-y-3 p-3">
            {page.image_data_url ? (
              <img
                src={page.image_data_url}
                alt={`Manual page ${page.page_number}`}
                className={`rounded-lg border border-slate-800 bg-white ${fullscreen ? 'mx-auto max-h-[80vh] w-auto max-w-full' : 'w-full'}`}
              />
            ) : (
              <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed border-slate-700 bg-slate-900/80 text-xs text-slate-500">
                <div className="text-center">
                  <FileSearch className="mx-auto mb-2 h-5 w-5 opacity-40" />
                  Preview image not available for this page.
                </div>
              </div>
            )}
            {showTextSnippet ? (
              <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Extracted Text Snippet
                </div>
                <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-slate-300">
                  {page.text_excerpt?.trim() || 'No stored text snippet available for this page.'}
                </pre>
              </div>
            ) : null}
          </div>
        </section>
      ))}
    </div>
  )

  if (!manualId) {
    return (
      <aside className={`${panelClassName ?? 'w-[40rem]'} shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-4`}>
        {headerContent ? (
          <div className="mb-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
            {headerContent}
          </div>
        ) : null}
        <div className="flex h-full min-h-72 items-center justify-center text-center text-sm text-slate-500">
          Select a record with a manual reference to preview its pages.
        </div>
      </aside>
    )
  }

  return (
    <>
    <aside className={`${panelClassName ?? 'w-[40rem]'} shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900 p-4`}>
      <div className="mb-4 space-y-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
          <p className="mt-1 text-xs text-slate-400">{manualName ?? 'Manual preview'}</p>
          {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
        </div>
        {headerContent ? (
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
            {headerContent}
          </div>
        ) : null}
        <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
          <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Preview Pages
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={pageInput}
              onChange={(event) => setPageInput(event.target.value)}
              placeholder="e.g. 9-12 or 3,5,7"
              className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs text-slate-100 focus:border-sky-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setRequestedPages(pageInput.trim())}
              className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500"
            >
              Load
            </button>
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
              title="Refresh preview"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={() => setIsFullscreen(true)}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800"
              title="Open large preview"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="mt-2 text-[11px] text-slate-500">
            Load one page or multiple physical pages to verify what the extractor used.
          </p>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-red-900/60 bg-red-950/40 p-3 text-xs text-red-200">
          {(error as Error)?.message ?? 'Preview could not be loaded.'}
        </div>
      ) : null}

      {renderPageCards(false)}
    </aside>
    {isFullscreen ? (
      <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm">
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/95 px-5 py-3">
            <div>
              <div className="text-sm font-semibold text-white">{title}</div>
              <div className="mt-1 text-xs text-slate-400">{manualName ?? 'Manual preview'}</div>
            </div>
            <button
              type="button"
              onClick={() => setIsFullscreen(false)}
              className="rounded-lg border border-slate-700 px-3 py-2 text-slate-300 hover:bg-slate-800"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-5">
            {renderPageCards(true)}
          </div>
        </div>
      </div>
    ) : null}
    </>
  )
}

export default ManualPagePreview
