import type React from "react";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { Navbar } from "../components/Navbar";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { Badge } from "../components/Badge";
import { Alert } from "../components/Alert";
import { ExtractProjectModal } from "../components/ExtractProjectModal";
import { AnalyzeProjectModal } from "../components/AnalyzeProjectModal";
import { ProjectDetailsModal } from "../components/ProjectDetailsModal";
import { apiClient } from "../api/client";
import { Project } from "../types/api";

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [selectedFilter, setSelectedFilter] = useState<
    "all" | "analyzed" | "uploaded"
  >("all");

  // Modal states
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [showExtractModal, setShowExtractModal] = useState(false);
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false);
  const [showDetailsModal, setShowDetailsModal] = useState(false);

  useEffect(() => {
    loadProjects();
    const interval = setInterval(loadProjects, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  const loadProjects = async () => {
    try {
      setLoading(true);
      const response = await apiClient.getProjects();
      setProjects(response.projects);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const validTypes = [".zip", ".tar", ".gz", ".tgz"];
    const fileName = file.name.toLowerCase();
    const isValid = validTypes.some((type) => fileName.endsWith(type));

    if (!isValid) {
      setError("Only ZIP and TAR files are allowed");
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError("File size must be less than 100MB");
      return;
    }

    try {
      setUploading(true);
      setUploadProgress(30);

      const response = await apiClient.uploadProject(
        file,
        file.name.split(".")[0]
      );
      console.log("file response" + response);
      setUploadProgress(100);
      setTimeout(() => {
        loadProjects();
        setUploadProgress(0);
        setUploading(false);
      }, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
      setUploadProgress(0);
    }
  };

  const handleExtractAndAnalyze = (project: Project) => {
    setSelectedProject(project);
    setShowExtractModal(true);
  };

  const handleAnalyzeOpen = (project: Project) => {
    setSelectedProject(project);
    setShowAnalyzeModal(true);
  };

  const handleDetailsOpen = (project: Project) => {
    setSelectedProject(project);
    setShowDetailsModal(true);
  };

  const handleExtractSuccess = () => {
    setShowExtractModal(false);
    loadProjects();
  };

  const handleAnalyzeSuccess = () => {
    setShowAnalyzeModal(false);
    loadProjects();
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm("Are you sure you want to delete this project?")) return;

    try {
      await apiClient.deleteProject(projectId);
      loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete project");
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "uploaded":
        return "info";
      case "extracting":
      case "analyzing":
        return "warning";
      case "analyzed":
      case "completed":
        return "success";
      case "failed":
        return "error";
      default:
        return "default";
    }
  };

  const getStatusIcon = (status: string) => {
    const icons: Record<string, JSX.Element> = {
      uploaded: (
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
      ),
      extracting: (
        <svg
          className="w-4 h-4 animate-spin"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
      ),
      analyzing: (
        <svg
          className="w-4 h-4 animate-pulse"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
      analyzed: (
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
      completed: (
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
      ),
      failed: (
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      ),
    };
    return icons[status] || icons.uploaded;
  };

  const stats = {
    total: projects.length,
    analyzed: projects.filter(
      (p) => p.status === "analyzed" || p.status === "completed"
    ).length,
    frameworks: [
      ...new Set(
        projects
          .filter((p) => p.metadata.framework !== "Unknown")
          .map((p) => p.metadata.framework)
      ),
    ].length,
    totalSize: projects.reduce((acc, p) => acc + p.file_size, 0),
  };

  const filteredProjects = projects.filter((p) => {
    if (selectedFilter === "all") return true;
    if (selectedFilter === "analyzed")
      return p.status === "analyzed" || p.status === "completed";
    if (selectedFilter === "uploaded") return p.status === "uploaded";
    return true;
  });

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  };

  if (loading && projects.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-900">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-gray-700 border-t-cyan-500 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400 text-lg">Loading your workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900">
      <Navbar />

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Header Section */}
        <div className="mb-8 animate-fade-in">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent mb-2">
                Dashboard
              </h1>
              <p className="text-gray-400">
                Manage and analyze your DevOps projects
              </p>
            </div>
            <label className="cursor-pointer">
              <div className="px-6 py-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-semibold rounded-xl transition-all transform hover:scale-105 active:scale-95 shadow-lg shadow-cyan-500/30 flex items-center gap-2">
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
                <span>Upload Project</span>
              </div>
              <input
                type="file"
                onChange={handleFileUpload}
                accept=".zip,.tar,.gz,.tgz"
                className="hidden"
                disabled={uploading}
              />
            </label>
          </div>
        </div>

        {/* Stats Grid */}
        <div
          className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8 animate-fade-in"
          style={{ animationDelay: "0.1s" }}
        >
          <div className="bg-gradient-to-br from-cyan-500/10 to-cyan-600/5 border border-cyan-500/20 rounded-xl p-6 hover:scale-105 transition-transform">
            <div className="flex items-center justify-between mb-3">
              <span className="text-cyan-400 text-sm font-medium">
                Total Projects
              </span>
              <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                <svg
                  className="w-5 h-5 text-cyan-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                  />
                </svg>
              </div>
            </div>
            <p className="text-3xl font-bold text-white">{stats.total}</p>
          </div>

          <div className="bg-gradient-to-br from-green-500/10 to-green-600/5 border border-green-500/20 rounded-xl p-6 hover:scale-105 transition-transform">
            <div className="flex items-center justify-between mb-3">
              <span className="text-green-400 text-sm font-medium">
                Analyzed
              </span>
              <div className="w-10 h-10 bg-green-500/20 rounded-lg flex items-center justify-center">
                <svg
                  className="w-5 h-5 text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold text-white">{stats.analyzed}</p>
              <span className="text-sm text-green-400 font-medium">
                {stats.total > 0
                  ? Math.round((stats.analyzed / stats.total) * 100)
                  : 0}
                %
              </span>
            </div>
          </div>

          <div className="bg-gradient-to-br from-purple-500/10 to-purple-600/5 border border-purple-500/20 rounded-xl p-6 hover:scale-105 transition-transform">
            <div className="flex items-center justify-between mb-3">
              <span className="text-purple-400 text-sm font-medium">
                Frameworks
              </span>
              <div className="w-10 h-10 bg-purple-500/20 rounded-lg flex items-center justify-center">
                <svg
                  className="w-5 h-5 text-purple-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 5a1 1 0 011-1h4a1 1 0 010 2H6v2h3a1 1 0 010 2H6v2h3a1 1 0 010 2H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h1a3 3 0 013 3v6a3 3 0 01-3 3h-1a1 1 0 01-1-1V5z"
                  />
                </svg>
              </div>
            </div>
            <p className="text-3xl font-bold text-white">{stats.frameworks}</p>
          </div>

          <div className="bg-gradient-to-br from-blue-500/10 to-blue-600/5 border border-blue-500/20 rounded-xl p-6 hover:scale-105 transition-transform">
            <div className="flex items-center justify-between mb-3">
              <span className="text-blue-400 text-sm font-medium">
                Total Size
              </span>
              <div className="w-10 h-10 bg-blue-500/20 rounded-lg flex items-center justify-center">
                <svg
                  className="w-5 h-5 text-blue-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
                  />
                </svg>
              </div>
            </div>
            <p className="text-3xl font-bold text-white">
              {formatBytes(stats.totalSize)}
            </p>
          </div>
        </div>

        {/* Upload Progress */}
        {uploading && (
          <div className="mb-6 animate-fade-in">
            <Card className="p-6 bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border-cyan-500/30">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
                <div className="flex-1">
                  <p className="text-white font-medium mb-2">
                    Uploading project...
                  </p>
                  <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-blue-600 transition-all duration-500"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                  <p className="text-gray-400 text-sm mt-2">
                    {uploadProgress}% complete
                  </p>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="mb-6 animate-fade-in">
            <Alert
              type="error"
              title="Error"
              message={error}
              onClose={() => setError(null)}
            />
          </div>
        )}

        {/* Filter Tabs */}
        <div
          className="flex items-center gap-4 mb-6 animate-fade-in"
          style={{ animationDelay: "0.2s" }}
        >
          <button
            onClick={() => setSelectedFilter("all")}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              selectedFilter === "all"
                ? "bg-cyan-500 text-white shadow-lg shadow-cyan-500/30"
                : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            All Projects ({projects.length})
          </button>
          <button
            onClick={() => setSelectedFilter("analyzed")}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              selectedFilter === "analyzed"
                ? "bg-green-500 text-white shadow-lg shadow-green-500/30"
                : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            Analyzed ({stats.analyzed})
          </button>
          <button
            onClick={() => setSelectedFilter("uploaded")}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              selectedFilter === "uploaded"
                ? "bg-blue-500 text-white shadow-lg shadow-blue-500/30"
                : "bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            Pending ({projects.filter((p) => p.status === "uploaded").length})
          </button>
        </div>

        {/* Projects List */}
        {filteredProjects.length === 0 ? (
          <Card className="p-12 text-center animate-fade-in">
            <div className="w-20 h-20 bg-gray-700/50 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg
                className="w-10 h-10 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
                />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-gray-300 mb-2">
              No Projects Found
            </h3>
            <p className="text-gray-500 mb-6">
              Upload your first project to get started with DevOps AutoPilot
            </p>
            <label className="inline-block cursor-pointer">
              <div className="px-6 py-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white font-semibold rounded-xl transition-all shadow-lg shadow-cyan-500/30">
                Upload Project
              </div>
              <input
                type="file"
                onChange={handleFileUpload}
                accept=".zip,.tar,.gz,.tgz"
                className="hidden"
                disabled={uploading}
              />
            </label>
          </Card>
        ) : (
          <div
            className="grid grid-cols-1 gap-6 animate-fade-in"
            style={{ animationDelay: "0.3s" }}
          >
            {filteredProjects.map((project, index) => (
              <div
                key={project._id}
                className="animate-fade-in"
                style={{ animationDelay: `${0.3 + index * 0.05}s` }}
              >
                <Card className="p-6 hover:border-cyan-500/50 transition-all group">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-xl font-bold text-white group-hover:text-cyan-400 transition-colors">
                          {project.project_name}
                        </h3>
                        <Badge variant={getStatusColor(project.status) as any}>
                          <span className="flex items-center gap-1.5">
                            {getStatusIcon(project.status)}
                            {project.status}
                          </span>
                        </Badge>
                      </div>
                      <p className="text-sm text-gray-400 flex items-center gap-2">
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                          />
                        </svg>
                        {project.file_name}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-gray-500">Uploaded</p>
                      <p className="text-sm text-gray-300 font-medium">
                        {new Date(project.upload_date).toLocaleDateString()}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-700">
                      <p className="text-gray-500 text-xs mb-1">Language</p>
                      <p className="text-white font-semibold">
                        {project.metadata.language}
                      </p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-700">
                      <p className="text-gray-500 text-xs mb-1">Framework</p>
                      <p className="text-white font-semibold">
                        {project.metadata.framework}
                      </p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-700">
                      <p className="text-gray-500 text-xs mb-1">Files</p>
                      <p className="text-white font-semibold">
                        {project.files_count}
                      </p>
                    </div>
                    <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-700">
                      <p className="text-gray-500 text-xs mb-1">Size</p>
                      <p className="text-white font-semibold">
                        {formatBytes(project.file_size)}
                      </p>
                    </div>
                  </div>

                  {project.metadata.dependencies.length > 0 && (
                    <div className="mb-4">
                      <p className="text-xs text-gray-500 mb-2 flex items-center gap-2">
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                          />
                        </svg>
                        Dependencies: {project.metadata.dependencies.length}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {project.metadata.dependencies
                          .slice(0, 6)
                          .map((dep, i) => (
                            <Badge key={i} variant="default" size="sm">
                              {dep}
                            </Badge>
                          ))}
                        {project.metadata.dependencies.length > 6 && (
                          <Badge variant="info" size="sm">
                            +{project.metadata.dependencies.length - 6} more
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-wrap gap-3 pt-4 border-t border-gray-700">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleDetailsOpen(project)}
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                        />
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                        />
                      </svg>
                      View Details
                    </Button>

                    {project.status === "uploaded" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleExtractAndAnalyze(project)}
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13 10V3L4 14h7v7l9-11h-7z"
                          />
                        </svg>
                        Extract & Analyze
                      </Button>
                    )}

                    {project.status === "extracted" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleAnalyzeOpen(project)}
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                          />
                        </svg>
                        Analyze
                      </Button>
                    )}

                    <Button
                      variant="danger"
                      size="sm"
                      className="ml-auto"
                      onClick={() => handleDeleteProject(project._id)}
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                      Delete
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={
                        project.status !== "analyzed" &&
                        project.status !== "completed"
                      }
                      onClick={() =>
                        navigate(`/projects/${project._id}/deploy`)
                      }
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v8m-4-4h8M5 12a7 7 0 1114 0 7 7 0 01-14 0z"
                        />
                      </svg>
                      Docker Deploy
                    </Button>
                  </div>
                </Card>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Modals */}
      {selectedProject && (
        <>
          <ExtractProjectModal
            project={selectedProject}
            isOpen={showExtractModal}
            onClose={() => setShowExtractModal(false)}
            onSuccess={handleExtractSuccess}
          />
          <AnalyzeProjectModal
            project={selectedProject}
            isOpen={showAnalyzeModal}
            onClose={() => setShowAnalyzeModal(false)}
            onSuccess={handleAnalyzeSuccess}
          />
          <ProjectDetailsModal
            project={selectedProject}
            isOpen={showDetailsModal}
            onClose={() => setShowDetailsModal(false)}
          />
        </>
      )}
    </div>
  );
};
