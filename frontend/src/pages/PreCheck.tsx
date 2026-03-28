import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  ArrowRight,
  ClipboardCheck,
} from 'lucide-react'
import apiClient from '@/api/client'

// ─── Interfaces ───────────────────────────────────────────────────────────────

interface PreCheckItem {
  id: string
  machinery_name: string
  status: 'found' | 'low_confidence' | 'missing'
  matched_manual?: string
  match_score?: number
  user_acknowledgement?: string
  absence_reason?: string
}

interface PreCheckResult {
  items: PreCheckItem[]
  run_at: string
}

type AckOption = '' | 'upload_pending' | 'genuinely_absent' | 'not_applicable' | 'confirmed'

const ACK_OPTIONS: { value: AckOption; label: string }[] = [
  { value: '', label: '— Select action —' },
  { value: 'upload_pending', label: 'Upload Pending' },
  { value: 'genuinely_absent', label: 'Genuinely Absent' },
  { value: 'not_applicable', label: 'Not Applicable' },
  { value: 'confirmed', label: 'Confirmed' },
]

// ─── Status Display ───────────────────────────────────────────────────────────

const StatusBadge: React.FC<{ status: PreCheckItem['status'] }> = ({ status }) => {
  if (status === 'found') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-900/40 text-emerald-400 text-xs rounded-full border border-emerald-600/40">
        <CheckCircle className="w-3.5 h-3.5" />
        Instruction Manual Found
      </span>
    )
  }
  if (status === 'low_confidence') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-900/40 text-amber-400 text-xs rounded-full border border-amber-600/40">
        <AlertTriangle className="w-3.5 h-3.5" />
        Low Confidence — Review Required
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-red-900/40 text-red-400 text-xs rounded-full border border-red-600/40">
      <XCircle className="w-3.5 h-3.5" />
      Missing — Action Required
    </span>
  )
}

// ─── Acknowledgement Cell ─────────────────────────────────────────────────────

interface AckCellProps {
  item: PreCheckItem
  vesselId: string
  onUpdate: (itemId: string, ack: string, reason?: string) => void
  isPending: boolean
}

const AckCell: React.FC<AckCellProps> = ({ item, vesselId, onUpdate, isPending }) => {
  const [localAck, setLocalAck] = useState<AckOption>((item.user_acknowledgement as AckOption) ?? '')
  const [localReason, setLocalReason] = useState(item.absence_reason ?? '')

  if (item.status === 'found') {
    return (
      <span className="inline-flex items-center gap-1.5 text-emerald-400 text-sm">
        <CheckCircle className="w-4 h-4" />
        No action needed
      </span>
    )
  }

  const handleAckChange = (value: AckOption) => {
    setLocalAck(value)
    if (value !== 'genuinely_absent') {
      onUpdate(item.id, value)
    }
  }

  const handleReasonBlur = () => {
    if (localAck === 'genuinely_absent') {
      onUpdate(item.id, localAck, localReason)
    }
  }

  return (
    <div className="space-y-2">
      <select
        value={localAck}
        onChange={(e) => handleAckChange(e.target.value as AckOption)}
        disabled={isPending}
        className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm focus:outline-none focus:border-sky-500 disabled:opacity-50 w-48"
      >
        {ACK_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {localAck === 'genuinely_absent' && (
        <input
          type="text"
          value={localReason}
          onChange={(e) => setLocalReason(e.target.value)}
          onBlur={handleReasonBlur}
          placeholder="Reason for absence..."
          className="w-48 px-3 py-1.5 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 text-sm focus:outline-none focus:border-sky-500"
        />
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const PreCheck: React.FC = () => {
  const { vesselId } = useParams<{ vesselId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Local override map for acknowledgements (itemId -> ack value)
  const [ackOverrides, setAckOverrides] = useState<Record<string, string>>({})

  const { data: result, isLoading: isLoadingResult } = useQuery<PreCheckResult>({
    queryKey: ['precheck', vesselId],
    queryFn: async () => {
      const res = await apiClient.get(`/api/v1/vessels/${vesselId}/precheck`)
      return res.data
    },
    enabled: !!vesselId,
  })

  const runMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post(`/api/v1/vessels/${vesselId}/precheck/run`)
      return res.data as PreCheckResult
    },
    onSuccess: () => {
      setAckOverrides({})
      queryClient.invalidateQueries({ queryKey: ['precheck', vesselId] })
    },
  })

  const patchMutation = useMutation({
    mutationFn: async ({
      itemId,
      user_acknowledgement,
      absence_reason,
    }: {
      itemId: string
      user_acknowledgement: string
      absence_reason?: string
    }) => {
      await apiClient.patch(`/api/v1/vessels/${vesselId}/precheck/${itemId}`, {
        user_acknowledgement,
        ...(absence_reason !== undefined && { absence_reason }),
      })
    },
    onSuccess: (_data, variables) => {
      setAckOverrides((prev) => ({ ...prev, [variables.itemId]: variables.user_acknowledgement }))
      queryClient.invalidateQueries({ queryKey: ['precheck', vesselId] })
    },
  })

  const handleUpdate = (itemId: string, ack: string, reason?: string) => {
    patchMutation.mutate({ itemId, user_acknowledgement: ack, absence_reason: reason })
  }

  const items = result?.items ?? []

  // All "missing" items must have a non-empty acknowledgement to proceed
  const missingItems = items.filter((item) => item.status === 'missing')
  const allMissingAcknowledged = missingItems.every((item) => {
    const ack = ackOverrides[item.id] ?? item.user_acknowledgement
    return ack && ack !== ''
  })
  const canProceed = missingItems.length === 0 || allMissingAcknowledged

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <ClipboardCheck className="w-7 h-7 text-sky-400" />
            Instruction Manual Pre-Check
          </h1>
          <p className="text-slate-400 mt-1">
            Step 1 of 2 — Verify instruction manuals are present for all major machinery
          </p>
        </div>
        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="flex items-center gap-2 px-5 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-50 font-medium"
        >
          {runMutation.isPending ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              Running Pre-Check...
            </>
          ) : (
            <>
              <RefreshCw className="w-4 h-4" />
              Run Pre-Check
            </>
          )}
        </button>
      </div>

      {/* Summary stats (when results exist) */}
      {items.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {(
            [
              { status: 'found', label: 'Found', color: 'emerald', icon: <CheckCircle className="w-5 h-5" /> },
              { status: 'low_confidence', label: 'Low Confidence', color: 'amber', icon: <AlertTriangle className="w-5 h-5" /> },
              { status: 'missing', label: 'Missing', color: 'red', icon: <XCircle className="w-5 h-5" /> },
            ] as const
          ).map(({ status, label, color, icon }) => {
            const count = items.filter((i) => i.status === status).length
            return (
              <div
                key={status}
                className={`bg-slate-800 border border-slate-700 rounded-xl p-4 flex items-center gap-3`}
              >
                <span className={`text-${color}-400`}>{icon}</span>
                <div>
                  <p className={`text-2xl font-bold text-${color}-400`}>{count}</p>
                  <p className="text-sm text-slate-400">{label}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Loading state */}
      {isLoadingResult && (
        <div className="flex items-center justify-center py-16">
          <div className="text-center space-y-3">
            <RefreshCw className="w-8 h-8 animate-spin text-sky-400 mx-auto" />
            <p className="text-slate-400">Loading pre-check results...</p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoadingResult && items.length === 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center">
          <ClipboardCheck className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400 font-medium">No pre-check results yet</p>
          <p className="text-slate-500 text-sm mt-1">Click "Run Pre-Check" to scan for instruction manuals.</p>
        </div>
      )}

      {/* Results Table */}
      {items.length > 0 && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-300">Pre-Check Results</h2>
            {result?.run_at && (
              <span className="text-xs text-slate-500">
                Last run: {new Date(result.run_at).toLocaleString()}
              </span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-900/50">
                  <th className="text-left px-4 py-3 text-slate-400 font-medium">Machinery Name</th>
                  <th className="text-left px-4 py-3 text-slate-400 font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-slate-400 font-medium">Matched Manual</th>
                  <th className="text-left px-4 py-3 text-slate-400 font-medium">Match Score</th>
                  <th className="text-left px-4 py-3 text-slate-400 font-medium">Acknowledgement</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={`border-b border-slate-700/50 hover:bg-slate-700/20 transition-colors ${
                      item.status === 'missing' ? 'bg-red-900/10' : item.status === 'low_confidence' ? 'bg-amber-900/10' : ''
                    }`}
                  >
                    <td className="px-4 py-4 text-white font-medium">{item.machinery_name}</td>
                    <td className="px-4 py-4">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-4 text-slate-400">
                      {item.matched_manual ?? <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-4 py-4">
                      {item.match_score != null ? (
                        <div className="flex items-center gap-2">
                          <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                item.match_score >= 0.8
                                  ? 'bg-emerald-500'
                                  : item.match_score >= 0.5
                                  ? 'bg-amber-500'
                                  : 'bg-red-500'
                              }`}
                              style={{ width: `${item.match_score * 100}%` }}
                            />
                          </div>
                          <span className="text-slate-300 text-xs">
                            {Math.round(item.match_score * 100)}%
                          </span>
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <AckCell
                        item={item}
                        vesselId={vesselId!}
                        onUpdate={handleUpdate}
                        isPending={patchMutation.isPending}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Proceed button */}
      {items.length > 0 && (
        <div className="flex items-center justify-between pt-2">
          <div>
            {!canProceed && (
              <p className="text-amber-400 text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                {missingItems.length - Object.keys(ackOverrides).filter(id => missingItems.some(i => i.id === id)).length} missing item(s) still require acknowledgement before proceeding.
              </p>
            )}
          </div>
          <button
            onClick={() => navigate(`/vessels/${vesselId}/manuals`)}
            disabled={!canProceed}
            className="flex items-center gap-2 px-6 py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-medium"
          >
            Proceed to Manual Review
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}

export default PreCheck
