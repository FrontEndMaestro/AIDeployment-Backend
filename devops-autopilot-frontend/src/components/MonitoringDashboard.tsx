import React, { useEffect, useState } from "react";
import { Activity, Server, Database, AlertCircle, PlayCircle, HeartPulse, ActivitySquare } from "lucide-react";
import { apiClient, streamMonitorLogs } from "../api/client";
import { Card } from "./Card";
import { Button } from "./Button";

interface MonitoringDashboardProps {
  projectId: string;
}

interface MonitorStatus {
  success: boolean;
  project_name: string;
  deployment_name: string;
  overall_healthy: boolean;
  kubernetes: {
    healthy: boolean;
    state: string;
    reason: string;
    restart_count: number;
    pod_name?: string;
  };
  aws: {
    status: string;
    healthy: boolean;
    details: string;
  };
}

export const MonitoringDashboard: React.FC<MonitoringDashboardProps> = ({ projectId }) => {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [healing, setHealing] = useState(false);
  const [error, setError] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getMonitorStatus(projectId);
      if (data.success) {
        setStatus(data);
      } else {
        setError(data.message || "Failed to fetch status");
      }
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // refresh every 5s
    return () => clearInterval(interval);
  }, [projectId]);

  useEffect(() => {
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [eventSource]);

  const handleHeal = async () => {
    try {
      setHealing(true);
      const res = await apiClient.healProject(projectId);
      if (res.success) {
        await fetchStatus();
      } else {
        setError(res.message);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setHealing(false);
    }
  };

  const toggleLogStream = () => {
    if (isStreaming) {
      eventSource?.close();
      setEventSource(null);
      setIsStreaming(false);
    } else {
      setLogs([]);
      const source = streamMonitorLogs(
        projectId,
        (line) => {
          setLogs((prev) => [...prev, line].slice(-100)); // keep last 100 lines
        },
        (err) => {
          console.error("Log stream error:", err);
          setIsStreaming(false);
        }
      );
      setEventSource(source);
      setIsStreaming(true);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex justify-center items-center h-full p-10 bg-gray-800 rounded-lg border border-gray-700 animate-pulse">
        <Activity className="text-cyan-500 animate-spin mr-2" />
        <span className="text-gray-300">Loading monitoring data...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gray-900 rounded-lg overflow-hidden">
      {/* Header Panel */}
      <div className="bg-gray-800 p-4 border-b border-gray-700 flex justify-between items-center">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <ActivitySquare className="text-cyan-400" />
            Live Monitoring Dashboard
          </h2>
          <p className="text-xs text-gray-400 mt-1">Real-time health and logs for {status?.project_name}</p>
        </div>
        
        <div className="flex gap-2">
          {status?.kubernetes?.state === "Running" ? (
            <div className="px-3 py-1 bg-green-500/20 text-green-400 text-xs font-semibold rounded-full flex items-center gap-1 border border-green-500/30">
              <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
              Healthy
            </div>
          ) : (
            <div className="px-3 py-1 bg-red-500/20 text-red-400 text-xs font-semibold rounded-full flex items-center gap-1 border border-red-500/30">
              <span className="w-2 h-2 rounded-full bg-red-500"></span>
              Degraded
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4">
        {/* K8s Card */}
        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-white font-medium flex items-center gap-2 text-sm">
              <Server size={16} className="text-blue-400" />
              Kubernetes Cluster (Local)
            </h3>
            {status?.kubernetes?.healthy ? (
              <Activity className="text-green-400 w-4 h-4" />
            ) : (
              <AlertCircle className="text-red-400 w-4 h-4" />
            )}
          </div>
          
          <div className="space-y-3">
            <div className="flex justify-between bg-gray-900 p-2 rounded text-xs border border-gray-750">
              <span className="text-gray-400">Pod Status</span>
              <span className={`font-mono ${status?.kubernetes?.state === 'Running' ? 'text-green-400' : 'text-yellow-400'}`}>
                {status?.kubernetes?.state || "Unknown"}
              </span>
            </div>
            <div className="flex justify-between bg-gray-900 p-2 rounded text-xs border border-gray-750">
              <span className="text-gray-400">Restarts</span>
              <span className="text-white font-mono">{status?.kubernetes?.restart_count || 0}</span>
            </div>
            
            <div className="pt-2 mt-2 border-t border-gray-700 flex justify-between items-center">
              <span className="text-xs text-gray-500 truncate max-w-[150px]">{status?.deployment_name}</span>
              <Button 
                size="sm" 
                variant="danger" 
                onClick={handleHeal} 
                loading={healing}
                className="py-1 px-2 text-[10px]"
              >
                <HeartPulse size={12} className="mr-1" /> Auto-Heal
              </Button>
            </div>
          </div>
        </Card>

        {/* AWS Card */}
        <Card className="bg-gray-800 border-gray-700 p-4">
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-white font-medium flex items-center gap-2 text-sm">
              <Database size={16} className="text-orange-400" />
              AWS Cloud (Terraform)
            </h3>
            {status?.aws?.healthy ? (
              <Activity className="text-green-400 w-4 h-4" />
            ) : (
              <div className="text-gray-500 text-xs">Offline</div>
            )}
          </div>
          
          <div className="space-y-3">
             <div className="flex justify-between bg-gray-900 p-2 rounded text-xs border border-gray-750">
              <span className="text-gray-400">Deployment State</span>
              <span className="text-white font-mono">{status?.aws?.status.replace(/_/g, " ")}</span>
            </div>
            <div className="flex justify-between bg-gray-900 p-2 rounded text-xs border border-gray-750">
               <span className="text-gray-400">Details</span>
               <span className="text-gray-300 truncate max-w-[150px]">{status?.aws?.details}</span>
            </div>
          </div>
        </Card>
      </div>

      {error && (
        <div className="mx-4 mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-xs flex items-center gap-2">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* Logs section */}
      <div className="flex-1 flex flex-col px-4 pb-4 min-h-[250px]">
        <div className="flex justify-between items-center mb-2">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.8)]"></div>
            Live Application Logs (SSE)
          </h3>
          <Button 
            variant="secondary" 
            size="sm" 
            onClick={toggleLogStream}
            className={`py-1 px-3 text-xs ${isStreaming ? 'bg-red-500/20 text-red-400 border-red-500/50 hover:bg-red-500/30' : 'bg-green-500/20 text-green-400 border-green-500/50 hover:bg-green-500/30'}`}
          >
            {isStreaming ? (
               <><AlertCircle size={12} className="mr-1" /> Stop Stream</>
            ) : (
               <><PlayCircle size={12} className="mr-1" /> Start SSE Stream</>
            )}
          </Button>
        </div>
        <div className="flex-1 bg-black rounded border border-gray-700 p-3 overflow-y-auto font-mono text-[11px] custom-scroll relative">
          {logs.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center text-gray-600">
              {isStreaming ? "Awaiting log events..." : "Click 'Start SSE Stream' to fetch live pod logs."}
            </div>
          ) : (
            logs.map((log, idx) => (
              <div key={idx} className="mb-0.5 whitespace-pre-wrap break-words">
                <span className="text-gray-500 select-none mr-2">
                  {new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' })}
                </span>
                <span className={log.toLowerCase().includes("error") || log.toLowerCase().includes("exception") ? "text-red-400" : "text-gray-300"}>
                  {log}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
