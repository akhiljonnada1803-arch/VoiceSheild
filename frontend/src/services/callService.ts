/**
 * VoiceShield Call Protection API client.
 * Handles active call sessions, chunk uploads, risk polling, and session lifecycle.
 */

import { apiFetch, ApiError } from '../config/apiConfig'

export interface CallStartPayload {
  caller_number: string
  call_type: 'inbound' | 'outbound' | 'voip'
  environment: 'android_recording' | 'speaker_mic' | 'voip_stream' | 'demo'
  language_hint: string
  chunk_duration_s: number
}

export interface CallStartResult {
  session_id: string
  status: string
  caller_number: string
  call_type: string
  environment: string
  started_at: number
}

export interface CallAlert {
  type: string
  severity: 'info' | 'warning' | 'critical'
  headline: string
  message: string
  actions: string[]
  timestamp: number
}

export interface CallChunkResult {
  session_id: string
  chunk_index: number
  duration_s: number
  chunk_score: number // 0.0 - 1.0 (synthetic probability)
  chunk_label: 'real' | 'fake' | 'unknown'
  model_used: string
  current_risk_score: number // 0 - 100%
  risk_level: 'safe' | 'suspicious' | 'high_risk'
  peak_risk_score: number
  reasons: string[]
  alerts: CallAlert[]
  latency_ms: number
}

export interface CallEndResult {
  session_id: string
  status: string
  caller_number: string
  total_chunks: number
  total_duration_s: number
  peak_risk_score: number
  final_risk_score: number
  final_risk_level: string
  summary_verdict: string
  alerts_triggered_count: number
}

export interface CallStatusResult {
  session_id: string
  is_active: boolean
  caller_number: string
  call_type: string
  environment: string
  total_chunks: number
  total_duration_s: number
  current_risk_score: number
  peak_risk_score: number
  risk_level: 'safe' | 'suspicious' | 'high_risk'
  recent_reasons: string[]
  recent_alerts: CallAlert[]
  risk_history: Array<{
    chunk_index: number
    timestamp: number
    chunk_score: number
    risk_score: number
    risk_level: string
    is_anomaly: boolean
  }>
}

export async function startCallProtection(payload: CallStartPayload): Promise<CallStartResult> {
  const res = await apiFetch('/call/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to start call protection' }))
    throw new ApiError(res.status, err.detail || 'Failed to start call session')
  }

  return res.json()
}

export async function uploadCallChunk(
  sessionId: string,
  audioBlob: Blob,
  filename = 'chunk.wav'
): Promise<CallChunkResult> {
  const formData = new FormData()
  formData.append('session_id', sessionId)
  formData.append('file', audioBlob, filename)

  const res = await apiFetch('/call/chunk', {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to analyze chunk' }))
    throw new ApiError(res.status, err.detail || 'Chunk analysis failed')
  }

  return res.json()
}

export async function endCallProtection(sessionId: string, reason = 'user_hung_up'): Promise<CallEndResult> {
  const res = await apiFetch(`/call/end?session_id=${encodeURIComponent(sessionId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to end call session' }))
    throw new ApiError(res.status, err.detail || 'Failed to end call session')
  }

  return res.json()
}

export async function getCallStatus(sessionId: string): Promise<CallStatusResult> {
  const res = await apiFetch(`/call/status/${encodeURIComponent(sessionId)}`)

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to fetch call status' }))
    throw new ApiError(res.status, err.detail || 'Failed to fetch call status')
  }

  return res.json()
}
