'use client'

import { Bell } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

export default function NotificationBell() {
  const router = useRouter()

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE

  const [count, setCount] = useState(0)

  useEffect(() => {
    fetchCount()

    const interval = setInterval(
      fetchCount,
      5000
    )

    return () => clearInterval(interval)
  }, [])

  const fetchCount = async () => {
    try {
      const res = await fetch(
        `${API_BASE}/watchlist/alerts/unread-count`
      )

      const data = await res.json()

      setCount(data.count || 0)
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <button
      onClick={() => router.push('/alerts')}
      className="
      relative
      p-2
      rounded-full
      hover:bg-slate-700
      hover:text-white
      transition"
    >
      <Bell className="w-6 h-6 text-red-500" />

      {count > 0 && (
        <span
          className="
          absolute
          -top-1
          -right-1
          bg-red-500
          text-white
          text-xs
          min-w-[18px]
          h-[18px]
          flex
          items-center
          justify-center
          rounded-full"
        >
          {count}
        </span>
      )}
    </button>
  )
}
