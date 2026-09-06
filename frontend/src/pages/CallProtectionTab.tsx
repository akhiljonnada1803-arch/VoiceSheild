import { useState, useEffect, useRef } from 'react'
import {
  startCallProtection,
  uploadCallChunk,
  endCallProtection,
  CallStartPayload,
  CallChunkResult,
  CallEndResult,
  CallAlert,
} from '../services/callService'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'

interface RiskDataPoint {
  time: string
  chunkIndex: number
  risk: number
  score: number
  level: string
}

export default function CallProtectionTab() {
  const [callerNumber, setCallerNumber] = useState('+91 98450 12345')
  const [callType, setCallType] = useState<'inbound' | 'outbound' | 'voip'>('inbound')
  const [environment, setEnvironment] = useState<'android_recording' | 'speaker_mic' | 'voip_stream' | 'demo'>('android_recording')
  const [languageHint, setLanguageHint] = useState('en-IN')
  const [chunkDuration, setChunkDuration] = useState(3.0)

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isProtecting, setIsProtecting] = useState(false)
  const [callDuration, setCallDuration] = useState(0)
  const [currentRisk, setCurrentRisk] = useState(0)
  const [peakRisk, setPeakRisk] = useState(0)
  const [riskLevel, setRiskLevel] = useState<'safe' | 'suspicious' | 'high_risk'>('safe')
  const [riskHistory, setRiskHistory] = useState<RiskDataPoint[]>([])
  const [alerts, setAlerts] = useState<CallAlert[]>([])
  const [reasons, setReasons] = useState<string[]>([])
  const [activeModel, setActiveModel] = useState<string>('xls_r_aasist')
  const [finalVerdict, setFinalVerdict] = useState<CallEndResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Audio recording ref for mic streaming
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const timerRef = useRef<number | null>(null)

  // Call duration clock
  useEffect(() => {
    if (isProtecting) {
      timerRef.current = window.setInterval(() => {
        setCallDuration((prev) => prev + 1)
      }, 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [isProtecting])

  // Start Call Protection
  const handleStartProtection = async () => {
    try {
      setLoading(true)
      setError(null)
      setFinalVerdict(null)
      setRiskHistory([])
      setAlerts([])
      setReasons([])
      setCurrentRisk(0)
      setPeakRisk(0)
      setCallDuration(0)
      setRiskLevel('safe')

      const payload: CallStartPayload = {
        caller_number: callerNumber,
        call_type: callType,
        environment: environment,
        language_hint: languageHint,
        chunk_duration_s: chunkDuration,
      }

      const res = await startCallProtection(payload)
      setSessionId(res.session_id)
      setIsProtecting(true)

      // If user selected mic/speaker input, initialize web audio stream
      if (environment === 'speaker_mic' || environment === 'android_recording') {
        startAudioCapture(res.session_id, chunkDuration)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to start call protection')
    } finally {
      setLoading(false)
    }
  }

  // Audio capture & chunk slicer
  const startAudioCapture = async (sid: string, durationS: number) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = async (e) => {
        if (e.data.size > 0 && isProtecting) {
          try {
            const chunkRes = await uploadCallChunk(sid, e.data, `chunk_${Date.now()}.webm`)
            handleChunkResult(chunkRes)
          } catch (err) {
            console.error('Error uploading live chunk:', err)
          }
        }
      }

      recorder.start(durationS * 1000)
    } catch (err) {
      console.warn('Microphone access denied or unavailable; simulation mode active.', err)
    }
  }

  const handleChunkResult = (res: CallChunkResult) => {
    setCurrentRisk(res.current_risk_score)
    setPeakRisk(res.peak_risk_score)
    setRiskLevel(res.risk_level)
    setActiveModel(res.model_used)

    if (res.reasons && res.reasons.length > 0) {
      setReasons(res.reasons)
    }

    if (res.alerts && res.alerts.length > 0) {
      setAlerts((prev) => [...res.alerts, ...prev].slice(0, 5))
    }

    setRiskHistory((prev) => [
      ...prev,
      {
        time: `+${prev.length * Math.round(chunkDuration)}s`,
        chunkIndex: res.chunk_index,
        risk: res.current_risk_score,
        score: Math.round(res.chunk_score * 100),
        level: res.risk_level,
      },
    ])
  }

  // Manually push a test audio chunk
  const handleUploadTestChunk = async (synthetic: boolean) => {
    if (!sessionId) return
    try {
      setLoading(true)
      // Generate synthetic or natural sine-based audio buffer
      const ctx = audioContextRef.current || new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = ctx
      const length = 16000 * chunkDuration
      const buffer = ctx.createBuffer(1, length, 16000)
      const data = buffer.getChannelData(0)

      for (let i = 0; i < length; i++) {
        // High risk: noisy robotic tone; Low risk: smooth voice harmonic
        if (synthetic) {
          data[i] = 0.4 * Math.sin((2 * Math.PI * 850 * i) / 16000) + (Math.random() - 0.5) * 0.1
        } else {
          data[i] = 0.3 * Math.sin((2 * Math.PI * 220 * i) / 16000) + 0.15 * Math.sin((2 * Math.PI * 440 * i) / 16000)
        }
      }

      // Convert buffer to wav blob
      const wavBlob = audioBufferToWavBlob(buffer)
      const res = await uploadCallChunk(sessionId, wavBlob, 'test_chunk.wav')
      handleChunkResult(res)
    } catch (err: any) {
      setError(err.message || 'Chunk simulation failed')
    } finally {
      setLoading(false)
    }
  }

  // End Call Protection
  const handleEndProtection = async () => {
    if (!sessionId) return
    try {
      setLoading(true)
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
        mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop())
      }

      const res = await endCallProtection(sessionId)
      setFinalVerdict(res)
      setIsProtecting(false)
      setSessionId(null)
    } catch (err: any) {
      setError(err.message || 'Failed to end call session')
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  const getRiskColor = (level: string) => {
    if (level === 'high_risk') return 'text-red-400 bg-red-950/60 border-red-500/50'
    if (level === 'suspicious') return 'text-amber-400 bg-amber-950/60 border-amber-500/50'
    return 'text-emerald-400 bg-emerald-950/60 border-emerald-500/50'
  }

  const getRiskBg = (level: string) => {
    if (level === 'high_risk') return 'from-red-600 to-rose-700'
    if (level === 'suspicious') return 'from-amber-500 to-orange-600'
    return 'from-emerald-500 to-teal-600'
  }

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-gray-900 via-slate-900 to-indigo-950 border border-indigo-900/40 rounded-xl p-6 shadow-xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                SIH 2026 Active
              </span>
              <span className="text-gray-400 text-xs">Telecom & Banking Fraud Shield</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
              <span>Real-Time Call Protection</span>
            </h1>
            <p className="text-gray-400 text-sm max-w-xl">
              Continuously screens incoming and VoIP phone calls every 3–5 seconds to detect AI-generated voice clones,
              CEO wire fraud, and banking KYC vishing attacks.
            </p>
          </div>

          {!isProtecting ? (
            <button
              onClick={handleStartProtection}
              disabled={loading}
              className="px-6 py-3.5 rounded-xl font-bold text-white bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 shadow-lg shadow-emerald-950/50 hover:shadow-emerald-900/80 transition-all flex items-center justify-center gap-2 text-base cursor-pointer disabled:opacity-50"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <span>{loading ? 'Initializing Shield...' : 'Protect This Call'}</span>
            </button>
          ) : (
            <button
              onClick={handleEndProtection}
              disabled={loading}
              className="px-6 py-3.5 rounded-xl font-bold text-white bg-gradient-to-r from-red-600 to-rose-700 hover:from-red-500 hover:to-rose-600 shadow-lg shadow-red-950/50 transition-all flex items-center justify-center gap-2 text-base cursor-pointer disabled:opacity-50 animate-pulse"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M5 3a2 2 0 00-2 2v1c0 8.284 6.716 15 15 15h1a2 2 0 002-2v-3.28a1 1 0 00-.684-.948l-4.493-1.498a1 1 0 00-1.21.502l-1.13 2.257a11.042 11.042 0 01-5.516-5.517l2.257-1.128a1 1 0 00.502-1.21L9.228 3.683A1 1 0 008.279 3H5z" />
              </svg>
              <span>End Call Protection</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-950/50 border border-red-800 rounded-lg text-red-300 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Call Metadata & Setup */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            Call Session Configuration
          </h2>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Caller Phone / VoIP ID</label>
              <input
                type="text"
                value={callerNumber}
                onChange={(e) => setCallerNumber(e.target.value)}
                disabled={isProtecting}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Call Direction</label>
                <select
                  value={callType}
                  onChange={(e) => setCallType(e.target.value as any)}
                  disabled={isProtecting}
                  className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                >
                  <option value="inbound">Inbound (Incoming)</option>
                  <option value="outbound">Outbound</option>
                  <option value="voip">VoIP Call</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">Language Hint</label>
                <select
                  value={languageHint}
                  onChange={(e) => setLanguageHint(e.target.value)}
                  disabled={isProtecting}
                  className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
                >
                  <option value="en-IN">Indian English</option>
                  <option value="hi-IN">Hindi</option>
                  <option value="te-IN">Telugu</option>
                  <option value="ta-IN">Tamil</option>
                  <option value="multi">Multilingual</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Audio Ingestion Mode</label>
              <select
                value={environment}
                onChange={(e) => setEnvironment(e.target.value as any)}
                disabled={isProtecting}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-indigo-500"
              >
                <option value="android_recording">Android Call Recorder (Dual Stream)</option>
                <option value="speaker_mic">Microphone / Speaker Audio</option>
                <option value="voip_stream">VoIP SIP / Media Stream</option>
                <option value="demo">Demo Simulation Mode</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Chunk Analysis Window: {chunkDuration}s
              </label>
              <input
                type="range"
                min="1.0"
                max="5.0"
                step="0.5"
                value={chunkDuration}
                onChange={(e) => setChunkDuration(parseFloat(e.target.value))}
                disabled={isProtecting}
                className="w-full accent-indigo-500"
              />
            </div>
          </div>

          {/* Active Call Status Card */}
          {isProtecting && (
            <div className="mt-4 p-4 bg-gray-950 border border-indigo-900/50 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs text-emerald-400 font-semibold uppercase">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                  Live Call Active
                </span>
                <span className="font-mono text-white text-sm font-bold">{formatTime(callDuration)}</span>
              </div>
              <div className="text-xs text-gray-400">
                Session ID: <span className="font-mono text-gray-300">{sessionId}</span>
              </div>
              <div className="text-xs text-gray-400">
                Active AI Detector: <span className="font-semibold text-indigo-300">{activeModel}</span>
              </div>

              {/* Simulation Chunk Triggers */}
              <div className="pt-2 border-t border-gray-800 space-y-2">
                <span className="text-[11px] font-medium text-gray-400 block">Inject Simulated Audio Chunk:</span>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => handleUploadTestChunk(false)}
                    disabled={loading}
                    className="px-2.5 py-1.5 bg-emerald-950/80 border border-emerald-700/50 text-emerald-300 hover:bg-emerald-900 rounded text-xs font-medium cursor-pointer"
                  >
                    + Natural Chunk
                  </button>
                  <button
                    onClick={() => handleUploadTestChunk(true)}
                    disabled={loading}
                    className="px-2.5 py-1.5 bg-red-950/80 border border-red-700/50 text-red-300 hover:bg-red-900 rounded text-xs font-medium cursor-pointer"
                  >
                    + Cloned Chunk
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Middle Column: Live Risk Gauge & Progression */}
        <div className="lg:col-span-2 space-y-6">
          {/* Risk Gauge Header Card */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
              {/* Score Meter */}
              <div className="md:col-span-1 flex flex-col items-center justify-center p-4 bg-gray-950 rounded-xl border border-gray-800 text-center">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                  Live Impersonation Risk
                </span>
                <div className="relative flex items-center justify-center">
                  <div className="text-4xl font-extrabold text-white tracking-tight">
                    {Math.round(currentRisk)}%
                  </div>
                </div>
                <div className={`mt-2 px-3 py-1 rounded-full text-xs font-bold border ${getRiskColor(riskLevel)}`}>
                  {riskLevel === 'high_risk' && 'HIGH RISK (AI CLONE)'}
                  {riskLevel === 'suspicious' && 'SUSPICIOUS (CAUTION)'}
                  {riskLevel === 'safe' && 'AUTHENTIC (SAFE)'}
                </div>
                <span className="text-[11px] text-gray-500 mt-2">Peak Call Risk: {Math.round(peakRisk)}%</span>
              </div>

              {/* Progress Bar & Recommendations */}
              <div className="md:col-span-2 space-y-4">
                <div>
                  <div className="flex justify-between text-xs text-gray-400 mb-1.5 font-medium">
                    <span>Threat Meter</span>
                    <span>{currentRisk < 40 ? 'Safe Zone' : currentRisk < 70 ? 'Suspicious Zone' : 'Threat Detected'}</span>
                  </div>
                  <div className="w-full bg-gray-950 rounded-full h-3.5 p-0.5 border border-gray-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 bg-gradient-to-r ${getRiskBg(riskLevel)}`}
                      style={{ width: `${Math.max(5, Math.min(100, currentRisk))}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500 mt-1">
                    <span>0% (Human)</span>
                    <span>40% (Threshold)</span>
                    <span>70% (Alert)</span>
                    <span>100% (Deepfake)</span>
                  </div>
                </div>

                {/* Live Explanations / Acoustic Cues */}
                <div className="bg-gray-950 p-3 rounded-lg border border-gray-800">
                  <span className="text-xs font-semibold text-gray-400 block mb-1">Acoustic Indicators:</span>
                  {reasons.length > 0 ? (
                    <ul className="space-y-1">
                      {reasons.map((r, idx) => (
                        <li key={idx} className="text-xs text-gray-300 flex items-start gap-1.5">
                          <span className="text-indigo-400 font-bold">•</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-xs text-gray-500 italic">No audio anomalies detected yet.</span>
                  )}
                </div>
              </div>
            </div>

            {/* Time-series Chart */}
            <div className="mt-6 pt-4 border-t border-gray-800">
              <span className="text-xs font-semibold text-gray-400 block mb-2">
                Call Risk Trajectory (Rolling 3s Chunks)
              </span>
              <div className="h-44 w-full">
                {riskHistory.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={riskHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8} />
                          <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <XAxis dataKey="time" stroke="#6b7280" fontSize={10} />
                      <YAxis domain={[0, 100]} stroke="#6b7280" fontSize={10} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#030712', borderColor: '#374151', borderRadius: '8px' }}
                        itemStyle={{ color: '#f3f4f6', fontSize: '12px' }}
                      />
                      <ReferenceLine y={40} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: 'Suspicious', fill: '#f59e0b', fontSize: 10 }} />
                      <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Critical', fill: '#ef4444', fontSize: 10 }} />
                      <Area type="monotone" dataKey="risk" stroke="#ef4444" strokeWidth={2} fillOpacity={1} fill="url(#riskGrad)" />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center border border-dashed border-gray-800 rounded-lg text-gray-500 text-xs">
                    Start call protection to view real-time risk graphs.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Active Advisories & Fraud Alerts */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-2">
              <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Active Banking & Telecom Advisories
            </h2>

            {alerts.length > 0 ? (
              <div className="space-y-3">
                {alerts.map((a, idx) => (
                  <div
                    key={idx}
                    className={`p-4 rounded-xl border ${
                      a.severity === 'critical'
                        ? 'bg-red-950/40 border-red-800/80 text-red-200'
                        : 'bg-amber-950/40 border-amber-800/80 text-amber-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm">{a.headline}</span>
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/40">
                        {a.severity}
                      </span>
                    </div>
                    <p className="text-xs opacity-90 mb-2">{a.message}</p>
                    {a.actions && a.actions.length > 0 && (
                      <div className="bg-black/30 p-2.5 rounded-lg space-y-1">
                        <span className="text-[11px] font-semibold block text-white">Recommended Actions:</span>
                        <ul className="space-y-1">
                          {a.actions.map((act, aIdx) => (
                            <li key={aIdx} className="text-xs text-gray-300 flex items-start gap-1">
                              <span>⚠️</span>
                              <span>{act}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-gray-950 rounded-xl border border-gray-800 text-gray-500 text-xs">
                No security alerts triggered. Call is safe.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Call Finalized Summary Modal / Card */}
      {finalVerdict && (
        <div className="p-6 bg-gradient-to-r from-gray-900 to-indigo-950 border border-indigo-500/40 rounded-xl space-y-4 shadow-2xl">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>Call Protection Report</span>
            </h3>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getRiskColor(finalVerdict.final_risk_level)}`}>
              {finalVerdict.final_risk_level.toUpperCase()}
            </span>
          </div>

          <p className="text-sm text-gray-200 font-medium">{finalVerdict.summary_verdict}</p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-gray-400 block">Total Chunks</span>
              <span className="text-base font-bold text-white">{finalVerdict.total_chunks}</span>
            </div>
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-gray-400 block">Call Duration</span>
              <span className="text-base font-bold text-white">{finalVerdict.total_duration_s}s</span>
            </div>
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-gray-400 block">Peak Risk</span>
              <span className="text-base font-bold text-red-400">{finalVerdict.peak_risk_score}%</span>
            </div>
            <div className="p-3 bg-gray-950 rounded-lg border border-gray-800">
              <span className="text-gray-400 block">Alerts Fired</span>
              <span className="text-base font-bold text-amber-400">{finalVerdict.alerts_triggered_count}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Utility to convert AudioBuffer to WAV Blob
function audioBufferToWavBlob(buffer: AudioBuffer): Blob {
  const numOfChan = buffer.numberOfChannels
  const length = buffer.length * numOfChan * 2 + 44
  const out = new DataView(new ArrayBuffer(length))
  const channels: Float32Array[] = []
  let sampleRate = buffer.sampleRate
  let offset = 0
  let pos = 0

  function setUint16(data: number) {
    out.setUint16(pos, data, true)
    pos += 2
  }
  function setUint32(data: number) {
    out.setUint32(pos, data, true)
    pos += 4
  }

  // RIFF identifier
  setUint32(0x46464952) // "RIFF"
  setUint32(length - 8) // file length - 8
  setUint32(0x45564157) // "WAVE"

  // fmt sub-chunk
  setUint32(0x20746d66) // "fmt "
  setUint32(16) // SubChunk1Size (16 for PCM)
  setUint16(1) // Linear PCM
  setUint16(numOfChan)
  setUint32(sampleRate)
  setUint32(sampleRate * 2 * numOfChan) // byte rate
  setUint16(numOfChan * 2) // block align
  setUint16(16) // bits per sample

  // data sub-chunk
  setUint32(0x61746164) // "data"
  setUint32(length - pos - 4)

  for (let i = 0; i < buffer.numberOfChannels; i++) {
    channels.push(buffer.getChannelData(i))
  }

  while (offset < buffer.length) {
    for (let i = 0; i < numOfChan; i++) {
      let sample = Math.max(-1, Math.min(1, channels[i][offset]))
      sample = (0.5 + sample < 0 ? sample * 32768 : sample * 32767) | 0
      out.setInt16(pos, sample, true)
      pos += 2
    }
    offset++
  }

  return new Blob([out.buffer], { type: 'audio/wav' })
}
