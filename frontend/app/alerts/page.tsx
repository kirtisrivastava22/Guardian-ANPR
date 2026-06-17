'use client'

import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'

export default function AlertsPage() {

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE

  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    fetchAlerts()
  }, [])

  const fetchAlerts = async () => {
    const res = await fetch(
      `${API_BASE}/watchlist/alerts`
    )

    const data = await res.json()

    setAlerts(data)
  }

  const acknowledge = async (id:number) => {

    await fetch(
      `${API_BASE}/watchlist/alerts/${id}/acknowledge`,
      {
        method:'POST'
      }
    )

    fetchAlerts()
  }

  return (
    <div className="max-w-7xl mx-auto">

      <h1 className="text-4xl font-bold mb-8 flex gap-3 items-center">
        <Bell />
        Alert Notifications
      </h1>

      <div className="space-y-4">

        {alerts.map((a:any)=>(
          <div
            key={a.id}
            className="
            border
            border-red-500
            bg-red-500/10
            rounded-xl
            p-6"
          >

            <div className="text-red-400 font-bold text-xl">
              {a.detected_plate}
            </div>

            <div>
              Match Score:
              {(a.match_score*100).toFixed(1)}%
            </div>

            <div>
              Confidence:
              {(a.det_confidence*100).toFixed(1)}%
            </div>

            <div>
              Source: {a.source}
            </div>

            <div>
              {new Date(a.timestamp)
                .toLocaleString()}
            </div>

            {!a.acknowledged && (
              <button
                onClick={()=>acknowledge(a.id)}
                className="
                mt-4
                bg-red-600
                px-4
                py-2
                rounded-lg"
              >
                Mark Reviewed
              </button>
            )}

          </div>
        ))}

      </div>

    </div>
  )
}