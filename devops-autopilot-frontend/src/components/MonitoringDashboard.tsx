import React, { useEffect, useRef, useState } from "react";
import {
  Activity, AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp,
  Clock, Cpu, ExternalLink, HeartPulse, Info, Layers, PlayCircle, RefreshCw,
  Square, Terminal, Wifi, WifiOff, XCircle, Zap, Box, Container,
} from "lucide-react";
import { apiClient, streamMonitorLogs } from "../api/client";

interface MonitoringDashboardProps { projectId: string; }

interface PodInfo {
  name: string; namespace: string; status: string; ready: boolean;
  restart_count: number; pod_ip?: string; node?: string;
  labels?: Record<string, string>; created_at?: string; waiting_reason?: string;
}
interface K8sEvent {
  type: string; reason: string; message: string; timestamp: string;
  count: number; object_kind?: string; object_name?: string;
}
interface MonitorStatus {
  success: boolean; project_name: string; deployment_name: string;
  namespace?: string; overall_healthy: boolean;
  kubernetes: {
    healthy: boolean; state: string; reason: string; restart_count: number;
    pod_name?: string; replicas?: number; ready_replicas?: number; health?: string;
  };
  aws: { status: string; healthy: boolean };
  pods: PodInfo[]; recent_events: K8sEvent[];
  deployment_status: string; deployment?: Record<string, any>;
}

// ── helpers ────────────────────────────────────────────────────────────────
function stateColor(s: string) {
  const l = s.toLowerCase();
  if (l.includes("running")) return "text-emerald-400";
  if (l.includes("pending") || l.includes("waiting")) return "text-yellow-400";
  if (l.includes("crash") || l.includes("error") || l.includes("terminated") || l.includes("failed")) return "text-red-400";
  return "text-gray-400";
}
function stateBg(s: string) {
  const l = s.toLowerCase();
  if (l.includes("running")) return "bg-emerald-500/10 border-emerald-500/25 text-emerald-300";
  if (l.includes("pending") || l.includes("waiting")) return "bg-yellow-500/10 border-yellow-500/25 text-yellow-300";
  if (l.includes("crash") || l.includes("error") || l.includes("failed")) return "bg-red-500/10 border-red-500/25 text-red-300";
  return "bg-white/5 border-white/10 text-gray-400";
}
function healthBadge(h: string) {
  const map: Record<string, string> = {
    HEALTHY: "bg-emerald-500/10 border-emerald-500/30 text-emerald-300",
    DEGRADED: "bg-yellow-500/10 border-yellow-500/30 text-yellow-300",
    FAILED: "bg-red-500/10 border-red-500/30 text-red-300",
    SCALING: "bg-blue-500/10 border-blue-500/30 text-blue-300",
    RECOVERING: "bg-orange-500/10 border-orange-500/30 text-orange-300",
    PENDING: "bg-gray-500/10 border-gray-500/20 text-gray-400",
    UNKNOWN: "bg-white/5 border-white/10 text-gray-500",
  };
  return map[h] || map.UNKNOWN;
}
function logColor(line: string) {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("fatal") || l.includes("exception")) return "text-red-400";
  if (l.includes("warn")) return "text-yellow-300";
  if (l.includes("info") || /^\d{4}-\d{2}-\d{2}/.test(l)) return "text-gray-300";
  return "text-gray-400";
}
function age(ts: string) {
  if (!ts) return "—";
  const s = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

// ── stat card ─────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, accent = "cyan" }: {
  icon: React.ReactNode; label: string; value: React.ReactNode; sub?: string; accent?: string;
}) {
  const accentMap: Record<string, string> = {
    cyan: "from-cyan-500/20 to-cyan-500/5 border-cyan-500/20",
    green: "from-emerald-500/20 to-emerald-500/5 border-emerald-500/20",
    red: "from-red-500/20 to-red-500/5 border-red-500/20",
    yellow: "from-yellow-500/20 to-yellow-500/5 border-yellow-500/20",
    purple: "from-violet-500/20 to-violet-500/5 border-violet-500/20",
    blue: "from-blue-500/20 to-blue-500/5 border-blue-500/20",
  };
  return (
    <div className={`rounded-2xl bg-gradient-to-br ${accentMap[accent] || accentMap.cyan} border p-4`}>
      <div className="flex items-center justify-between mb-3">{icon}
        <span className="text-[9px] font-black uppercase tracking-widest text-gray-600">{label}</span>
      </div>
      <p className="text-2xl font-black text-white truncate">{value}</p>
      {sub && <p className="text-[10px] text-gray-600 mt-1 truncate">{sub}</p>}
    </div>
  );
}

// ── section wrapper ───────────────────────────────────────────────────────
function Section({ title, icon, badge, children, defaultOpen = true }: {
  title: string; icon: React.ReactNode; badge?: React.ReactNode;
  children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl bg-[#0a0f1a] border border-white/[0.06] overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02] transition-all"
        onClick={() => setOpen(v => !v)}
      >
        <div className="flex items-center gap-2.5">
          {icon}
          <span className="text-xs font-black uppercase tracking-widest text-white">{title}</span>
          {badge}
        </div>
        {open ? <ChevronUp size={13} className="text-gray-600" /> : <ChevronDown size={13} className="text-gray-600" />}
      </button>
      {open && <div className="border-t border-white/[0.05]">{children}</div>}
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────
export const MonitoringDashboard: React.FC<MonitoringDashboardProps> = ({ projectId }) => {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [logs, setLogs] = useState<{ ts: string; line: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [healing, setHealing] = useState(false);
  const [error, setError] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [appUrl, setAppUrl] = useState<string | null>(null);
  const [portForwardActive, setPortForwardActive] = useState(false);
  const [accessLoading, setAccessLoading] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const fetchStatus = async () => {
    try {
      const data = await apiClient.getMonitorStatus(projectId);
      if (data.success) { setStatus(data); setError(""); }
      else setError(data.message || "Failed to fetch status");
    } catch (e: any) { setError(e.message || "Cannot reach backend"); }
    finally { setLoading(false); setLastRefresh(new Date()); }
  };

  const fetchAccessUrl = async () => {
    setAccessLoading(true);
    try {
      const data = await apiClient.getAccessUrl(projectId);
      if (data.url) {
        setAppUrl(data.url);
        setPortForwardActive(data.port_forward_active);
      }
    } catch { /* silently ignore — app may not be deployed yet */ }
    finally { setAccessLoading(false); }
  };

  useEffect(() => { fetchStatus(); const t = setInterval(fetchStatus, 8000); return () => clearInterval(t); }, [projectId]);
  useEffect(() => { fetchAccessUrl(); }, [projectId]);
  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);
  useEffect(() => () => { esRef.current?.close(); }, []);

  const handleHeal = async () => {
    setHealing(true);
    try {
      const res = await apiClient.healProject(projectId);
      if (res.success) { await fetchStatus(); }
      else setError(res.message);
    } catch (e: any) { setError(e.message); }
    finally { setHealing(false); }
  };

  const toggleStream = () => {
    if (streaming) {
      esRef.current?.close(); esRef.current = null; setStreaming(false);
    } else {
      setLogs([]);
      const ts = () => new Date().toLocaleTimeString([], { hour12: false });
      const src = streamMonitorLogs(
        projectId,
        (line) => setLogs(p => [...p, { ts: ts(), line }].slice(-300)),
        () => setStreaming(false),
      );
      esRef.current = src; setStreaming(true);
    }
  };

  if (loading && !status) return (
    <div className="flex flex-col items-center justify-center h-full min-h-[400px] gap-3 text-gray-600">
      <RefreshCw size={24} className="animate-spin text-cyan-500" />
      <p className="text-xs font-mono uppercase tracking-widest">Connecting to cluster...</p>
    </div>
  );

  const pods = status?.pods || [];
  const events = status?.recent_events || [];
  const runningPods = pods.filter(p => p.status.toLowerCase().includes("running"));
  const warningEvents = events.filter(e => e.type === "Warning");
  const k8s = (status?.kubernetes || {}) as Partial<NonNullable<MonitorStatus["kubernetes"]>>;
  const healthy = status?.overall_healthy ?? false;
  const health = k8s.health || (healthy ? "HEALTHY" : "UNKNOWN");

  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto custom-scroll pr-1">

      {/* ── Header strip ────────────────────────────────────────────────── */}
      <div className="rounded-2xl bg-[#0a0f1a] border border-white/[0.06] px-5 py-3.5 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className={`w-2.5 h-2.5 rounded-full ${healthy ? "bg-emerald-500 shadow-[0_0_10px_rgba(52,211,153,0.8)]" : "bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.6)]"} animate-pulse`} />
          <div>
            <p className="text-sm font-black text-white uppercase tracking-widest">
              {status?.project_name || "Monitoring"}
            </p>
            <p className="text-[10px] text-gray-600 font-mono">
              {status?.deployment_name || "—"}
              {status?.namespace && <span className="ml-2 text-gray-700">ns/{status.namespace}</span>}
            </p>
          </div>
          <span className={`ml-2 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border flex items-center gap-1.5 ${healthBadge(health)}`}>
            {healthy ? <Wifi size={9} /> : <WifiOff size={9} />}
            {health}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-700 font-mono flex items-center gap-1">
            <Clock size={9} />{lastRefresh.toLocaleTimeString([], { hour12: false })}
          </span>

          {/* ── Open App Button ── */}
          {appUrl ? (
            <a
              href={appUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-[10px] font-black uppercase tracking-widest hover:bg-emerald-500/20 transition-all group"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${portForwardActive ? "bg-emerald-400 animate-pulse shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-yellow-400"}`} />
              Open App
              <ExternalLink size={9} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </a>
          ) : (
            <button
              onClick={fetchAccessUrl}
              disabled={accessLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/5 border border-white/10 text-gray-500 text-[10px] font-black uppercase tracking-widest hover:text-white transition-all disabled:opacity-40"
            >
              {accessLoading ? <RefreshCw size={9} className="animate-spin" /> : <ExternalLink size={9} />}
              {accessLoading ? "Connecting..." : "Get URL"}
            </button>
          )}

          <button
            onClick={handleHeal} disabled={healing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-orange-500/10 border border-orange-500/25 text-orange-300 text-[10px] font-black uppercase tracking-widest hover:bg-orange-500/20 transition-all disabled:opacity-40"
          >
            <HeartPulse size={10} className={healing ? "animate-pulse" : ""} />
            {healing ? "Healing..." : "Auto-Heal"}
          </button>
          <button onClick={fetchStatus} className="w-7 h-7 flex items-center justify-center rounded-xl bg-white/5 border border-white/10 text-gray-500 hover:text-white transition-all">
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-red-500/8 border border-red-500/20 rounded-xl text-xs text-red-400 flex-shrink-0">
          <AlertCircle size={13} />{error}
        </div>
      )}

      {/* ── Stat cards ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-shrink-0">
        <StatCard icon={<Box size={16} className="text-cyan-400" />} label="Total Pods" value={pods.length} sub={`${runningPods.length} running`} accent="cyan" />
        <StatCard
          icon={<Activity size={16} className={stateColor(k8s.state || "")} />}
          label="Pod State" value={k8s.state || "Unknown"}
          sub={`${k8s.ready_replicas ?? "?"}/${k8s.replicas ?? "?"} ready`}
          accent={k8s.state?.toLowerCase().includes("running") ? "green" : k8s.state?.toLowerCase().includes("pending") ? "yellow" : "red"}
        />
        <StatCard icon={<AlertTriangle size={16} className="text-yellow-400" />} label="Warnings" value={warningEvents.length} sub={`${events.length} total events`} accent={warningEvents.length > 0 ? "yellow" : "green"} />
        <StatCard icon={<RefreshCw size={16} className="text-violet-400" />} label="Restarts" value={k8s.restart_count ?? 0} sub="all containers" accent={(k8s.restart_count ?? 0) > 0 ? "yellow" : "green"} />
      </div>

      {/* ── Pods Table ──────────────────────────────────────────────────── */}
      <Section
        title={`Pod Status (${pods.length})`}
        icon={<Layers size={14} className="text-cyan-400" />}
        badge={runningPods.length > 0 && (
          <span className="px-2 py-0.5 rounded-full text-[9px] font-black bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            {runningPods.length} running
          </span>
        )}
      >
        {pods.length === 0 ? (
          <div className="flex items-center gap-2 px-5 py-6 text-xs text-gray-600">
            <Info size={14} />No pods found. Deploy to Kubernetes first.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-white/[0.02]">
                  {["Pod Name", "Status", "Ready", "Restarts", "Node", "IP", "Age"].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-[9px] font-black uppercase tracking-widest text-gray-600 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pods.map((pod, i) => (
                  <tr key={i} className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-all">
                    <td className="px-4 py-2.5 font-mono text-gray-300 max-w-[200px] truncate" title={pod.name}>{pod.name}</td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] font-bold ${stateBg(pod.status)}`}>
                        {pod.status.toLowerCase().includes("running") ? <CheckCircle2 size={10} /> : pod.status.toLowerCase().includes("pending") ? <Clock size={10} /> : <XCircle size={10} />}
                        {pod.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">{pod.ready ? <CheckCircle2 size={13} className="text-emerald-400" /> : <XCircle size={13} className="text-red-400" />}</td>
                    <td className="px-4 py-2.5 font-mono"><span className={pod.restart_count > 0 ? "text-yellow-400 font-bold" : "text-gray-600"}>{pod.restart_count}</span></td>
                    <td className="px-4 py-2.5 font-mono text-gray-500 text-[10px] truncate">{pod.node || "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-gray-600 text-[10px]">{pod.pod_ip || "—"}</td>
                    <td className="px-4 py-2.5 text-gray-600">{age(pod.created_at || "")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── K8s Events ──────────────────────────────────────────────────── */}
      <Section
        title={`Events (${events.length})`}
        icon={<Zap size={14} className="text-purple-400" />}
        badge={warningEvents.length > 0 && (
          <span className="px-2 py-0.5 rounded-full text-[9px] font-black bg-yellow-500/10 border border-yellow-500/20 text-yellow-400">
            {warningEvents.length} warnings
          </span>
        )}
        defaultOpen={warningEvents.length > 0}
      >
        {events.length === 0 ? (
          <div className="flex items-center gap-2 px-5 py-5 text-xs text-gray-600">
            <CheckCircle2 size={13} className="text-emerald-500" />Cluster is quiet — no recent events.
          </div>
        ) : (
          <div className="max-h-[200px] overflow-y-auto custom-scroll divide-y divide-white/[0.03]">
            {[...events].reverse().map((ev, i) => (
              <div key={i} className={`flex items-start gap-3 px-4 py-2.5 ${ev.type === "Warning" ? "bg-yellow-500/[0.03]" : ""}`}>
                {ev.type === "Warning"
                  ? <AlertTriangle size={11} className="text-yellow-400 mt-0.5 shrink-0" />
                  : <Info size={11} className="text-blue-400 mt-0.5 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                    <span className={`text-[10px] font-bold ${ev.type === "Warning" ? "text-yellow-300" : "text-blue-300"}`}>{ev.reason}</span>
                    {ev.object_kind && <span className="text-[9px] text-gray-600 font-mono">{ev.object_kind}/{ev.object_name}</span>}
                    {ev.count > 1 && <span className="text-[9px] bg-white/5 text-gray-600 px-1.5 rounded-full">×{ev.count}</span>}
                    <span className="text-[9px] text-gray-700 ml-auto shrink-0">{age(ev.timestamp)}</span>
                  </div>
                  <p className="text-[10px] text-gray-400 leading-relaxed">{ev.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* ── Deployment Info ──────────────────────────────────────────────── */}
      {status?.deployment && Object.keys(status.deployment).length > 0 && (
        <Section title="Deployment Info" icon={<Container size={14} className="text-blue-400" />} defaultOpen={false}>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 p-4">
            {Object.entries(status.deployment).map(([k, v]) => (
              <div key={k} className="bg-black/20 rounded-xl p-2.5 border border-white/5">
                <p className="text-[9px] font-bold text-gray-600 uppercase mb-0.5">{k.replace(/_/g, " ")}</p>
                <p className="text-[11px] text-white font-mono truncate">{String(v)}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ── Live Pod Logs ────────────────────────────────────────────────── */}
      <div className="rounded-2xl bg-[#0a0f1a] border border-white/[0.06] overflow-hidden flex flex-col min-h-[280px]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/[0.05]">
          <div className="flex items-center gap-2">
            <Terminal size={13} className="text-cyan-400" />
            <span className="text-xs font-black uppercase tracking-widest text-white">Live Pod Logs</span>
            {streaming && (
              <span className="flex items-center gap-1 text-[9px] text-emerald-400 font-black bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />LIVE
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {streaming && <button onClick={() => setLogs([])} className="text-[10px] text-gray-600 hover:text-gray-300 font-mono border border-white/8 px-2 py-1 rounded-lg transition-all">Clear</button>}
            <button
              onClick={toggleStream}
              className={`flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest px-3 py-1.5 rounded-xl border transition-all ${streaming ? "bg-red-500/10 text-red-400 border-red-500/25 hover:bg-red-500/20" : "bg-emerald-500/10 text-emerald-400 border-emerald-500/25 hover:bg-emerald-500/20"}`}
            >
              {streaming ? <><Square size={9} /> Stop</> : <><PlayCircle size={9} /> Start Stream</>}
            </button>
          </div>
        </div>

        {/* macOS-style bar */}
        <div className="flex items-center gap-1.5 px-4 py-1.5 bg-black/30 border-b border-white/[0.04]">
          <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
          <span className="ml-2 text-[10px] text-gray-700 font-mono">kubectl logs -f {(k8s as any).pod_name || "(pod)"} --timestamps</span>
          <span className="ml-auto text-[10px] text-gray-700 font-mono">{logs.length} lines</span>
        </div>

        {/* Log body */}
        <div className="flex-1 bg-black/40 p-4 overflow-y-auto font-mono text-[11px] leading-relaxed custom-scroll">
          {logs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-700">
              <Cpu size={24} />
              <p className="text-xs">{streaming ? "Awaiting log events from pod..." : "Click 'Start Stream' to tail live pod logs"}</p>
            </div>
          ) : (
            logs.map((entry, idx) => (
              <div key={idx} className="flex gap-3 mb-0.5 hover:bg-white/[0.02] px-1 rounded group">
                <span className="text-gray-700 shrink-0 select-none w-[60px] group-hover:text-gray-500 transition-all">{entry.ts}</span>
                <span className={`${logColor(entry.line)} break-all`}>{entry.line}</span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
};
