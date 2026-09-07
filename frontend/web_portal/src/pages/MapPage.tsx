import { MapPin, Shield, Video } from 'lucide-react';
import { useStore } from '../store/useStore';
import { useState } from 'react';

export default function MapPage() {
  const cameras = useStore((s) => s.cameras);
  const zones   = useStore((s) => s.zones);
  const [selectedSector, setSelectedSector] = useState('Drass');

  return (
    <div className="space-y-4">
      {/* ── Page Header ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] p-4 rounded-2xl shadow-card transition-colors">
        <div>
          <div className="flex items-center gap-2">
            <MapPin size={18} className="text-[#22c55e] light:text-[#15803d]" />
            <h2 className="text-base font-bold text-white light:text-slate-900 font-mono">Tactical Sector Map — Sector {selectedSector}</h2>
          </div>
          <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-0.5">
            Geospatial surveillance grid, active camera nodes, and restricted perimeter boundaries
          </p>
        </div>

        <div className="flex items-center gap-2">
          {['Drass', 'Kargil', 'Siachen', 'Forward Post'].map((sec) => (
            <button
              key={sec}
              type="button"
              onClick={() => setSelectedSector(sec)}
              className={`px-3 py-1 rounded-xl text-xs font-mono font-semibold transition-all cursor-pointer ${
                selectedSector === sec
                  ? 'bg-[#13271d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] shadow-xs'
                  : 'bg-[#191c24] light:bg-slate-50 text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 border border-[#272b37] light:border-[#d3d8e3]'
              }`}
            >
              {sec}
            </button>
          ))}
        </div>
      </div>

      {/* ── Tactical Map Container ───────────────────────────────── */}
      <div className="relative w-full h-[540px] bg-[#090a0e] border border-[#272b37] light:border-[#d3d8e3] rounded-2xl overflow-hidden shadow-card flex items-center justify-center">
        {/* Topographic grid overlay */}
        <div
          className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: `linear-gradient(#22c55e 1px, transparent 1px), linear-gradient(90deg, #22c55e 1px, transparent 1px)`,
            backgroundSize: '40px 40px'
          }}
        />

        {/* Mountain contour background */}
        <img
          src="/shield_bg_artwork.png"
          alt="Terrain Map"
          className="absolute inset-0 w-full h-full object-cover opacity-20 filter contrast-125 pointer-events-none"
        />

        {/* Tactical Radar Ring */}
        <div className="absolute w-[360px] h-[360px] rounded-full border border-emerald-500/20 pointer-events-none flex items-center justify-center animate-pulse">
          <div className="w-[240px] h-[240px] rounded-full border border-emerald-500/25 flex items-center justify-center">
            <div className="w-[120px] h-[120px] rounded-full border border-emerald-500/30" />
          </div>
        </div>

        {/* Map Center Sector Node */}
        <div className="relative z-10 text-center flex flex-col items-center">
          <div className="w-12 h-12 rounded-full bg-emerald-500/20 border-2 border-emerald-400 flex items-center justify-center text-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.5)] mb-2">
            <Shield size={22} />
          </div>
          <span className="text-xs font-mono font-bold text-white bg-[#121419]/90 px-2.5 py-0.5 rounded-lg border border-[#272b37]">
            HQ Command: Sector {selectedSector}
          </span>
          <span className="text-[10px] font-mono text-emerald-400 mt-1 font-semibold">
            {cameras.length} Active Feeds • {Object.keys(zones).length} Monitored Zones
          </span>
        </div>

        {/* Camera Markers */}
        {cameras.map((cam, idx) => {
          const angles = [45, 135, 225, 315, 90, 180, 270];
          const angle = (angles[idx % angles.length] * Math.PI) / 180;
          const radius = 160;
          const left = 50 + (radius * Math.cos(angle)) / 6;
          const top = 50 + (radius * Math.sin(angle)) / 4.5;

          return (
            <div
              key={cam.id}
              style={{ left: `${left}%`, top: `${top}%` }}
              className="absolute z-20 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center group cursor-pointer"
            >
              <div className="w-8 h-8 rounded-full bg-[#121419] border border-[#22c55e]/60 flex items-center justify-center text-[#22c55e] shadow-md group-hover:scale-110 transition-transform">
                <Video size={14} />
              </div>
              <span className="text-[9px] font-mono font-bold text-white bg-black/80 px-1.5 py-0.5 rounded-md mt-1 border border-white/10 whitespace-nowrap">
                {cam.name}
              </span>
            </div>
          );
        })}

        {/* Tactical Legend Panel */}
        <div className="absolute bottom-4 left-4 bg-[#121419]/95 border border-[#272b37] rounded-xl p-3 text-xs space-y-1.5 shadow-xl font-mono">
          <div className="text-[10px] text-[#9aa2b5] uppercase tracking-wider font-bold mb-1">Perimeter Status</div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-white text-[11px]">Active Camera Node</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-white text-[11px]">Restricted Zone Boundary</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span className="text-white text-[11px]">Loitering Alert Buffer</span>
          </div>
        </div>
      </div>
    </div>
  );
}
