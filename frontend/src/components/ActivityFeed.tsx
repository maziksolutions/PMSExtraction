import React from 'react'
import { Activity } from 'lucide-react'
import type { ActivityEvent } from '@/hooks/useVesselSocket'

interface Props {
  events: ActivityEvent[]
}

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const ACTION_COLORS: Record<string, string> = {
  accepted: 'text-green-400',
  rejected: 'text-red-400',
  corrected: 'text-sky-400',
  modified: 'text-amber-400',
  created: 'text-violet-400',
  deleted: 'text-slate-400',
}

const ActivityFeed: React.FC<Props> = ({ events }) => {
  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
        <Activity className="h-4 w-4 text-sky-400" />
        <span className="text-sm font-semibold text-slate-200">Activity Feed</span>
        {events.length > 0 && (
          <span className="ml-auto rounded-full bg-sky-700 px-2 py-0.5 text-xs font-medium text-sky-100">
            {events.length}
          </span>
        )}
      </div>

      {/* Events list */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {events.length === 0 ? (
          <p className="py-10 text-center text-xs text-slate-500">
            No recent activity.
            <br />
            Events appear here as the team reviews records.
          </p>
        ) : (
          events.map((e) => {
            const actionWord = e.action_type.split('.')[1] ?? e.action_type
            const colorClass = ACTION_COLORS[actionWord] ?? 'text-slate-300'
            return (
              <div key={e.id} className="rounded-lg bg-slate-800 p-2.5">
                <p className="text-xs text-slate-200 leading-relaxed">{e.description}</p>
                <div className="mt-1.5 flex items-center justify-between">
                  <span className={`text-xs font-medium ${colorClass}`}>
                    {e.entity_type} • {actionWord}
                  </span>
                  <span className="text-xs text-slate-500">{timeAgo(e.created_at)}</span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default ActivityFeed
