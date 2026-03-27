import React from 'react'
import type { PresenceUser } from '@/hooks/useVesselSocket'

interface Props {
  users: PresenceUser[]
  isConnected: boolean
}

const PresenceIndicators: React.FC<Props> = ({ users, isConnected }) => {
  return (
    <div className="flex items-center gap-2">
      {/* Connection indicator */}
      <span
        className={`flex h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-slate-600'}`}
        title={isConnected ? 'Connected' : 'Disconnected'}
      />
      {/* User avatars */}
      <div className="flex -space-x-1.5">
        {users.slice(0, 5).map((u) => (
          <div
            key={u.user_id}
            title={u.user_name}
            className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-slate-900 bg-sky-700 text-xs font-semibold text-white uppercase"
          >
            {u.user_name?.charAt(0) ?? '?'}
          </div>
        ))}
        {users.length > 5 && (
          <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-slate-900 bg-slate-700 text-xs font-semibold text-slate-300">
            +{users.length - 5}
          </div>
        )}
      </div>
      {users.length > 0 && (
        <span className="text-xs text-slate-500">
          {users.length} online
        </span>
      )}
    </div>
  )
}

export default PresenceIndicators
