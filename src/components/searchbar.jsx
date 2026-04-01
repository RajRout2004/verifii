import { useState } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'https://verifii-backend.onrender.com'

export default function SearchBar({ onSearch, loading }) {
  const [query, setQuery] = useState('')
  const [gstinResults, setGstinResults] = useState(null)
  const [gstinLoading, setGstinLoading] = useState(false)

  const isGstin = query.trim().length === 15 && /^\d{2}/.test(query.trim())

  async function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim()) return
    setGstinResults(null)
    onSearch(query.trim())
  }

  async function handleGstinSearch() {
    if (!query.trim()) return
    setGstinLoading(true)
    setGstinResults(null)
    try {
      const res = await axios.post(`${API}/gstin-search`, { company_name: query.trim() }, { timeout: 35000 })
      setGstinResults(res.data)
    } catch (err) {
      setGstinResults({ error: 'Could not fetch GSTINs. Try again.' })
    } finally {
      setGstinLoading(false)
    }
  }

  function handleGstinClick(gstin) {
    // Only pass company name if we successfully fetched the real legal/trade name for this specific GSTIN
    const item = gstinResults?.gstins?.find(g => g.gstin === gstin)
    let companyNameToPass = ''
    if (item) {
      if (item.legal_name && item.legal_name !== 'N/A' && item.legal_name !== 'Could not fetch from registry') {
        companyNameToPass = item.legal_name
      } else if (item.trade_name && item.trade_name !== 'N/A' && item.trade_name !== (gstinResults?.company_name || '').toUpperCase()) {
        companyNameToPass = item.trade_name
      }
    }
    setQuery(gstin)
    setGstinResults(null)
    onSearch(gstin, companyNameToPass)
  }

  return (
    <div className="w-full">
      {/* Search form */}
      <form onSubmit={handleSubmit} className="w-full">
        <div className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Enter supplier name or 15-digit GSTIN..."
            className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors text-sm"
            disabled={loading || gstinLoading}
          />
          <button
            type="submit"
            disabled={loading || gstinLoading || !query.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-3 rounded-xl font-medium text-sm transition-colors whitespace-nowrap"
          >
            {loading ? 'Verifying...' : 'Verify'}
          </button>
        </div>

        {/* Tip + GSTIN search button */}
        <div className="flex items-center justify-between mt-2 px-1">
          <p className="text-slate-500 text-xs">
            {isGstin
              ? 'GSTIN detected — will verify against GST registry'
              : 'Tip: Enter company name for web research, or 15-digit GSTIN for registry lookup'}
          </p>
          {!isGstin && query.trim().length > 2 && (
            <button
              type="button"
              onClick={handleGstinSearch}
              disabled={gstinLoading || loading}
              className="text-xs text-indigo-400 hover:text-indigo-300 disabled:opacity-50 transition-colors whitespace-nowrap ml-3"
            >
              {gstinLoading ? 'Searching GSTINs...' : 'Find all GSTINs →'}
            </button>
          )}
        </div>
      </form>

      {/* GSTIN Results Panel */}
      {gstinResults && (
        <div className="mt-4 bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          {gstinResults.error ? (
            <div className="p-4 text-red-400 text-sm">{gstinResults.error}</div>
          ) : (
            <>
              <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
                <div>
                  <p className="text-white text-sm font-medium">{gstinResults.company_name}</p>
                  <p className="text-slate-500 text-xs mt-0.5">{gstinResults.note}</p>
                </div>
                <button
                  onClick={() => setGstinResults(null)}
                  className="text-slate-500 hover:text-slate-300 text-xs"
                >
                  ✕ Close
                </button>
              </div>

              {gstinResults.gstins?.length > 0 ? (
                <div className="max-h-72 overflow-y-auto">
                  {gstinResults.gstins.map((item, i) => (
                    <button
                      key={i}
                      onClick={() => handleGstinClick(item.gstin)}
                      className="w-full text-left px-4 py-3 border-b border-slate-700/50 last:border-0 hover:bg-slate-700/50 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-white text-xs font-medium font-mono">{item.gstin}</p>
                          <p className="text-slate-400 text-xs mt-0.5">{item.state}</p>
                          {item.legal_name && item.legal_name !== 'N/A' && item.legal_name !== 'Could not fetch from registry' && (
                            <p className="text-slate-500 text-xs">{item.legal_name}</p>
                          )}
                        </div>
                        <div className="text-right shrink-0 ml-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${item.status?.toLowerCase().includes('active')
                              ? 'bg-emerald-900/50 text-emerald-400'
                              : 'bg-slate-700 text-slate-400'
                            }`}>
                            {item.status || 'Unknown'}
                          </span>
                          <p className="text-indigo-400 text-xs mt-1">Click to verify →</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="p-4">
                  <p className="text-slate-400 text-sm">No GSTINs found via API.</p>
                  <p className="text-slate-500 text-xs mt-1">
                    Try entering the GSTIN directly, or proceed with company name search.
                  </p>
                  <button
                    onClick={() => { setGstinResults(null); onSearch(query.trim()) }}
                    className="mt-3 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg transition-colors"
                  >
                    Search by company name instead
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}