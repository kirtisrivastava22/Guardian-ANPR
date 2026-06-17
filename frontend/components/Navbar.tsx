// components/Navbar.tsx
'use client';

import Link from "next/link";
import { Camera, Image, Video, Clock, AlertTriangle } from "lucide-react";
import NotificationBell from "./NotificationBell"

export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-500 bg-slate-800 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-8">
        
        <Link
          href="/"
          className="flex items-center gap-3"
        >
          <div className="h-10 w-10 rounded-xl bg-white text-slate-900 flex items-center justify-center font-bold">
            G
          </div>

          <div>
            <h1 className="font-bold text-lg text-white">
             Guardian ANPR
            </h1>

            <p className="text-xs text-slate-200">
              Real-Time Automatic Number Plate Recognition and Alert System
            </p>
          </div>
        </Link>

        <nav className="flex items-center gap-2 text-slate-200">
          <NavItem  href="/" icon={<Camera size={18} />} label="Live" />
          <NavItem  href="/image" icon={<Image size={18} />} label="Image" />
          <NavItem  href="/video" icon={<Video size={18} />} label="Video" />
          <NavItem  href="/history" icon={<Clock size={18} />} label="History" />
          <NavItem  href="/watchlist" icon={<AlertTriangle size={18} />} label="Watchlist" />
        </nav>
        <NotificationBell />
      </div>
    </header>
  );
}

function NavItem({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="
        flex items-center gap-2
        rounded-xl px-4 py-2
        text-slate-200
        hover:bg-slate-600
        hover:text-white
        transition-all duration-300
      "
    >
      {icon}
      <span className="font-medium">{label}</span>
    </Link>
  );
}