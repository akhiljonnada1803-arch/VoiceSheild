import { useState } from 'react'
import CallProtectionTab from './pages/CallProtectionTab'
import DemoCallTab from './pages/DemoCallTab'
import DetectTab from './pages/DetectTab'
import ResultsTab from './pages/ResultsTab'
import LoginControl from './components/LoginControl'

type Tab = 'call' | 'demo' | 'detect' | 'results'

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('call')

  const tabs: { id: Tab; label: string; badge?: string }[] = [
    { id: 'call', label: 'Call Protection (Live)', badge: 'Core' },
    { id: 'demo', label: 'SIH Banking Scenarios', badge: 'Demo' },
    { id: 'detect', label: 'Audio File Forensics' },
    { id: 'results', label: 'Model Benchmarks' },
  ]

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col selection:bg-indigo-500 selection:text-white">
      {/* Header */}
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-3.5 sticky top-0 z-50 backdrop-blur bg-gray-900/90">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3.5">
            <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 via-cyan-500 to-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-950/60 p-0.5">
              <div className="w-full h-full bg-gray-950 rounded-[10px] flex items-center justify-center">
                <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-white font-extrabold text-lg tracking-tight">VoiceShield</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/40">
                  SIH 2026
                </span>
              </div>
              <span className="text-gray-400 text-xs hidden sm:block">
                Real-Time Voice-Clone & Impersonation Defense Platform
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>Banking Shield: Active</span>
            </div>
            <LoginControl />
            <span className="text-xs text-gray-500 font-mono">v2.0</span>
          </div>
        </div>
      </header>

      {/* Navigation Tab bar */}
      <nav className="bg-gray-900/60 border-b border-gray-800 px-6 backdrop-blur">
        <div className="max-w-6xl mx-auto flex gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-5 py-3.5 text-sm font-semibold transition-all border-b-2 flex items-center gap-2 cursor-pointer ${
                activeTab === tab.id
                  ? 'text-indigo-400 border-indigo-500 bg-indigo-500/5'
                  : 'text-gray-400 border-transparent hover:text-gray-200 hover:border-gray-700'
              }`}
            >
              <span>{tab.label}</span>
              {tab.badge && (
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-bold uppercase ${
                    activeTab === tab.id
                      ? 'bg-indigo-500/30 text-indigo-300'
                      : 'bg-gray-800 text-gray-400'
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 px-6 py-8">
        <div className="max-w-6xl mx-auto">
          {activeTab === 'call' && <CallProtectionTab />}
          {activeTab === 'demo' && <DemoCallTab />}
          {activeTab === 'detect' && <DetectTab />}
          {activeTab === 'results' && <ResultsTab />}
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-gray-900 border-t border-gray-800 px-6 py-4 mt-auto">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between text-xs text-gray-500 gap-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-400">VoiceShield</span>
            <span>·</span>
            <span>Smart India Hackathon 2026</span>
            <span>·</span>
            <span>Indian Telecom & Banking Security Initiative</span>
          </div>
          <span>Edge-Inference & Privacy-First Architecture (DPDP Act Compliant)</span>
        </div>
      </footer>
    </div>
  )
}
