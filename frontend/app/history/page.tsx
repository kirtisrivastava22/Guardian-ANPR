'use client';
import { useEffect, useState } from "react"
import { History, Image, Video, Camera, Trash2, Download } from "lucide-react"

interface HistoryRecord {
  id: number
  plate_number: string
  confidence: number
  timestamp: string
  source: string
  image_path?: string
}

export default function HistoryPage() {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE;
  const [records, setRecords] = useState<HistoryRecord[]>([])
  const [filter, setFilter] = useState<string>("all")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/history/`)
      const data = await res.json()
      setRecords(data)
    } catch (error) {
      console.error("Failed to fetch history:", error)
    } finally {
      setLoading(false)
    }
  }

  const deleteRecord = async (id: number) => {
    if (!confirm("Delete this record?")) return
    
    try {
      await fetch(`${API_BASE}/history/${id}`, {
        method: "DELETE"
      })
      setRecords(prev => prev.filter(r => r.id !== id))
    } catch (error) {
      console.error("Failed to delete:", error)
    }
  }
const clearHistory = async () => {
  if (!confirm("Delete all history?")) return;

  await fetch(`${API_BASE}/history/clear`, {
    method: "DELETE"
  });

  setRecords([]);
};
  const exportCSV = () => {
    const csv = [
      "ID,Plate Number,Confidence,Source,Timestamp",
      ...filteredRecords.map(r => 
        `${r.id},${r.plate_number},${(r.confidence * 100).toFixed(1)}%,${r.source},${r.timestamp}`
      )
    ].join('\n')
    
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `history_${new Date().getTime()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filteredRecords = records.filter(r => 
    filter === "all" || r.source === filter
  )

  const getSourceIcon = (source: string) => {
    switch (source) {
      case "image": return <Image className="w-4 h-4" />
      case "video": return <Video className="w-4 h-4" />
      case "live": return <Camera className="w-4 h-4" />
      default: return null
    }
  }

  const getSourceColor = (source: string) => {
    switch (source) {
      case "image": return "text-blue-400 bg-blue-500/10 border-blue-500/30"
      case "video": return "text-purple-400 bg-purple-500/10 border-purple-500/30"
      case "live": return "text-green-400 bg-green-500/10 border-green-500/30"
      default: return "text-slate-400 bg-slate-500/10 border-slate-500/30"
    }
  }

  return (
    <>
        <div className="bg-white
  rounded-3xl
  shadow-sm
  border border-slate-200
  p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-4xl font-bold text-cyan-400 flex items-center gap-3">
            <History className="w-10 h-10" />
            Detection History
          </h1>
          <div className="flex items-center gap-4">
          <button
  onClick={clearHistory}
  className="bg-red-600 text-white px-4 py-2 rounded-lg"
>
  Delete All
</button>
          {records.length > 0 && (
            <button
              onClick={exportCSV}
              className="px-6 py-2.5 bg-cyan-600 text-white rounded-lg 
                hover:bg-cyan-700 font-medium transition-colors flex items-center gap-2"
            >
              <Download className="w-5 h-5" />
              Export CSV
            </button>
          )}
          </div>
        </div>

        <div className="bg-slate-800 backdrop-blur rounded-xl p-6 border border-slate-700 mb-6">
          <div className="flex items-center gap-4 flex-wrap">
            <span className="text-slate-300 font-medium">Live Records</span>
            {["all", "image", "video", "live"].map((src) => (
              <button
                key={src}
                onClick={() => setFilter(src)}
                className={`px-5 py-3
    rounded-xl
    text-white
    font-medium
    transition-all
    duration-300 ${
                  filter === src
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                }`}
              >
                {src.charAt(0).toUpperCase() + src.slice(1)}
              </button>
            ))}
            <div className="ml-auto text-sm text-slate-400">
              Total: {filteredRecords.length} records
            </div>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20">
            <div className="w-12 h-12 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <p className="text-slate-400">Loading history...</p>
          </div>
        ) : filteredRecords.length === 0 ? (
          <div className="bg-slate-800/50 backdrop-blur rounded-xl p-12 border border-slate-700 text-center">
            <History className="w-16 h-16 mx-auto mb-4 text-slate-600" />
            <p className="text-slate-400 text-lg">No detection records found</p>
            <p className="text-slate-500 text-sm mt-2">
              {filter !== "all" ? "Try changing the filter" : "Start detecting license plates to see history"}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredRecords.map((record) => (
              <div
                key={record.id}
                className="bg-slate-800 backdrop-blur rounded-xl border border-slate-700 hover:border-cyan-500/50 transition-all group overflow-hidden">
                {record.image_path && (
                  <div className="aspect-video bg-slate-900 relative overflow-hidden">
                    <img
                      src={`http://localhost:8000${record.image_path}`}
                      alt={record.plate_number}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none'
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 to-transparent" />
                  </div>
                )}

                <div className="p-4">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <p className="font-mono text-2xl font-bold text-white mb-2">
                        {record.plate_number}
                      </p>
                      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border ${getSourceColor(record.source)}`}>
                        {getSourceIcon(record.source)}
                        {record.source}
                      </div>
                    </div>
                    
                    <button
                      onClick={() => deleteRecord(record.id)}
                      className="p-2 px-5 py-3
    rounded-xl
    bg-red-900
    text-white
    font-medium
    hover:bg-slate-800
    transition-all
    duration-300"
                      title="Delete record"
                    >
                      <Trash2 className="w-4 h-4 text-red-400" />
                    </button>
                  </div>

                  <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-400">Confidence</span>
                      <span className="text-cyan-400 font-semibold">
                        {(record.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="w-full bg-slate-600 rounded-full h-1.5 mb-3">
                      <div
                        className="bg-cyan-500 h-1.5 rounded-full"
                        style={{ width: `${record.confidence * 100}%` }}
                      />
                    </div>
                    
                    <div className="text-slate-400 text-xs">
                      {new Date(record.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
    </>

  )
}
