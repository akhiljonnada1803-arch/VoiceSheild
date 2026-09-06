import { useState, useRef } from 'react'
import {
  startCallProtection,
  uploadCallChunk,
  endCallProtection,
  CallChunkResult,
  CallAlert,
} from '../services/callService'

interface DemoScenario {
  id: string
  title: string
  caller: string
  organization: string
  threatType: 'Genuine' | 'CEO Wire Fraud' | 'Bank KYC / OTP Scam'
  description: string
  chunks: {
    fake: boolean
    text: string
    freq: number
  }[]
}

const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: 'ceo_fraud',
    title: 'Executive Voice Clone Wire Fraud',
    caller: '+91 98110 99887 (Spoofed CEO ID)',
    organization: 'FinTech Corporate Office',
    threatType: 'CEO Wire Fraud',
    description:
      'Impersonates the Managing Director calling the finance lead, citing an emergency offshore vendor settlement of ₹25,00,000.',
    chunks: [
      { fake: false, text: '"Hello Rahul, are you at your desk right now?"', freq: 300 },
      { fake: true, text: '"We have an urgent acquisition closing in 20 minutes. I need you to initiate an RTGS transfer immediately."', freq: 880 },
      { fake: true, text: '"I will send account details on WhatsApp now. Bypass regular dual-approval, I will sign the voucher later."', freq: 940 },
    ],
  },
  {
    id: 'bank_kyc',
    title: 'HDFC / SBI KYC Expiry & OTP Vishing',
    caller: '+91 80034 56789 (Fake Bank Tollfree)',
    organization: 'Retail Banking Customer',
    threatType: 'Bank KYC / OTP Scam',
    description:
      'AI clone of a bank compliance officer claiming the user’s debit card and net banking will be suspended unless the OTP is read out.',
    chunks: [
      { fake: true, text: '"Greetings, this is Bank Verification Cell. Your account KYC has expired."', freq: 750 },
      { fake: true, text: '"We have generated a 6-digit verification code to your registered mobile number."', freq: 850 },
      { fake: true, text: '"Please read out the code immediately to prevent permanent account suspension."', freq: 920 },
    ],
  },
  {
    id: 'genuine_manager',
    title: 'Authentic Branch Manager Call',
    caller: '+91 94440 12345 (Verified Official)',
    organization: 'Regional Operations',
    threatType: 'Genuine',
    description:
      'Legitimate internal call discussing routine branch logistics with authentic human vocal tract acoustics.',
    chunks: [
      { fake: false, text: '"Hi team, let us reschedule the quarterly audit meeting to Thursday afternoon."', freq: 220 },
      { fake: false, text: '"Please review the operational checklist and email the signed PDF copy."', freq: 240 },
      { fake: false, text: '"Thanks everyone, see you at the review meeting tomorrow."', freq: 210 },
    ],
  },
]

export default function DemoCallTab() {
  const [selectedScenario, setSelectedScenario] = useState<DemoScenario>(DEMO_SCENARIOS[0])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [activeChunkIndex, setActiveChunkIndex] = useState<number>(-1)
  const [riskScore, setRiskScore] = useState<number>(0)
  const [riskLevel, setRiskLevel] = useState<string>('safe')
  const [alerts, setAlerts] = useState<CallAlert[]>([])
  const [reasons, setReasons] = useState<string[]>([])
  const [logs, setLogs] = useState<string[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)

  const handleRunSimulation = async () => {
    try {
      setIsRunning(true)
      setActiveChunkIndex(-1)
      setRiskScore(0)
      setRiskLevel('safe')
      setAlerts([])
      setReasons([])
      setLogs([`[INFO] Starting VoiceShield simulation for: ${selectedScenario.title}`])

      // 1. Start call protection session
      const startRes = await startCallProtection({
        caller_number: selectedScenario.caller,
        call_type: 'inbound',
        environment: 'demo',
        language_hint: 'en-IN',
        chunk_duration_s: 3.0,
      })

      setActiveSessionId(startRes.session_id)
      setLogs((prev) => [...prev, `[PROTECT] Session started (ID: ${startRes.session_id})`])

      const ctx = audioContextRef.current || new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = ctx

      // 2. Iterate through simulated chunks with realistic delays
      for (let i = 0; i < selectedScenario.chunks.length; i++) {
        setActiveChunkIndex(i)
        const chunk = selectedScenario.chunks[i]
        setLogs((prev) => [...prev, `[CHUNK ${i + 1}] Processing: ${chunk.text}`])

        // Generate synthetic or natural sine-based audio buffer
        const length = 16000 * 3.0
        const buffer = ctx.createBuffer(1, length, 16000)
        const data = buffer.getChannelData(0)

        for (let j = 0; j < length; j++) {
          if (chunk.fake) {
            data[j] = 0.45 * Math.sin((2 * Math.PI * chunk.freq * j) / 16000) + (Math.random() - 0.5) * 0.15
          } else {
            data[j] = 0.3 * Math.sin((2 * Math.PI * chunk.freq * j) / 16000) + 0.15 * Math.sin((2 * Math.PI * (chunk.freq * 2) * j) / 16000)
          }
        }

        const wavBlob = audioBufferToWavBlob(buffer)
        const chunkRes: CallChunkResult = await uploadCallChunk(startRes.session_id, wavBlob, `sim_chunk_${i}.wav`)

        setRiskScore(chunkRes.current_risk_score)
        setRiskLevel(chunkRes.risk_level)
        if (chunkRes.reasons?.length) setReasons(chunkRes.reasons)
        if (chunkRes.alerts?.length) setAlerts(chunkRes.alerts)

        setLogs((prev) => [
          ...prev,
          `[EVAL] Score: ${(chunkRes.chunk_score * 100).toFixed(1)}% | Call Risk: ${chunkRes.current_risk_score.toFixed(1)}% (${chunkRes.risk_level.toUpperCase()})`,
        ])

        // Sleep 2.5 seconds to simulate real-time call progression
        await new Promise((r) => setTimeout(r, 2500))
      }

      // 3. Conclude session
      const endRes = await endCallProtection(startRes.session_id, 'demo_completed')
      setLogs((prev) => [
        ...prev,
        `[SUMMARY] Call concluded. Final Risk: ${endRes.final_risk_score.toFixed(1)}% | Verdict: ${endRes.summary_verdict}`,
      ])
    } catch (err: any) {
      setLogs((prev) => [...prev, `[ERROR] Simulation failed: ${err.message}`])
    } finally {
      setIsRunning(false)
      setActiveChunkIndex(-1)
    }
  }

  const getRiskColor = (level: string) => {
    if (level === 'high_risk') return 'text-red-400 bg-red-950/60 border-red-500/50'
    if (level === 'suspicious') return 'text-amber-400 bg-amber-950/60 border-amber-500/50'
    return 'text-emerald-400 bg-emerald-950/60 border-emerald-500/50'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-gray-900 via-indigo-950 to-slate-900 border border-indigo-900/40 rounded-xl p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-2">
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            Interactive SIH 2026 Jury Showcase
          </span>
        </div>
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Live Banking & Telecom Fraud Scenarios
        </h1>
        <p className="text-gray-400 text-sm max-w-2xl mt-1">
          Demonstrates how VoiceShield responds within seconds during live phone conversations to protect Indian banking
          customers and enterprises from AI voice clone impersonations.
        </p>
      </div>

      {/* Scenario Selector */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {DEMO_SCENARIOS.map((sc) => (
          <div
            key={sc.id}
            onClick={() => !isRunning && setSelectedScenario(sc)}
            className={`p-4 rounded-xl border transition-all cursor-pointer ${
              selectedScenario.id === sc.id
                ? 'bg-indigo-950/50 border-indigo-500 shadow-lg shadow-indigo-950/50 ring-1 ring-indigo-500'
                : 'bg-gray-900 border-gray-800 hover:border-gray-700 opacity-80'
            } ${isRunning ? 'pointer-events-none' : ''}`}
          >
            <div className="flex items-center justify-between mb-2">
              <span
                className={`text-[11px] font-bold px-2 py-0.5 rounded ${
                  sc.threatType === 'Genuine'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : 'bg-red-950 text-red-400 border border-red-800'
                }`}
              >
                {sc.threatType}
              </span>
              <span className="text-xs text-gray-500 font-mono">{sc.chunks.length} Chunks</span>
            </div>
            <h3 className="text-sm font-bold text-white mb-1">{sc.title}</h3>
            <p className="text-xs text-gray-400 line-clamp-2">{sc.description}</p>
          </div>
        ))}
      </div>

      {/* Active Scenario Playground */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Script & Chunk Pipeline */}
        <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-white">{selectedScenario.title}</h2>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 font-mono">Caller: {selectedScenario.caller}</span>
                {activeSessionId && (
                  <span className="text-[10px] text-indigo-400 font-mono">({activeSessionId})</span>
                )}
              </div>
            </div>
            <button
              onClick={handleRunSimulation}
              disabled={isRunning}
              className="px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 shadow-md text-xs cursor-pointer disabled:opacity-50 flex items-center gap-2"
            >
              {isRunning ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-white animate-ping" />
                  <span>Simulating Call ({activeChunkIndex + 1}/{selectedScenario.chunks.length})...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Launch Live Simulation</span>
                </>
              )}
            </button>
          </div>

          {/* Conversation Stream */}
          <div className="space-y-2 pt-2">
            <span className="text-xs font-semibold text-gray-400 block uppercase">Conversation Audio Stream:</span>
            {selectedScenario.chunks.map((ch, idx) => (
              <div
                key={idx}
                className={`p-3 rounded-lg border text-xs transition-all ${
                  activeChunkIndex === idx
                    ? 'bg-indigo-950/80 border-indigo-500 shadow-md ring-1 ring-indigo-500 text-white'
                    : idx < activeChunkIndex
                    ? 'bg-gray-950/60 border-gray-800 text-gray-400'
                    : 'bg-gray-950 border-gray-900 text-gray-500'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-gray-300">Audio Chunk #{idx + 1} (3.0s)</span>
                  {activeChunkIndex === idx && (
                    <span className="text-[10px] text-cyan-400 font-mono animate-pulse">ANALYZING INFERENCE</span>
                  )}
                  {idx < activeChunkIndex && (
                    <span className="text-[10px] text-gray-400 font-mono">SCORED</span>
                  )}
                </div>
                <p className="italic">{ch.text}</p>
              </div>
            ))}
          </div>

          {/* Execution Logs */}
          <div className="mt-4 pt-4 border-t border-gray-800">
            <span className="text-xs font-semibold text-gray-400 block mb-1">System Execution Log:</span>
            <div className="h-32 bg-gray-950 rounded-lg p-3 font-mono text-[11px] text-gray-300 overflow-y-auto space-y-1 border border-gray-800">
              {logs.map((log, idx) => (
                <div key={idx} className="leading-tight">{log}</div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Live Risk & Actionable Advisories */}
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 text-center space-y-3">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider block">
              Live Impersonation Score
            </span>
            <div className="text-5xl font-extrabold text-white tracking-tight">
              {Math.round(riskScore)}%
            </div>
            <div className={`inline-block px-3 py-1 rounded-full text-xs font-bold border ${getRiskColor(riskLevel)}`}>
              {riskLevel === 'high_risk' && 'HIGH RISK (AI CLONE)'}
              {riskLevel === 'suspicious' && 'SUSPICIOUS'}
              {riskLevel === 'safe' && 'AUTHENTIC HUMAN'}
            </div>

            <div className="text-left bg-gray-950 p-3 rounded-lg border border-gray-800 space-y-1">
              <span className="text-xs font-semibold text-gray-400 block">Forensic Insights:</span>
              {reasons.length > 0 ? (
                reasons.map((r, i) => (
                  <div key={i} className="text-xs text-gray-300 flex items-start gap-1">
                    <span className="text-indigo-400 font-bold">•</span>
                    <span>{r}</span>
                  </div>
                ))
              ) : (
                <span className="text-xs text-gray-500 italic">No anomalies triggered.</span>
              )}
            </div>
          </div>

          {/* Advisories */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
              Real-Time Security Advisory
            </h3>
            {alerts.length > 0 ? (
              alerts.map((a, i) => (
                <div key={i} className="p-3 bg-red-950/40 border border-red-800 rounded-lg text-xs space-y-2">
                  <div className="font-bold text-red-200">{a.headline}</div>
                  <p className="text-gray-300">{a.message}</p>
                  {a.actions && (
                    <ul className="space-y-1 pt-1 border-t border-red-900/50">
                      {a.actions.map((act, j) => (
                        <li key={j} className="text-red-300 flex items-start gap-1">
                          <span>⚠️</span>
                          <span>{act}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))
            ) : (
              <div className="p-3 bg-gray-950 rounded-lg border border-gray-800 text-xs text-gray-500">
                Safe channel. No fraudulent patterns detected.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

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

  setUint32(0x46464952) // "RIFF"
  setUint32(length - 8)
  setUint32(0x45564157) // "WAVE"

  setUint32(0x20746d66) // "fmt "
  setUint32(16)
  setUint16(1)
  setUint16(numOfChan)
  setUint32(sampleRate)
  setUint32(sampleRate * 2 * numOfChan)
  setUint16(numOfChan * 2)
  setUint16(16)

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
