import { useState } from 'react'
import { hasToken, clearToken, ApiError } from '../config/apiConfig'
import { login } from '../services/authService'

/**
 * Header login control.
 * Provides JWT authentication with quick demo credentials.
 */
export default function LoginControl() {
  const [open, setOpen] = useState(false)
  const [loggedIn, setLoggedIn] = useState(hasToken())
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('voiceshield2026')
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (u = username, p = password) => {
    setMsg('')
    setLoading(true)
    try {
      await login(u, p)
      setLoggedIn(true)
      setPassword('')
      setOpen(false)
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Login failed (network error)')
    } finally {
      setLoading(false)
    }
  }

  const handleQuickDemo = (role: 'admin' | 'analyst') => {
    if (role === 'admin') {
      setUsername('admin')
      setPassword('voiceshield2026')
      handleLogin('admin', 'voiceshield2026')
    } else {
      setUsername('analyst')
      setPassword('analyst2026')
      handleLogin('analyst', 'analyst2026')
    }
  }

  const handleLogout = () => {
    clearToken()
    setLoggedIn(false)
  }

  if (loggedIn) {
    return (
      <button
        type="button"
        onClick={handleLogout}
        className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs font-medium text-gray-300 transition hover:bg-gray-700 cursor-pointer"
      >
        Log out
      </button>
    )
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setMsg('')
          setOpen(true)
        }}
        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-700 cursor-pointer shadow-sm"
      >
        Log in
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs px-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-950 p-6 shadow-2xl space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Sign in to VoiceShield</h3>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setOpen(false)}
                className="text-gray-500 transition hover:text-white cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-gray-400">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                autoComplete="current-password"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 p-2.5 text-sm text-gray-100 placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
              />
            </div>

            <button
              type="button"
              onClick={() => handleLogin()}
              disabled={!username || !password || loading}
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50 cursor-pointer shadow-md"
            >
              {loading ? 'Authenticating...' : 'Log in'}
            </button>

            {/* Quick Demo Logins */}
            <div className="pt-3 border-t border-gray-800 text-xs">
              <span className="text-gray-400 block mb-2 font-medium">Quick 1-Click Demo Login:</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => handleQuickDemo('admin')}
                  className="px-2.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 text-indigo-300 font-medium cursor-pointer text-center"
                >
                  Admin Demo
                </button>
                <button
                  type="button"
                  onClick={() => handleQuickDemo('analyst')}
                  className="px-2.5 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 text-cyan-300 font-medium cursor-pointer text-center"
                >
                  Analyst Demo
                </button>
              </div>
              <p className="mt-2 text-[11px] text-gray-500 text-center">
                Credentials: <span className="text-gray-300 font-mono">admin / voiceshield2026</span> (or <span className="text-gray-300 font-mono">voiceguard2026</span>)
              </p>
            </div>

            {msg && <p className="text-xs text-red-400 bg-red-950/50 p-2 rounded border border-red-800">{msg}</p>}
          </div>
        </div>
      )}
    </>
  )
}
