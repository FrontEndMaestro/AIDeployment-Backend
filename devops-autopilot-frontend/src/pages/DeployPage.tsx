import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Container,
  Cloud,
  ArrowLeft,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  FilePlus2,
  FolderPlus,
  Rocket,
  Code2,
  Terminal as TerminalIcon,
  Settings,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { AIChatSidebar } from "../components/AIChatSidebar";
import { apiClient, streamAWSTerraform } from "../api/client";
import { LoadingSpinner } from "../components/LoadingSpinner";
import {
  DockerContextResponse,
  FileNode,
} from "../types/api";
import ThreeBackground from "../components/ThreeBackground";
import { MonitoringDashboard } from "../components/MonitoringDashboard";

type DeployMode = "docker" | "aws" | "monitor";

interface ChatMessage {
  role: "user" | "ai";
  content: string;
}

interface LogLine {
  line: string;
  stage: "build" | "run" | "push" | string;
  exit_code?: number;
  complete?: boolean;
}

export const DeployPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [context, setContext] = useState<DockerContextResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [logInput, setLogInput] = useState("");
  const [instructions, setInstructions] = useState("");
  const [sending, setSending] = useState(false);
  const [openFiles, setOpenFiles] = useState<string[]>([]);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [dirtyFlags, setDirtyFlags] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<boolean>(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [eventSource, setEventSource] = useState<EventSource | null>(null);
  const [refreshingTree, setRefreshingTree] = useState<boolean>(false);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const [healingInProgress, setHealingInProgress] = useState<boolean>(false);
  const [lastFailedAction, setLastFailedAction] = useState<"build" | "run" | "push" | null>(null);

  // Deploy mode toggle: docker or aws
  const [deployMode, setDeployMode] = useState<DeployMode>("docker");
  const [selectedModel, setSelectedModel] = useState<string>("gemini-2.5-flash");
  const [awsConfig, setAwsConfig] = useState({
    aws_region: "us-east-1",
    docker_repo_prefix: "",
    db_engine: "none",
    mongo_db_url: "",
    desired_count: 1,
  });
  const [awsStatus, setAwsStatus] = useState<string>("not_deployed");
  const [terraformExists, setTerraformExists] = useState<boolean>(false);
  const [terraformLogs, setTerraformLogs] = useState<{ type: string; message: string; stage?: string }[]>([]);
  const [isDeploying, setIsDeploying] = useState(false);

  const rawApiBase =
    (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8000/api";
  const apiBase = rawApiBase.endsWith("/api")
    ? rawApiBase.replace(/\/+$/, "")
    : `${rawApiBase.replace(/\/+$/, "")}/api`;
  const rootLabel = context?.project.project_name || "project";

  useEffect(() => {
    if (!projectId) return;
    const fetchContext = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getDockerContext(projectId);
        setContext(data);
        setMessages([
          {
            role: "ai",
            content:
              "Llama 3.1 is ready to validate or generate Dockerfiles. Share any extra instructions or build logs to begin.",
          },
        ]);
        setError(null);

        // Also fetch AWS prerequisites to get Docker Hub username
        try {
          const awsPrereqs = await apiClient.checkAWSPrerequisites(projectId);
          if (awsPrereqs.docker_hub_username) {
            setAwsConfig(prev => ({ ...prev, docker_repo_prefix: awsPrereqs.docker_hub_username || "" }));
          }
          if (awsPrereqs.terraform_exists) {
            setTerraformExists(true);
            setAwsStatus(awsPrereqs.aws_deployment_status || "terraform_generated");
          }
        } catch {
          // AWS prerequisites optional
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load deploy context"
        );
      } finally {
        setLoading(false);
      }
    };
    fetchContext();
  }, [projectId]);

  const refreshExplorer = async () => {
    if (!projectId) return;
    try {
      setRefreshingTree(true);
      const data = await apiClient.getDockerContext(projectId);
      setContext(data);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error
              ? `Unable to refresh explorer: ${err.message}`
              : "Unable to refresh explorer",
        },
      ]);
    } finally {
      setRefreshingTree(false);
    }
  };

  const joinPaths = (base: string | null | undefined, name: string) => {
    const cleanBase = base ? base.replace(/\/+$/, "") : "";
    const cleanName = name.replace(/^\/+/, "");
    return cleanBase ? `${cleanBase}/${cleanName}` : cleanName;
  };

  const handleSend = async () => {
    if (!projectId || !input.trim()) return;

    const messageText = input.trim();
    const logsText = logInput.trim();
    const instructionsText = instructions.trim();

    const userMsg: ChatMessage = { role: "user", content: messageText };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    setInput("");

    const { streamDockerChat } = await import("../api/client");
    const params: { message: string; logs?: string[]; instructions?: string } = {
      message: messageText,
    };
    if (logsText) {
      params.logs = logsText.split("\n").slice(-50);
    }
    if (instructionsText) {
      params.instructions = instructionsText;
    }

    let accumulatedContent = "";
    setMessages((prev) => [...prev, { role: "ai", content: "" }]);

    streamDockerChat(
      projectId,
      { ...params, model: selectedModel },
      (token) => {
        accumulatedContent += token;
        setMessages((prev) => {
          const newMessages = [...prev];
          for (let i = newMessages.length - 1; i >= 0; i--) {
            if (newMessages[i].role === "ai") {
              newMessages[i] = { role: "ai", content: accumulatedContent };
              break;
            }
          }
          return newMessages;
        });
      },
      () => {
        setSending(false);
      },
      (error) => {
        setMessages((prev) => {
          const newMessages = [...prev];
          for (let i = newMessages.length - 1; i >= 0; i--) {
            if (newMessages[i].role === "ai") {
              if (newMessages[i].content === "") {
                newMessages[i] = { role: "ai", content: `Error: ${error.message}` };
              }
              break;
            }
          }
          return newMessages;
        });
        setSending(false);
      }
    );
  };

  const appendLogs = (incoming: LogLine) => {
    setLogs((prev) => [...prev, incoming]);
  };

  // ── Auto-heal: stream LLM analysis + auto-write fixed files ────────────────
  const triggerAutoHeal = async (
    action: "build" | "run" | "push",
    allLogs: LogLine[]
  ) => {
    if (!projectId) return;
    setHealingInProgress(true);
    setLastFailedAction(action);

    const logText = allLogs
      .map((l) => `[${l.stage?.toUpperCase()}] ${l.line}`)
      .slice(-40)
      .join("\n");

    const healPrompt =
      `The Docker "${action}" step just failed. Here are the full build logs:\n\n` +
      logText +
      `\n\nPlease:\n` +
      `1. Identify the root cause of the failure.\n` +
      `2. Generate the corrected file(s) (Dockerfile, Gemfile, package.json, etc.) needed to fix it.\n` +
      `3. Output the fixed files in fenced code blocks tagged with their filename.\n` +
      `4. Briefly explain what was wrong and what you changed.`;

    setMessages((prev) => [
      ...prev,
      {
        role: "ai",
        content:
          `🔄 **Auto-Heal triggered** — ${action} exited with error.\n` +
          `Analyzing ${allLogs.length} log lines and generating fixes...`,
      },
    ]);

    const { streamDockerChat } = await import("../api/client");
    let accumulated = "";
    setMessages((prev) => [...prev, { role: "ai", content: "" }]);

    streamDockerChat(
      projectId,
      { message: healPrompt, model: selectedModel },
      (token) => {
        accumulated += token;
        setMessages((prev) => {
          const next = [...prev];
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].role === "ai") {
              next[i] = { role: "ai", content: accumulated };
              break;
            }
          }
          return next;
        });
      },
      async () => {
        setHealingInProgress(false);
        await refreshExplorer();
        setMessages((prev) => [
          ...prev,
          {
            role: "ai",
            content:
              `✅ **Auto-Heal complete.** Fixed files have been written to disk.\n` +
              `Click **🔄 Retry ${action}** in the build panel to rebuild with the fixes applied.`,
          },
        ]);
      },
      (err) => {
        setHealingInProgress(false);
        setMessages((prev) => [
          ...prev,
          { role: "ai", content: `❌ Auto-Heal failed: ${err.message}` },
        ]);
      }
    );
  };

  const startStream = (action: "build" | "run" | "push") => {
    if (!projectId) return;
    if (eventSource) eventSource.close();
    setLogs([]);
    setLastFailedAction(null);
    const token = apiClient.getToken();
    const url = new URL(`${apiBase}/docker/${projectId}/logs`);
    url.searchParams.set("action", action);
    if (token) url.searchParams.set("token", token);

    const collectedLogs: LogLine[] = [];
    const source = new EventSource(url.toString());

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const logLine: LogLine = {
          line: data.line,
          stage: data.stage,
          exit_code: data.exit_code,
          complete: data.complete,
        };
        collectedLogs.push(logLine);
        appendLogs(logLine);

        if (data.complete && typeof data.exit_code === "number") {
          source.close();
          setEventSource(null);
          if (data.exit_code !== 0) {
            triggerAutoHeal(action, collectedLogs);
          } else {
            setMessages((prev) => [
              ...prev,
              { role: "ai", content: `✅ Docker **${action}** completed successfully!` },
            ]);
          }
        }
      } catch (err) {
        appendLogs({
          line: err instanceof Error ? err.message : "Malformed log event",
          stage: action,
        });
      }
    };

    source.onerror = () => {
      appendLogs({ line: "Log stream error or closed.", stage: action });
      source.close();
      setEventSource(null);
    };

    setEventSource(source);
  };

  useEffect(() => {
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [eventSource]);

  const handleFileSelect = async (node: FileNode) => {
    if (node.is_dir || !projectId) return;
    try {
      const resp = await apiClient.readProjectFile(projectId, node.path);
      setOpenFiles((prev) =>
        prev.includes(node.path) ? prev : [...prev, node.path]
      );
      setActiveFile(node.path);
      setFileContents((prev) => ({ ...prev, [node.path]: resp.content }));
      setDirtyFlags((prev) => ({ ...prev, [node.path]: false }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unable to load file";
      setFileContents((prev) => ({ ...prev, [node.path]: msg }));
      setDirtyFlags((prev) => ({ ...prev, [node.path]: false }));
    }
  };

  const handleSaveFile = async () => {
    if (!projectId || !activeFile || !dirtyFlags[activeFile]) return;
    try {
      setSaving(true);
      await apiClient.writeProjectFile(projectId, {
        path: activeFile,
        content: fileContents[activeFile] || "",
      });
      setDirtyFlags((prev) => ({ ...prev, [activeFile]: false }));
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: `Saved ${activeFile}. Re-run build if needed.` },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error ? `Save failed: ${err.message}` : "Save failed",
        },
      ]);
    } finally {
      setSaving(false);
    }
  };

  const pruneDeletedState = (targetPath: string) => {
    const normalized = targetPath.replace(/\/+$/, "");
    const prefix = `${normalized}/`;

    setOpenFiles((prev) =>
      prev.filter(
        (p) => p !== normalized && !p.startsWith(prefix)
      )
    );
    setFileContents((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key === normalized || key.startsWith(prefix)) {
          delete next[key];
        }
      });
      return next;
    });
    setDirtyFlags((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((key) => {
        if (key === normalized || key.startsWith(prefix)) {
          delete next[key];
        }
      });
      return next;
    });
    if (activeFile && (activeFile === normalized || activeFile.startsWith(prefix))) {
      setActiveFile(null);
    }
  };

  const handleCreateFile = async (basePath?: string | null) => {
    if (!projectId) return;
    const name = window.prompt("New file name (relative to this folder)");
    if (!name || !name.trim()) return;
    const fullPath = joinPaths(basePath, name.trim());
    try {
      await apiClient.createProjectFile(projectId, fullPath, "");
      await refreshExplorer();
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: `Created file ${fullPath}` },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error ? `Create file failed: ${err.message}` : "Create file failed",
        },
      ]);
    }
  };

  const handleCreateFolder = async (basePath?: string | null) => {
    if (!projectId) return;
    const name = window.prompt("New folder name (relative to this folder)");
    if (!name || !name.trim()) return;
    const fullPath = joinPaths(basePath, name.trim());
    try {
      await apiClient.createProjectFolder(projectId, fullPath);
      await refreshExplorer();
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: `Created folder ${fullPath}` },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error ? `Create folder failed: ${err.message}` : "Create folder failed",
        },
      ]);
    }
  };

  const handleDeletePath = async (targetPath: string) => {
    if (!projectId) return;
    const confirmed = window.confirm(`Delete ${targetPath}? This cannot be undone.`);
    if (!confirmed) return;
    try {
      await apiClient.deleteProjectPath(projectId, targetPath);
      pruneDeletedState(targetPath);
      await refreshExplorer();
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: `Deleted ${targetPath}` },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error ? `Delete failed: ${err.message}` : "Delete failed",
        },
      ]);
    }
  };

  const renderFileTree = (nodes: FileNode[], depth = 0) => {
    return nodes.map((node) => (
      <div
        key={node.path}
        className={`mb-1 ${depth > 0 ? "border-l border-gray-800" : ""}`}
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        <div
          className={`flex items-center justify-between group rounded px-2 py-1 hover:bg-gray-700/50 ${!node.is_dir && activeFile === node.path ? "bg-gray-700/60 border border-cyan-600/40" : ""
            }`}
        >
          <div className="flex items-center gap-2">
            {node.is_dir ? (
              <button
                className="text-cyan-300 hover:text-white text-xs"
                onClick={() =>
                  setExpandedDirs((prev) => ({
                    ...prev,
                    [node.path]: !(prev[node.path] ?? true),
                  }))
                }
                aria-label={expandedDirs[node.path] ?? true ? "Collapse folder" : "Expand folder"}
              >
                {(expandedDirs[node.path] ?? true) ? (<ChevronDown size={12} />) : (<ChevronRight size={12} />)}
              </button>
            ) : (
              <span className="text-gray-600 text-xs">-</span>
            )}
            <button
              className={`text-left text-sm ${node.is_dir ? "text-cyan-200" : activeFile === node.path ? "text-white" : "text-gray-200"
                } hover:text-white`}
              onClick={() => (node.is_dir ? setExpandedDirs((prev) => ({ ...prev, [node.path]: !(prev[node.path] ?? true) })) : handleFileSelect(node))}
            >
              {node.name}
            </button>
          </div>
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {node.is_dir && (
              <>
                <button
                  className="text-[10px] px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-cyan-300 hover:border-cyan-500"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCreateFile(node.path);
                  }}
                  disabled={refreshingTree}
                  aria-label={`Add file in ${node.path}`}
                >
                  File
                </button>
                <button
                  className="text-[10px] px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-cyan-300 hover:border-cyan-500"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCreateFolder(node.path);
                  }}
                  disabled={refreshingTree}
                  aria-label={`Add folder in ${node.path}`}
                >
                  Dir
                </button>
              </>
            )}
            <button
              className="text-[10px] px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-red-300 hover:border-red-500"
              onClick={(e) => {
                e.stopPropagation();
                handleDeletePath(node.path);
              }}
              disabled={refreshingTree}
            >
              Delete
            </button>
          </div>
        </div>
        {node.is_dir && (expandedDirs[node.path] ?? true) && node.children && node.children.length > 0 && (
          <div className="mt-1">{renderFileTree(node.children, depth + 1)}</div>
        )}
      </div>
    ));
  };

  const metadataList = useMemo(() => {
    if (!context) return [];
    const m = context.metadata;
    return [
      { label: "Framework", value: m.framework },
      { label: "Language", value: m.language },
      { label: "Runtime", value: m.runtime },
      { label: "Port", value: m.port },
      { label: "Backend Port", value: m.backend_port },
      { label: "Frontend Port", value: m.frontend_port },
      { label: "Database", value: m.database },
      { label: "Database Port", value: m.database_port },
    ].filter((item) => item.value !== undefined && item.value !== null);
  }, [context]);

  if (loading) {
    return <LoadingSpinner message="Loading deploy workspace..." />;
  }

  if (error || !context) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 animate-fade-in" style={{ background: 'var(--bg-base)' }}>
        <div className="flex items-center gap-3 text-rose-400">
          <AlertCircle size={20} />
          <p className="text-sm font-medium">{error || 'Unable to load deploy context'}</p>
        </div>
        <Button variant="secondary" onClick={() => navigate('/dashboard')}>
          <ArrowLeft size={15} /> Back to Dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen relative overflow-hidden flex flex-col bg-[#050810]">
      <ThreeBackground />
      <div className="absolute inset-0 grid-bg opacity-30 pointer-events-none" style={{ zIndex: 1 }} />

      <div className="relative z-10 flex flex-col h-full bg-[#050810]/40">
        <Navbar />

        <main className="flex-1 max-w-[1600px] w-full mx-auto px-6 py-6 flex flex-col gap-6">

          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-black text-white tracking-tight uppercase flex items-center gap-3">
                {deployMode === "docker" ? (
                  <><Container size={28} className="text-cyan-400" /> Docker Orchestration</>
                ) : deployMode === "aws" ? (
                  <><Cloud size={28} className="text-orange-400" /> Cloud Deployment</>
                ) : (
                  <><Settings size={28} className="text-violet-400" /> Live Monitoring</>
                )}
              </h1>
              <p className="text-gray-400 mt-1 text-sm flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                Workspace: <span className="text-white font-semibold ml-1">{context.project.project_name}</span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="bg-white/5 border border-white/10 rounded-xl p-1 flex gap-1">
                {([
                  { mode: "docker", label: "🐳 Infrastructure", active: "bg-cyan-500 text-white shadow-cyan-500/20" },
                  { mode: "aws",    label: "☁️ Cloud AWS",     active: "bg-orange-500 text-white shadow-orange-500/20" },
                  { mode: "monitor",label: "📊 Monitor",       active: "bg-violet-500 text-white shadow-violet-500/20" },
                ] as const).map(({ mode, label, active }) => (
                  <button
                    key={mode}
                    onClick={() => setDeployMode(mode)}
                    className={`px-4 py-2 rounded-lg text-xs font-bold tracking-wide uppercase transition-all shadow-lg ${deployMode === mode ? active : "text-gray-400 hover:text-white"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <Button variant="secondary" onClick={() => navigate("/dashboard")}>
                <ArrowLeft size={15} /> Back
              </Button>
            </div>
          </div>

          {/* Main 3-column grid */}
          <div className="grid grid-cols-12 gap-4" style={{ height: "calc(100vh - 210px)", minHeight: "640px" }}>

            {/* ═══ LEFT: File Explorer ═══ */}
            <div className="col-span-2 flex flex-col gap-4 h-full overflow-y-auto custom-scroll">

              {/* File tree */}
              <div className="flex-1 flex flex-col bg-[#0d1117] border border-white/8 rounded-2xl overflow-hidden min-h-0">
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/8 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <Rocket size={14} className="text-cyan-400" />
                    <div>
                      <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Workspace</p>
                      <p className="text-sm font-bold text-white truncate max-w-[90px]">{rootLabel}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => refreshExplorer()}
                    disabled={refreshingTree}
                    className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-all"
                  >
                    <RefreshCw size={12} className={refreshingTree ? "animate-spin" : ""} />
                  </button>
                </div>

                <div className="flex gap-2 px-3 py-2 border-b border-white/5 flex-shrink-0">
                  <button onClick={() => handleCreateFile(null)} disabled={refreshingTree}
                    className="flex-1 flex items-center justify-center gap-1 text-xs font-semibold py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/20 transition-all">
                    <FilePlus2 size={11} /> File
                  </button>
                  <button onClick={() => handleCreateFolder(null)} disabled={refreshingTree}
                    className="flex-1 flex items-center justify-center gap-1 text-xs font-semibold py-1.5 rounded-lg bg-white/5 border border-white/10 text-gray-400 hover:text-white transition-all">
                    <FolderPlus size={11} /> Dir
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto custom-scroll p-3 min-h-0">
                  {renderFileTree(context.file_tree.tree)}
                </div>
              </div>

              {/* Stack info */}
              {metadataList.length > 0 && (
                <div className="flex-shrink-0 bg-[#0d1117] border border-white/8 rounded-2xl p-4">
                  <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3 flex items-center gap-2">
                    <Settings size={12} /> Stack Info
                  </h3>
                  <div className="flex flex-col gap-2">
                    {metadataList.map((item) => (
                      <div key={item.label} className="flex justify-between items-center py-1 border-b border-white/5 last:border-0">
                        <span className="text-xs text-gray-500 font-medium">{item.label}</span>
                        <span className="text-xs font-bold text-cyan-300 truncate max-w-[70px] text-right">{item.value as string}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* ═══ CENTER: Code Editor + Action Panel ═══ */}
            <div className="col-span-6 flex flex-col gap-4 h-full" style={{ minHeight: 0 }}>

              {deployMode === "monitor" && projectId ? (
                <MonitoringDashboard projectId={projectId} />
              ) : (
                <>
                  {/* Code Editor */}
                  <div className="flex-1 flex flex-col bg-[#0d1117] border border-white/8 rounded-2xl overflow-hidden" style={{ minHeight: 0 }}>
                    {/* Tab bar */}
                    <div className="flex-shrink-0 flex items-center gap-2 px-4 py-3 border-b border-white/8 overflow-x-auto no-scrollbar">
                      <Code2 size={14} className="text-gray-600 flex-shrink-0" />
                      {openFiles.length === 0 ? (
                        <span className="text-sm text-gray-600 italic">Open a file from the explorer →</span>
                      ) : (
                        openFiles.map((path) => (
                          <button key={path} onClick={() => setActiveFile(path)}
                            className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                              activeFile === path
                                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                                : "text-gray-500 hover:text-gray-300 hover:bg-white/5"
                            }`}>
                            {dirtyFlags[path] && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                            {path.split("/").pop()}
                          </button>
                        ))
                      )}
                    </div>

                    {/* Editor */}
                    <div className="flex-1 min-h-0">
                      <textarea
                        value={(activeFile && fileContents[activeFile]) || ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (!activeFile) return;
                          setFileContents((prev) => ({ ...prev, [activeFile]: val }));
                          setDirtyFlags((prev) => ({ ...prev, [activeFile]: true }));
                        }}
                        className="w-full h-full p-5 text-sm focus:outline-none resize-none custom-scroll font-mono leading-7 bg-transparent"
                        style={{ color: "#e6edf3" }}
                        placeholder="Select a file from the explorer to view and edit it..."
                        spellCheck={false}
                      />
                    </div>

                    {/* Footer */}
                    <div className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 border-t border-white/8 bg-black/20">
                      <span className="text-xs font-mono text-gray-500">
                        {activeFile ? `📄 ${activeFile}` : "— no file open —"}
                        {activeFile && dirtyFlags[activeFile] && (
                          <span className="ml-2 text-amber-400 font-bold">● unsaved changes</span>
                        )}
                      </span>
                      <Button variant="primary" disabled={!activeFile || !dirtyFlags[activeFile] || saving} loading={saving} onClick={handleSaveFile}>
                        💾 Save File
                      </Button>
                    </div>
                  </div>

                  {/* ─── Docker Build Panel ─── */}
                  {deployMode === "docker" && (
                    <div className={`flex-shrink-0 rounded-2xl overflow-hidden border transition-all ${
                      healingInProgress
                        ? "bg-[#0d1117] border-orange-500/40 shadow-lg shadow-orange-500/10"
                        : "bg-[#0d1117] border-cyan-500/15"
                    }`}>
                      {/* Header */}
                      <div className={`flex items-center justify-between px-4 py-3 border-b ${healingInProgress ? "border-orange-500/20 bg-orange-500/5" : "border-cyan-500/10"}`}>
                        <div className="flex items-center gap-2">
                          <TerminalIcon size={15} className={healingInProgress ? "text-orange-400" : "text-cyan-400"} />
                          <span className="text-sm font-bold text-white">Docker Build Controls</span>
                          {healingInProgress && (
                            <span className="flex items-center gap-1.5 text-xs font-bold text-orange-300 bg-orange-500/10 px-2.5 py-0.5 rounded-full border border-orange-500/25 animate-pulse">
                              <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-ping" />
                              🔄 Auto-Healing...
                            </span>
                          )}
                          {context.metadata.deploy_blocked && !healingInProgress && (
                            <span className="text-xs font-bold text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full border border-amber-400/20">
                              ⚠ Deployment Blocked
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-500 font-mono">Local Docker Desktop</span>
                      </div>

                      {/* Healing status banner */}
                      {healingInProgress && (
                        <div className="mx-4 mt-3 p-3 bg-orange-500/5 border border-orange-500/15 rounded-xl flex items-start gap-3">
                          <div className="w-5 h-5 rounded-full border-2 border-orange-400 border-t-transparent animate-spin flex-shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-bold text-orange-300">AI is analyzing the error and rewriting your files</p>
                            <p className="text-xs text-orange-400/70 mt-0.5">Watch the AI Assistant panel on the right for live progress →</p>
                          </div>
                        </div>
                      )}

                      {/* Blocker warning */}
                      {context.metadata.deploy_blocked && (
                        <div className="mx-4 mt-3 p-3 bg-amber-500/5 border border-amber-500/15 rounded-xl">
                          <p className="text-sm text-amber-300">
                            <strong>Blocker:</strong> {context.metadata.deploy_blocked_reason || "Missing environment configurations."}
                          </p>
                        </div>
                      )}

                      {/* Action buttons */}
                      <div className="grid grid-cols-3 gap-3 px-4 py-3">
                        {[
                          { action: "build", emoji: "🔨", label: "Build Image",   cls: "bg-cyan-500/10 border-cyan-500/20 text-cyan-300 hover:bg-cyan-500/20" },
                          { action: "run",   emoji: "▶",  label: "Run Container", cls: "bg-emerald-500/10 border-emerald-500/20 text-emerald-300 hover:bg-emerald-500/20" },
                          { action: "push",  emoji: "⬆",  label: "Push to Hub",   cls: "bg-violet-500/10 border-violet-500/20 text-violet-300 hover:bg-violet-500/20" },
                        ].map(({ action, emoji, label, cls }) => (
                          <button
                            key={action}
                            onClick={() => startStream(action as any)}
                            disabled={!!context.metadata.deploy_blocked || healingInProgress}
                            className={`py-3 rounded-xl text-sm font-bold border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${cls}`}
                          >
                            {emoji} {label}
                          </button>
                        ))}
                      </div>

                      {/* Retry button — shown after failed build */}
                      {lastFailedAction && !healingInProgress && (
                        <div className="px-4 pb-3">
                          <button
                            onClick={() => startStream(lastFailedAction)}
                            className="w-full py-2.5 rounded-xl text-sm font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25 transition-all flex items-center justify-center gap-2"
                          >
                            🔄 Retry {lastFailedAction} with auto-applied fixes
                          </button>
                        </div>
                      )}

                      {/* Log terminal */}
                      <div className={`mx-4 mb-4 bg-black/50 rounded-xl p-3 h-32 overflow-y-auto custom-scroll font-mono text-xs leading-relaxed border ${
                        healingInProgress ? "border-orange-500/20" : "border-white/8"
                      }`}>
                        {logs.length === 0 ? (
                          <p className="text-gray-600 italic">No logs yet — click an action above to start streaming output...</p>
                        ) : (
                          logs.map((l, idx) => (
                            <div key={idx} className="mb-0.5">
                              <span className={`mr-2 font-bold ${l.stage === "build" ? "text-cyan-400" : l.stage === "run" ? "text-emerald-400" : "text-violet-400"}`}>
                                [{l.stage?.toUpperCase()}]
                              </span>
                              <span className={l.exit_code !== undefined && l.exit_code !== 0 ? "text-rose-400" : "text-gray-300"}>
                                {l.line}
                              </span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}


                  {/* ─── AWS Cloud Panel ─── */}
                  {deployMode === "aws" && (
                    <div className="flex-shrink-0 bg-[#0d1117] border border-orange-500/15 rounded-2xl overflow-hidden">
                      {/* Header */}
                      <div className="flex items-center justify-between px-4 py-3 border-b border-orange-500/10">
                        <div className="flex items-center gap-2">
                          <Cloud size={15} className="text-orange-400" />
                          <span className="text-sm font-bold text-white">AWS Cloud Deployment</span>
                          <span className="text-xs text-gray-500">via Terraform</span>
                        </div>
                        <span className={`text-xs font-bold px-3 py-1 rounded-full border ${
                          awsStatus === "deployed"
                            ? "bg-emerald-500/10 border-emerald-500/25 text-emerald-400"
                            : awsStatus === "terraform_generated"
                            ? "bg-orange-500/10 border-orange-500/25 text-orange-400"
                            : "bg-gray-500/10 border-gray-500/20 text-gray-500"
                        }`}>
                          {awsStatus === "deployed" ? "✅ Deployed" : awsStatus === "terraform_generated" ? "📋 Ready" : "⚪ Not Deployed"}
                        </span>
                      </div>

                      {/* Config fields */}
                      <div className="grid grid-cols-2 gap-4 px-4 pt-3 pb-2">
                        <div>
                          <label className="block text-xs font-bold text-gray-500 uppercase mb-1.5">AWS Region</label>
                          <select
                            value={awsConfig.aws_region}
                            onChange={(e) => setAwsConfig(prev => ({ ...prev, aws_region: e.target.value }))}
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-orange-500/50 transition-colors"
                          >
                            <option value="us-east-1">🇺🇸 US East — N. Virginia</option>
                            <option value="us-west-2">🇺🇸 US West — Oregon</option>
                            <option value="eu-west-1">🇪🇺 EU — Ireland</option>
                            <option value="ap-southeast-1">🌏 Asia — Singapore</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-bold text-gray-500 uppercase mb-1.5">Docker Hub Username</label>
                          <input
                            type="text"
                            value={awsConfig.docker_repo_prefix}
                            onChange={(e) => setAwsConfig(prev => ({ ...prev, docker_repo_prefix: e.target.value }))}
                            placeholder="your-dockerhub-username"
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-orange-500/50 placeholder-gray-600 transition-colors"
                          />
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="grid grid-cols-2 gap-3 px-4 pb-3">
                        <button
                          onClick={async () => {
                            if (!projectId) return;
                            setIsDeploying(true);
                            setMessages(prev => [...prev, { role: "ai", content: "Generating Terraform infrastructure files..." }]);
                            try {
                              const result = await apiClient.generateTerraform(projectId, awsConfig);
                              setAwsStatus("terraform_generated");
                              setMessages(prev => [...prev, { role: "ai", content: `✅ Terraform generated at ${result.terraform_path}` }]);
                              await refreshExplorer();
                            } catch (err: any) {
                              setMessages(prev => [...prev, { role: "ai", content: `❌ Terraform failed: ${err.message}` }]);
                            }
                            setIsDeploying(false);
                          }}
                          disabled={isDeploying || !awsConfig.docker_repo_prefix}
                          className="py-3 rounded-xl text-sm font-bold bg-orange-500/10 border border-orange-500/20 text-orange-300 hover:bg-orange-500/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {isDeploying ? "⏳ Generating..." : "📋 Generate Terraform"}
                        </button>
                        <button
                          onClick={() => {
                            if (!projectId) return;
                            setIsDeploying(true);
                            streamAWSTerraform(
                              projectId, "apply",
                              (ev) => setTerraformLogs(prev => [...prev, ev]),
                              () => { setIsDeploying(false); setAwsStatus("deployed"); },
                              (err) => { setIsDeploying(false); setMessages(prev => [...prev, { role: "ai", content: err.message }]); }
                            );
                          }}
                          disabled={isDeploying || (awsStatus === "not_deployed" && !terraformExists)}
                          className="py-3 rounded-xl text-sm font-bold bg-orange-500 hover:bg-orange-600 text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-lg shadow-orange-500/20"
                        >
                          {isDeploying ? "⏳ Deploying..." : "🚀 Deploy to AWS"}
                        </button>
                      </div>

                      {/* Terraform logs */}
                      <div className="mx-4 mb-4 bg-black/50 border border-white/8 rounded-xl p-3 h-28 overflow-y-auto custom-scroll font-mono text-xs leading-relaxed">
                        {terraformLogs.length === 0 ? (
                          <p className="text-gray-600 italic">No Terraform logs yet — generate or deploy to see output...</p>
                        ) : (
                          terraformLogs.map((l, i) => (
                            <div key={i} className={`mb-0.5 ${l.type === "error" ? "text-rose-400" : "text-gray-300"}`}>
                              <span className="text-orange-400 mr-2">[{l.stage || "tf"}]</span>{l.message}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* ═══ RIGHT: AI Chat ═══ */}
            <div className="col-span-4 h-full" style={{ minHeight: 0 }}>
              <AIChatSidebar
                messages={messages}
                input={input}
                onInputChange={setInput}
                onSend={() => { if (!context.metadata.deploy_blocked) handleSend(); }}
                sending={sending || !!context.metadata.deploy_blocked}
                logInput={logInput}
                onLogInputChange={setLogInput}
                instructions={instructions}
                onInstructionsChange={setInstructions}
                selectedModel={selectedModel}
                onModelChange={setSelectedModel}
              />
            </div>

          </div>
        </main>
      </div>
    </div>
  );
};
