import React, { useState } from 'react';
import { Card } from './Card';
import { Button } from './Button';
import { Badge } from './Badge';
import { apiClient } from '../api/client';
import { Project } from '../types/api';

interface ProjectDetailsModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
}

export const ProjectDetailsModal: React.FC<ProjectDetailsModalProps> = ({
  project,
  isOpen,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'metadata' | 'logs'>('overview');
  const [exporting, setExporting] = useState(false);

  const handleExport = async (format: 'json' | 'yaml') => {
    try {
      setExporting(true);
      const response = await apiClient.exportMetadata(project._id, format);
      if (response.success) {
        const dataStr = JSON.stringify(response.data, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${project.project_name}-metadata.${format}`;
        link.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  if (!isOpen) return null;

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'uploaded':
        return 'info';
      case 'extracting':
      case 'analyzing':
        return 'warning';
      case 'analyzed':
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold text-white mb-2">{project.project_name}</h2>
              <div className="flex items-center gap-2">
                <Badge variant={getStatusColor(project.status) as any}>
                  {project.status}
                </Badge>
                <span className="text-gray-400 text-sm">{project.file_name}</span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition text-2xl leading-none"
            >
              ×
            </button>
          </div>

          {/* Tabs */}
          <div className="flex gap-4 mb-6 border-b border-gray-700">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-4 py-2 font-medium transition-colors border-b-2 ${
                activeTab === 'overview'
                  ? 'border-cyan-500 text-cyan-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveTab('metadata')}
              className={`px-4 py-2 font-medium transition-colors border-b-2 ${
                activeTab === 'metadata'
                  ? 'border-cyan-500 text-cyan-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Metadata
            </button>
            <button
              onClick={() => setActiveTab('logs')}
              className={`px-4 py-2 font-medium transition-colors border-b-2 ${
                activeTab === 'logs'
                  ? 'border-cyan-500 text-cyan-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Logs
            </button>
          </div>

          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">File Name</p>
                  <p className="text-white font-medium">{project.file_name}</p>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">File Size</p>
                  <p className="text-white font-medium">
                    {(project.file_size / (1024 * 1024)).toFixed(2)} MB
                  </p>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">Upload Date</p>
                  <p className="text-white font-medium">
                    {new Date(project.upload_date).toLocaleString()}
                  </p>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">Status</p>
                  <Badge variant={getStatusColor(project.status) as any}>
                    {project.status}
                  </Badge>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">Total Files</p>
                  <p className="text-white font-medium">{project.files_count}</p>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                  <p className="text-gray-400 text-xs mb-2 uppercase">Total Folders</p>
                  <p className="text-white font-medium">{project.folders_count}</p>
                </div>
              </div>

              {project.extraction_date && (
                <div className="bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 rounded-lg p-4">
                  <p className="text-cyan-400 font-semibold mb-1">Extraction Date</p>
                  <p className="text-gray-300">
                    {new Date(project.extraction_date).toLocaleString()}
                  </p>
                </div>
              )}

              {project.analysis_date && (
                <div className="bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20 rounded-lg p-4">
                  <p className="text-green-400 font-semibold mb-1">Analysis Date</p>
                  <p className="text-gray-300">
                    {new Date(project.analysis_date).toLocaleString()}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Metadata Tab */}
          {activeTab === 'metadata' && (
            <div className="space-y-4">
              {project.metadata ? (
                <>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Framework</p>
                      <p className="text-white font-medium text-lg">{project.metadata.framework}</p>
                    </div>

                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Language</p>
                      <p className="text-white font-medium text-lg">{project.metadata.language}</p>
                    </div>

                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Runtime</p>
                      <p className="text-white font-medium text-sm">{project.metadata.runtime || 'N/A'}</p>
                    </div>

                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Port</p>
                      <p className="text-white font-medium">{project.metadata.port || 'N/A'}</p>
                    </div>
                  </div>

                  {project.metadata.build_command && (
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Build Command</p>
                      <code className="text-cyan-400 text-sm break-all">
                        {project.metadata.build_command}
                      </code>
                    </div>
                  )}

                  {project.metadata.start_command && (
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Start Command</p>
                      <code className="text-cyan-400 text-sm break-all">
                        {project.metadata.start_command}
                      </code>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Dockerfile</p>
                      <p className="text-lg font-bold">
                        {project.metadata.dockerfile ? (
                          <span className="text-green-400">✅ Yes</span>
                        ) : (
                          <span className="text-gray-400">❌ No</span>
                        )}
                      </p>
                    </div>

                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-2 uppercase">Docker Compose</p>
                      <p className="text-lg font-bold">
                        {project.metadata.docker_compose ? (
                          <span className="text-green-400">✅ Yes</span>
                        ) : (
                          <span className="text-gray-400">❌ No</span>
                        )}
                      </p>
                    </div>
                  </div>

                  {project.metadata.dependencies.length > 0 && (
                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                      <p className="text-gray-400 text-xs mb-3 uppercase">
                        Dependencies ({project.metadata.dependencies.length})
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {project.metadata.dependencies.map((dep, idx) => (
                          <Badge key={idx} variant="info" size="sm">
                            {dep}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {project.metadata.ml_confidence && (
                    <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4">
                      <p className="text-yellow-400 font-semibold mb-3">ML Confidence Scores</p>
                      <div className="space-y-3">
                        <div>
                          <div className="flex justify-between mb-1">
                            <span className="text-gray-300 text-sm">Language</span>
                            <span className="text-white font-bold">
                              {Math.round(project.metadata.ml_confidence.language * 100)}%
                            </span>
                          </div>
                          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-cyan-500 to-blue-600"
                              style={{
                                width: `${project.metadata.ml_confidence.language * 100}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between mb-1">
                            <span className="text-gray-300 text-sm">Framework</span>
                            <span className="text-white font-bold">
                              {Math.round(project.metadata.ml_confidence.framework * 100)}%
                            </span>
                          </div>
                          <div className="w-full h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-cyan-500 to-blue-600"
                              style={{
                                width: `${project.metadata.ml_confidence.framework * 100}%`,
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <p>No metadata available. Please analyze the project first.</p>
                </div>
              )}
            </div>
          )}

          {/* Logs Tab */}
          {activeTab === 'logs' && (
            <div>
              {project.logs && project.logs.length > 0 ? (
                <div className="bg-gray-900/80 rounded-lg border border-gray-700 font-mono text-sm max-h-96 overflow-y-auto">
                  <div className="divide-y divide-gray-700">
                    {project.logs.map((log, idx) => (
                      <div key={idx} className="p-3 hover:bg-gray-800/30 transition flex gap-3">
                        <span className="text-gray-500 flex-shrink-0 min-w-fit">
                          {new Date(log.timestamp).toLocaleTimeString()}
                        </span>
                        <span className="text-cyan-400 flex-1 break-all">{log.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <p>No logs available</p>
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 pt-6 border-t border-gray-700 flex-wrap">
            {project.status === 'analyzed' && (
              <>
                <Button
                  variant="secondary"
                  onClick={() => handleExport('json')}
                  loading={exporting}
                >
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
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export JSON
                </Button>

                <Button
                  variant="secondary"
                  onClick={() => handleExport('yaml')}
                  loading={exporting}
                >
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
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                    />
                  </svg>
                  Export YAML
                </Button>
              </>
            )}

            <Button variant="secondary" onClick={onClose} className="ml-auto">
              Close
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};