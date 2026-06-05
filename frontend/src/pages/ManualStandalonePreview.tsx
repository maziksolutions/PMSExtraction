import React from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import ManualPagePreview from '@/components/manuals/ManualPagePreview'

const ManualStandalonePreview: React.FC = () => {
  const { vesselId, manualId } = useParams<{ vesselId: string; manualId: string }>()
  const [searchParams] = useSearchParams()
  const name = searchParams.get('name') || 'Manual Preview'
  const pages = searchParams.get('pages') || ''
  const mode = searchParams.get('mode') || ''

  return (
    <div className="h-screen w-screen bg-slate-950 p-2 overflow-hidden flex flex-col">
      <ManualPagePreview
        vesselId={vesselId ?? ''}
        manualId={manualId}
        manualName={name}
        title="Manual Preview"
        defaultPages={pages}
        panelClassName="h-full w-full min-w-0"
        showTextSnippet={true}
        hideHeader={true}
        enableSnipPush={mode === 'snip'}
      />
    </div>
  )
}

export default ManualStandalonePreview
