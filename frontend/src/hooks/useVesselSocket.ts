import { useEffect, useRef, useState, useCallback } from 'react'
import { useAuthStore } from '@/store/authStore'

export interface PresenceUser {
  user_id: string
  user_name: string
}

export interface ActivityEvent {
  id: string
  action_type: string
  entity_type: string
  entity_id: string
  description: string
  created_at: string
  user_id: string
}

interface UseVesselSocketResult {
  presenceList: PresenceUser[]
  activityFeed: ActivityEvent[]
  isConnected: boolean
  sendMessage: (msg: object) => void
}

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

export function useVesselSocket(vesselId: string | undefined): UseVesselSocketResult {
  const { accessToken: token } = useAuthStore()
  const wsRef = useRef<WebSocket | null>(null)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [presenceList, setPresenceList] = useState<PresenceUser[]>([])
  const [activityFeed, setActivityFeed] = useState<ActivityEvent[]>([])

  const sendMessage = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    if (!vesselId || !token) return

    const url = `${WS_BASE}/api/v1/ws/${vesselId}?token=${token}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      heartbeatRef.current = setInterval(() => {
        sendMessage({ type: 'heartbeat' })
      }, 30_000)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'presence_update') {
          setPresenceList(msg.users ?? [])
        } else if (msg.type === 'activity') {
          setActivityFeed((prev) => [msg.event, ...prev].slice(0, 100))
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current)
      }
    }

    ws.onerror = () => {
      setIsConnected(false)
    }

    return () => {
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current)
      }
      ws.close()
    }
  }, [vesselId, token])

  return { presenceList, activityFeed, isConnected, sendMessage }
}
