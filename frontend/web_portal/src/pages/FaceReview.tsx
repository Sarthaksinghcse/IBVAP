import React, { useEffect, useState } from 'react';
import { ShieldAlert, CheckCircle2, XCircle, RefreshCw, Eye } from 'lucide-react';
import * as api from '../services/api';

export function FaceReview() {
  const [clusters, setClusters] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const backendRoot = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const fetchClusters = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getUnknownFaceClusters(7, 2);
      setClusters(res.clusters || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load unknown faces');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 uppercase">Unknown Face Review</h1>
          <p className="text-sm text-slate-400 mt-1">Review and promote recurring unidentified individuals to the registry.</p>
        </div>
        <button onClick={fetchClusters} className="p-2 bg-slate-800 rounded hover:bg-slate-700">
          <RefreshCw className={`w-5 h-5 text-slate-300 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading clusters...</div>
      ) : clusters.length === 0 ? (
        <div className="text-center py-12 bg-slate-800/30 border border-slate-700 rounded-lg text-slate-400">
          No recurring unknown faces found in the selected timeframe.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clusters.map((cluster, i) => (
            <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-slate-200">Cluster {i + 1}</h3>
                  <p className="text-xs text-slate-400">Seen {cluster.sightings} times</p>
                </div>
                <div className="px-2 py-1 bg-amber-500/20 text-amber-400 border border-amber-500/40 rounded text-xs font-bold uppercase">
                  Unknown
                </div>
              </div>
              
              <div className="flex gap-2 overflow-x-auto py-2">
                {cluster.events.map((evt: any) => (
                  <div key={evt.id} className="w-16 h-16 shrink-0 bg-slate-900 border border-slate-700 rounded overflow-hidden">
                    {evt.snapshot_path ? (
                      <img src={`${backendRoot}${evt.snapshot_path}`} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <Eye className="w-6 h-6 text-slate-600" />
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="pt-3 border-t border-slate-700/50 flex items-center justify-end gap-2">
                <button className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs rounded transition">
                  Dismiss
                </button>
                <button className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded transition">
                  Promote to Target
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
