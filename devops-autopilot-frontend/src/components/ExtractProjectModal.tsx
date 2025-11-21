import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { Button } from './Button';
import { Alert } from './Alert';
import { ProgressBar } from './ProgressBar';
import { apiClient } from '../api/client';
import { Project } from '../types/api';

interface ExtractProjectModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface ExtractedFile {
  name: string;
  path: string;
  type: 'file' | 'folder';
  size?: number;
  extension?: string;
}

export const ExtractProjectModal: React.FC<ExtractProjectModalProps> = ({
  project,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [extractedFiles, setExtractedFiles] = useState<ExtractedFile[]>([]);
  const [showFiles, setShowFiles] = useState(false);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);

  const pollExtractionStatus = async () => {
    try {
      const response = await apiClient.getExtractionStatus(project._id);
      if (response.success) {
        if (response.data.status === 'extracted') {
          setSuccess(true);
          setLoading(false);
          if (pollingInterval) clearInterval(pollingInterval);
          setTimeout(onSuccess, 2000);
        }
      }
    } catch (err) {
      // Continue polling
    }
  };

  useEffect(() => {
    if (loading && !pollingInterval) {
      const interval = setInterval(pollExtractionStatus, 2000);
      setPollingInterval(interval);
      return () => clearInterval(interval);
    }
  }, [loading, pollingInterval]);

  const handleExtract = async () => {
    setError(null);
    setSuccess(false);
    setLoading(true);

    try {
      const response = await apiClient.extractProject(project._id);

      if (response.success) {
        // Start polling for extraction status
        const pollInterval = setInterval(async () => {
          try {
            const statusResponse = await apiClient.getExtractionStatus(project._id);
            if (statusResponse.data.status === 'extracted') {
              clearInterval(pollInterval);
              setSuccess(true);
              setLoading(false);

              // Fetch extracted files
              const filesResponse = await apiClient.getExtractedFiles(project._id);
              if (filesResponse.success) {
                setExtractedFiles(filesResponse.files);
              }

              onSuccess();
            }
          } catch (err) {
            // Continue polling
          }
        }, 2000);

        setPollingInterval(pollInterval as any);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Extraction failed');
      setLoading(false);
    }
  };

  const fetchExtractedFiles = async () => {
    try {
      const response = await apiClient.getExtractedFiles(project._id);
      if (response.success) {
        setExtractedFiles(response.files);
        setShowFiles(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch files');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold text-white mb-1">Extract Project</h2>
              <p className="text-gray-400 text-sm">{project.project_name}</p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition text-2xl leading-none"
            >
              ×
            </button>
          </div>

          {/* Project Info */}
          <div className="bg-gray-900/50 rounded-lg p-4 mb-6 border border-gray-700">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-gray-500 text-xs mb-1">File Name</p>
                <p className="text-white font-medium">{project.file_name}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs mb-1">File Size</p>
                <p className="text-white font-medium">
                  {(project.file_size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
              <div>
                <p className="text-gray-500 text-xs mb-1">Current Status</p>
                <p className="text-white font-medium capitalize">{project.status}</p>
              </div>
              <div>
                <p className="text-gray-500 text-xs mb-1">Upload Date</p>
                <p className="text-white font-medium">
                  {new Date(project.upload_date).toLocaleDateString()}
                </p>
              </div>
            </div>
          </div>

          {/* Error Alert */}
          {error && (
            <div className="mb-6">
              <Alert type="error" title="Error" message={error} onClose={() => setError(null)} />
            </div>
          )}

          {/* Success Alert */}
          {success && (
            <div className="mb-6">
              <Alert
                type="success"
                title="Success"
                message={`Project extracted successfully! ${project.files_count} files, ${project.folders_count} folders`}
              />
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="mb-6">
              <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-4">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 border-3 border-cyan-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                  <div>
                    <p className="text-white font-medium">Extracting project...</p>
                    <p className="text-cyan-400 text-sm">This may take a moment</p>
                  </div>
                </div>
                <ProgressBar value={50} label="Extraction Progress" showPercentage={false} />
              </div>
            </div>
          )}

          {/* Extracted Files */}
          {showFiles && extractedFiles.length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-bold text-white mb-3">Extracted Files</h3>
              <div className="bg-gray-900/50 rounded-lg border border-gray-700 max-h-96 overflow-y-auto">
                <div className="divide-y divide-gray-700">
                  {extractedFiles.slice(0, 50).map((file, idx) => (
                    <div key={idx} className="p-3 flex items-center gap-3 hover:bg-gray-800/50 transition">
                      <div className="flex-shrink-0">
                        {file.type === 'folder' ? (
                          <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
                          </svg>
                        ) : (
                          <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                            />
                          </svg>
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm truncate">{file.name}</p>
                        <p className="text-gray-500 text-xs">{file.path}</p>
                      </div>
                    </div>
                  ))}
                  {extractedFiles.length > 50 && (
                    <div className="p-3 text-center text-gray-400 text-sm">
                      +{extractedFiles.length - 50} more files
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 pt-6 border-t border-gray-700">
            {!loading && !success && (
              <Button variant="primary" onClick={handleExtract}>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z"
                  />
                </svg>
                Extract Project
              </Button>
            )}

            {success && (
              <>
                <Button variant="secondary" onClick={fetchExtractedFiles}>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  View Files
                </Button>
                <Button variant="secondary" onClick={onClose}>
                  Close
                </Button>
              </>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
};