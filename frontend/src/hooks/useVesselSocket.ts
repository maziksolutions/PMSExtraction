import { useEffect, useRef, useState, useCallback } from 'react'
import { useAuthStore } from '@/store/authStore'
import apiClient from '@/api/client'

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

    let cancelled = false
    const loadActivity = () =>
      apiClient
        .get(`/vessels/${vesselId}/activity`, { params: { limit: 100 } })
        .then((response) => {
          if (cancelled) return
          const items = Array.isArray(response.data?.items) ? response.data.items : []
          setActivityFeed(items)
        })
        .catch(() => {
          if (!cancelled) {
            setActivityFeed((prev) => prev)
          }
        })

    loadActivity()
    const activityInterval = window.setInterval(loadActivity, 15000)

    const url = `${WS_BASE}/api/v1/ws/${vesselId}`
    const ws = new WebSocket(url, ['access-token', token])
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
          setActivityFeed((prev) => {
            const next = [msg.event, ...prev.filter((item) => item.id !== msg.event?.id)]
            return next.slice(0, 100)
          })
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
      cancelled = true
      window.clearInterval(activityInterval)
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current)
      }
      ws.close()
    }
  }, [vesselId, token])

  return { presenceList, activityFeed, isConnected, sendMessage }
}
