'use client'

import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'

export default function WatchlistPage() {

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE

  const [vehicles,setVehicles] = useState([])

  const [form,setForm] = useState({
    plate:'',
    owner_name:'',
    reason:'stolen',
    description:'',
    reported_by:''
  })

  useEffect(()=>{
    loadVehicles()
  },[])

  const loadVehicles = async()=>{
    const res = await fetch(
      `${API_BASE}/watchlist`
    )

    const data = await res.json()

    setVehicles(data)
  }

  const addVehicle = async()=>{

    await fetch(
      `${API_BASE}/watchlist`,
      {
        method:'POST',
        headers:{
          'Content-Type':'application/json'
        },
        body:JSON.stringify(form)
      }
    )

    setForm({
      plate:'',
      owner_name:'',
      reason:'stolen',
      description:'',
      reported_by:''
    })

    loadVehicles()
  }

  const removeVehicle = async(id:number)=>{

    await fetch(
      `${API_BASE}/watchlist/${id}`,
      {
        method:'DELETE'
      }
    )

    loadVehicles()
  }

  return (
    <div className="max-w-7xl mx-auto">

      <h1 className="text-4xl font-bold mb-8 text-cyan-400">
        Stolen Vehicle Registry
      </h1>

      <div className="
      bg-slate-800
      text-white
      rounded-xl
      p-6
      mb-8">

        <input
          placeholder="Plate Number"
          value={form.plate}
          onChange={e=>setForm({
            ...form,
            plate:e.target.value
          })}
          className="w-full mb-3 p-3 rounded border-slate-200 text-white bg-slate-700"
        />

        <input
          placeholder="Owner"
          value={form.owner_name}
          onChange={e=>setForm({
            ...form,
            owner_name:e.target.value
          })}
          className="w-full mb-3 p-3 rounded border-slate-200 text-white bg-slate-700"
        />

        <input
          placeholder="Description"
          value={form.description}
          onChange={e=>setForm({
            ...form,
            description:e.target.value
          })}
          className="w-full mb-3 p-3 rounded border-slate-200 text-white bg-slate-700"
        />

        <button
          onClick={addVehicle}
          className="
          bg-red-600
          px-5
          py-3
          rounded-lg"
        >
          Register Vehicle
        </button>

      </div>

      <div className="space-y-4">

        {vehicles.map((v:any)=>(
          <div
            key={v.id}
            className="
            bg-slate-800
            rounded-xl
            text-white
            p-4
            flex
            justify-between"
          >

            <div>
              <div className="font-mono text-xl">
                {v.plate}
              </div>

              <div>
                {v.owner_name}
              </div>

              <div>
                {v.description}
              </div>
            </div>

            <button
              onClick={()=>
                removeVehicle(v.id)
              }
            >
              <Trash2 />
            </button>

          </div>
        ))}

      </div>

    </div>
  )
}
