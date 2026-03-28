import { useState } from 'react'
import axios from 'axios'
import SearchBar from './components/searchbar'
import ResultCard from './components/resultcard'
import History from './components/history'

const API = 'http://verifii-backend.onrender.com/verifylhost:8000/verify'

function App() {
  const [activeTab, setActiveTab] = useState('search')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSearch(query) {
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await axios.post(`${API}/verify`, { query })
      setResult(res.data)
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        'Something went wrong. Is the backend running?'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* ── Header ── */}
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              Verifii
            </h1>
          </div>
          <span className="text-xs text-slate-500 hidden sm:block">
            AI-Powered Supplier Verification
          </span>
        </div>
      </header>

      {/* ── Main Content ── */}
      <main className="flex-1 max-w-3xl mx-auto w-full px-4 py-6">
        {/* Tab Navigation */}
        <div className="flex gap-1 bg-slate-900 rounded-xl p-1 mb-6">
          <button
            onClick={() => setActiveTab('search')}
            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'search'
                ? 'bg-slate-800 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <span className="flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Search
            </span>
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${
              activeTab === 'history'
                ? 'bg-slate-800 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-300'
            }`}
          >
            <span className="flex items-center justify-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              History
            </span>
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'search' && (
          <div>
            <SearchBar onSearch={handleSearch} loading={loading} />

            {/* Loading State */}
            {loading && (
              <div className="mt-8 flex flex-col items-center gap-3">
                <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-slate-400 text-sm">
                  Analyzing supplier — this may take up to a minute...
                </p>
              </div>
            )}

            {/* Error State */}
            {error && (
              <div className="mt-6 p-4 bg-red-900/30 border border-red-700/50 rounded-xl">
                <p className="text-red-400 text-sm flex items-start gap-2">
                  <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  {error}
                </p>
              </div>
            )}

            {/* Result */}
            {result && !loading && <ResultCard result={result} />}
          </div>
        )}

        {activeTab === 'history' && <History />}
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-800 py-4">
        <p className="text-center text-slate-600 text-xs">
          Verifii · Open Source · Powered by Groq
        </p>
      </footer>
    </div>
  )
}

export default App
