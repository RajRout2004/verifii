import { useEffect, useState } from 'react'
import axios from 'axios'

export default function History() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get('https://verifii-backend.onrender.com/history')
      .then(res => setHistory(res.data))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false))
  }, [])

  const verdictColor = {
    GREEN:  'text-emerald-400 bg-emerald-900/30 border-emerald-700',
    YELLOW: 'text-yellow-400 bg-yellow-900/30 border-yellow-700',
    RED:    'text-red-400 bg-red-900/30 border-red-700',
  }

  if (loading) return <p className="text-slate-500 text-sm text-center mt-10">Loading history...</p>
  if (!history.length) return <p className="text-slate-500 text-sm text-center mt-10">No searches yet.</p>

  return (
    <div className="space-y-3">
      {history.map(item => (
        <div key={item.id} className="p-4 bg-slate-800 rounded-xl border border-slate-700">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <p className="text-white font-medium text-sm">{item.query}</p>
              <p className="text-slate-400 text-xs mt-1">{item.summary}</p>
            </div>
            <div className="text-right shrink-0">
              <span className={`text-xs font-semibold px-2 py-1 rounded-full border ${verdictColor[item.verdict] || verdictColor.YELLOW}`}>
                {item.verdict} · {item.trust_score}/100
              </span>
              <p className="text-slate-600 text-xs mt-1">
                {new Date(item.searched_at).toLocaleDateString('en-IN')}
              </p>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}