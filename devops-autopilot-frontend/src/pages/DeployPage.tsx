import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Navbar } from "../components/Navbar";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { apiClient } from "../api/client";
import {
  DockerContextResponse,
  DockerfileInfo,
  FileNode,
} from "../types/api";

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
  const [logStreamBaseUrl, setLogStreamBaseUrl] = useState<string | null>(null);
  const [refreshingTree, setRefreshingTree] = useState<boolean>(false);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});
  const apiBase = "http://localhost:8000/api";
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
    const userMsg: ChatMessage = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    try {
      const payload: { message: string; logs?: string[]; instructions?: string } =
        { message: input.trim() };
      if (logInput.trim()) {
        payload.logs = logInput.split("\n").slice(-50);
      }
      if (instructions.trim()) {
        payload.instructions = instructions.trim();
      }
      const resp = await apiClient.sendDockerChat(projectId, payload);
      if (resp.log_stream_base_url) {
        setLogStreamBaseUrl(resp.log_stream_base_url);
      }
      setMessages((prev) => [...prev, { role: "ai", content: resp.reply }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "ai",
          content:
            err instanceof Error
              ? `Error contacting Llama 3.1: ${err.message}`
              : "Error contacting Llama 3.1",
        },
      ]);
    } finally {
      setSending(false);
      setInput("");
    }
  };

  const appendLogs = (incoming: LogLine) => {
    setLogs((prev) => [...prev, incoming]);
  };

  const startStream = (action: "build" | "run" | "push") => {
    if (!projectId) return;
    if (eventSource) {
      eventSource.close();
    }
    setLogs([]);
    const token = apiClient.getToken();
    const base =
      logStreamBaseUrl && logStreamBaseUrl.startsWith("http")
        ? logStreamBaseUrl
        : logStreamBaseUrl
        ? `${apiBase}${logStreamBaseUrl.startsWith("/") ? "" : "/"}${logStreamBaseUrl}`
        : `${apiBase}/docker/${projectId}/logs`;
    const url = new URL(base);
    url.searchParams.set("action", action);
    if (token) {
      url.searchParams.set("token", token);
    }
    const source = new EventSource(url.toString());
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        appendLogs({
          line: data.line,
          stage: data.stage,
          exit_code: data.exit_code,
          complete: data.complete,
        });

        if (data.complete && typeof data.exit_code === "number") {
          source.close();
          setEventSource(null);
          if (data.exit_code !== 0) {
            const tail: string[] = data.tail || [];
            const summary = tail.slice(-20).join("\n");
            setMessages((prev) => [
              ...prev,
              {
                role: "ai",
                content: `${action} failed, sending logs to Llama 3.1 for analysis...`,
              },
            ]);
            apiClient
              .sendDockerChat(projectId, {
                message: `${action} failed. Analyze these logs and fix Dockerfile.`,
                logs: summary ? summary.split("\n") : undefined,
              })
              .then((resp) =>
                setMessages((prev) => [...prev, { role: "ai", content: resp.reply }])
              )
              .catch((err) =>
                setMessages((prev) => [
                  ...prev,
                  {
                    role: "ai",
                    content:
                      err instanceof Error
                        ? `Error sending logs to Llama 3.1: ${err.message}`
                        : "Error sending logs to Llama 3.1",
                  },
                ])
              );
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
          className={`flex items-center justify-between group rounded px-2 py-1 hover:bg-gray-700/50 ${
            !node.is_dir && activeFile === node.path ? "bg-gray-700/60 border border-cyan-600/40" : ""
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
                {(expandedDirs[node.path] ?? true) ? "▾" : "▸"}
              </button>
            ) : (
              <span className="text-gray-600 text-xs">•</span>
            )}
            <button
              className={`text-left text-sm ${
                node.is_dir ? "text-cyan-200" : activeFile === node.path ? "text-white" : "text-gray-200"
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
                  className="text-[10px] px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-200 hover:border-cyan-500"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCreateFile(node.path);
                  }}
                  disabled={refreshingTree}
                >
                  + File
                </button>
                <button
                  className="text-[10px] px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-200 hover:border-cyan-500"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCreateFolder(node.path);
                  }}
                  disabled={refreshingTree}
                >
                  + Folder
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

  const renderDockerfiles = (items: DockerfileInfo[], title: string) => (
    <Card className="p-4 bg-gray-800 border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <span className="text-xs text-gray-400">{items.length} file(s)</span>
      </div>
      {items.length === 0 ? (
        <p className="text-gray-400 text-sm">None detected yet.</p>
      ) : (
        items.map((df) => (
          <div
            key={df.path}
            className="mb-3 rounded border border-gray-700 bg-gray-900 p-3"
          >
            <p className="text-xs text-cyan-400 mb-2">{df.path}</p>
            <pre className="text-xs text-gray-200 overflow-auto max-h-64 whitespace-pre-wrap">
              {df.content}
            </pre>
          </div>
        ))
      )}
    </Card>
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <p className="text-gray-300">Loading deploy workspace...</p>
      </div>
    );
  }

  if (error || !context) {
    return (
      <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center gap-4">
        <p className="text-red-400">{error || "Unable to load deploy context"}</p>
        <Button onClick={() => navigate("/dashboard")}>Back to Dashboard</Button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navbar />
      <main className="max-w-7xl mx-auto px-6 py-8 h-[calc(100vh-64px)]">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white">Docker Deploy</h1>
            <p className="text-gray-400">
              Project: {context.project.project_name} (powered by Llama 3.1)
            </p>
          </div>
          <Button variant="secondary" onClick={() => navigate("/dashboard")}>
            Back to Dashboard
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-[calc(100vh-150px)]">
          {/* Left sidebar: file explorer + metadata (scroll here only) */}
          <div className="lg:col-span-3 flex flex-col bg-gray-850/0 gap-3 overflow-y-auto pr-1 custom-scroll">
            <Card className="p-4 bg-gray-800 border-gray-700">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-gray-400">
                    Explorer
                  </p>
                  <p className="text-sm text-white font-semibold">{rootLabel}</p>
                </div>
                <button
                  className="text-[11px] px-2 py-1 rounded bg-gray-900 border border-gray-700 text-gray-200 hover:border-cyan-500"
                  onClick={() => refreshExplorer()}
                  disabled={refreshingTree}
                  title="Refresh"
                >
                  ↻
                </button>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                <button
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-md bg-gray-900/80 border border-gray-700 text-gray-100 hover:border-cyan-500 hover:text-white shadow-sm transition"
                  onClick={() => handleCreateFile(null)}
                  disabled={refreshingTree}
                >
                  <span className="text-cyan-400 text-xs">＋</span>
                  New File
                </button>
                <button
                  className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-md bg-gray-900/80 border border-gray-700 text-gray-100 hover:border-cyan-500 hover:text-white shadow-sm transition"
                  onClick={() => handleCreateFolder(null)}
                  disabled={refreshingTree}
                >
                  <span className="text-cyan-400 text-xs">＋</span>
                  New Folder
                </button>
                {refreshingTree && (
                  <span className="text-xs text-gray-400">Refreshing…</span>
                )}
              </div>
              <div className="max-h-[420px] overflow-y-auto custom-scroll rounded-md border border-gray-750/60 bg-gray-900/60">
                {renderFileTree(context.file_tree.tree)}
              </div>
            </Card>

            <Card className="p-4 bg-gray-800 border-gray-700">
              <h3 className="text-sm font-semibold text-white mb-2">
                Project Metadata
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {metadataList.map((item) => (
                  <div
                    key={item.label}
                    className="bg-gray-900 rounded-lg p-2 border border-gray-700"
                  >
                    <p className="text-xs text-gray-500">{item.label}</p>
                    <p className="text-sm text-white truncate">
                      {item.value as string}
                    </p>
                  </div>
                ))}
              </div>
              {context.metadata.env_variables?.length ? (
                <div className="mt-2">
                  <p className="text-xs text-gray-500 mb-1">Env variables</p>
                  <div className="flex flex-wrap gap-1">
                    {context.metadata.env_variables.slice(0, 10).map((v) => (
                      <span
                        key={v}
                        className="text-[11px] bg-gray-900 border border-gray-700 rounded px-2 py-0.5 text-gray-200"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {context.compose_files.length > 0 && (
                <div className="mt-2 text-xs text-gray-400">
                  Docker Compose detected ({context.compose_files.length})
                </div>
              )}
            </Card>
          </div>

          {/* Center panel: tabs + editor */}
          <div className="lg:col-span-6 flex flex-col space-y-3">
            <Card className="p-0 bg-gray-800 border-gray-700 flex flex-col h-full">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
                <div className="flex flex-wrap gap-2">
                  {openFiles.length === 0 ? (
                    <span className="text-xs text-gray-500">
                      Open a file from the explorer
                    </span>
                  ) : (
                    openFiles.map((path) => (
                      <button
                        key={path}
                        className={`px-3 py-1 rounded text-xs border ${
                          activeFile === path
                            ? "bg-gray-700 text-white border-cyan-500/50"
                            : "bg-gray-900 text-gray-300 border-gray-700"
                        }`}
                        onClick={() => setActiveFile(path)}
                      >
                        {dirtyFlags[path] ? "* " : ""}
                        {path.split("/").pop()}
                      </button>
                    ))
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {activeFile || "No file selected"}
                </div>
              </div>

              <div className="flex-1 flex flex-col">
                <textarea
                  value={(activeFile && fileContents[activeFile]) || ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!activeFile) return;
                    setFileContents((prev) => ({ ...prev, [activeFile]: val }));
                    setDirtyFlags((prev) => ({ ...prev, [activeFile]: true }));
                  }}
                  className="w-full flex-1 bg-gray-900 border-0 rounded-b-lg p-4 text-sm text-gray-100 focus:outline-none"
                  placeholder="File preview and edit here"
                  spellCheck={false}
                />
                <div className="flex items-center justify-between px-4 py-2 border-t border-gray-700">
                  <div className="text-xs text-gray-400">
                    Tabs styled like VS Code; syntax highlighting can be added with a code editor component later.
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!activeFile || !dirtyFlags[activeFile] || saving}
                    loading={saving}
                    onClick={handleSaveFile}
                  >
                    Save File
                  </Button>
                </div>
              </div>
            </Card>
          </div>

          {/* Right sidebar: docker actions + chat */}
          <div className="lg:col-span-3 flex flex-col gap-3 max-h-[calc(100vh-180px)] overflow-y-auto custom-scroll">
            <Card className="p-4 bg-gray-800 border-gray-700">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-white">Docker Actions</h3>
                <span className="text-xs text-gray-400">Build & Run</span>
              </div>
              <div className="flex flex-wrap gap-2 mb-3">
                <Button variant="secondary" size="sm" onClick={() => startStream("build")}>
                  Build Image
                </Button>
                <Button variant="secondary" size="sm" onClick={() => startStream("run")}>
                  Run Container
                </Button>
                <Button variant="secondary" size="sm" onClick={() => startStream("push")}>
                  Push Image
                </Button>
              </div>
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 max-h-36 overflow-auto custom-scroll">
                {logs.length === 0 ? (
                  <p className="text-sm text-gray-400">Logs will stream here.</p>
                ) : (
                  logs.map((l, idx) => (
                    <div key={idx} className="text-xs text-gray-200">
                      <span className="text-cyan-400 mr-2">[{l.stage}]</span>
                      {l.line}
                      {typeof l.exit_code === "number" ? ` (exit ${l.exit_code})` : ""}
                    </div>
                  ))
                )}
              </div>
            </Card>

            <Card className="p-4 bg-gray-800 border-gray-700 flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-white">
                  Llama 3.1 Deploy Chat
                </h3>
                <span className="text-xs text-gray-400">Dockerfile validation</span>
              </div>

              <div className="flex-1 overflow-y-auto custom-scroll mb-4 space-y-3 min-h-[320px] max-h-[520px]">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded ${
                      msg.role === "user"
                        ? "bg-cyan-500/10 text-cyan-100"
                        : "bg-gray-900 text-gray-200"
                    }`}
                  >
                    <div className="text-xs uppercase text-gray-400 mb-1">
                      {msg.role === "user" ? "You" : "Llama 3.1"}
                    </div>
                    <pre className="whitespace-pre-wrap text-sm leading-relaxed">
                      {msg.content}
                    </pre>
                  </div>
                ))}
              </div>

              <div className="space-y-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm text-white focus:border-cyan-500 focus:outline-none"
                  placeholder="Ask Llama 3.1 to validate or generate Dockerfiles..."
                  rows={2}
                />

                <textarea
                  value={logInput}
                  onChange={(e) => setLogInput(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 focus:border-cyan-500 focus:outline-none"
                  placeholder="Paste recent build/run logs here (optional)..."
                  rows={2}
                />

                <input
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 focus:border-cyan-500 focus:outline-none"
                  placeholder="High-level deploy instructions (optional)"
                />

                <div className="flex justify-end">
                  <Button onClick={handleSend} loading={sending} disabled={!input}>
                    Send to Llama 3.1
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
};
