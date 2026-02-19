import React, { useState, useEffect } from 'react';
import { apiClient, streamAWSTerraform } from '../api/client';
import { Button } from './Button';
import { Alert } from './Alert';
import { LoadingSpinner } from './LoadingSpinner';

interface AWSDeployPanelProps {
  projectId: string;
  projectName: string;
  onStatusChange?: () => void;
}

interface AWSConfig {
  aws_region: string;
  docker_repo_prefix: string;
  db_engine: string;
  mongo_db_url: string;
  rds_db_url: string;
  desired_count: number;
}

interface AWSStatus {
  aws_deployment_status: string;
  aws_region?: string;
  aws_frontend_url?: string;
  docker_push_success: boolean;
  live_alb_url?: string;
}

interface TerraformEvent {
  type: string;
  message: string;
  stage?: string;
}

const AWS_REGIONS = [
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-east-2', label: 'US East (Ohio)' },
  { value: 'us-west-1', label: 'US West (N. California)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
  { value: 'eu-west-1', label: 'EU (Ireland)' },
  { value: 'eu-central-1', label: 'EU (Frankfurt)' },
  { value: 'ap-south-1', label: 'Asia Pacific (Mumbai)' },
  { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
];

const DB_ENGINES = [
  { value: 'none', label: 'No Database' },
  { value: 'mongo', label: 'MongoDB (Atlas/Cloud)' },
  { value: 'postgres', label: 'PostgreSQL (RDS)' },
  { value: 'mysql', label: 'MySQL (RDS)' },
];

const AWSDeployPanel: React.FC<AWSDeployPanelProps> = ({ 
  projectId, 
  projectName,
  onStatusChange 
}) => {
  const [status, setStatus] = useState<AWSStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [terraformLogs, setTerraformLogs] = useState<TerraformEvent[]>([]);
  const [isDeploying, setIsDeploying] = useState(false);
  
  const [config, setConfig] = useState<AWSConfig>({
    aws_region: 'us-east-1',
    docker_repo_prefix: '',
    db_engine: 'none',
    mongo_db_url: '',
    rds_db_url: '',
    desired_count: 1,
  });

  // Load status on mount
  useEffect(() => {
    loadStatus();
  }, [projectId]);

  const loadStatus = async () => {
    try {
      setLoading(true);
      const result = await apiClient.getAWSStatus(projectId);
      setStatus(result);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load AWS status');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateTerraform = async () => {
    try {
      setError(null);
      setLoading(true);
      
      await apiClient.generateTerraform(projectId, {
        aws_region: config.aws_region,
        docker_repo_prefix: config.docker_repo_prefix,
        db_engine: config.db_engine !== 'none' ? config.db_engine : undefined,
        mongo_db_url: config.db_engine === 'mongo' ? config.mongo_db_url : undefined,
        rds_db_url: config.db_engine !== 'none' && config.db_engine !== 'mongo' ? config.rds_db_url : undefined,
        desired_count: config.desired_count,
      });
      
      await loadStatus();
      setShowConfig(false);
      onStatusChange?.();
    } catch (err: any) {
      setError(err.message || 'Failed to generate Terraform');
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    setIsDeploying(true);
    setTerraformLogs([]);
    setError(null);

    streamAWSTerraform(
      projectId,
      'apply',
      (event) => {
        setTerraformLogs(prev => [...prev, event]);
      },
      () => {
        setIsDeploying(false);
        loadStatus();
        onStatusChange?.();
      },
      (err) => {
        setError(err.message);
        setIsDeploying(false);
      }
    );
  };

  const handleDestroy = () => {
    if (!window.confirm('⚠️ This will permanently delete all AWS resources. Are you sure?')) {
      return;
    }

    setIsDeploying(true);
    setTerraformLogs([]);
    setError(null);

    streamAWSTerraform(
      projectId,
      'destroy',
      (event) => {
        setTerraformLogs(prev => [...prev, event]);
      },
      () => {
        setIsDeploying(false);
        loadStatus();
        onStatusChange?.();
      },
      (err) => {
        setError(err.message);
        setIsDeploying(false);
      }
    );
  };

  const handleScaleToZero = () => {
    setIsDeploying(true);
    setTerraformLogs([]);

    streamAWSTerraform(
      projectId,
      'scale-zero',
      (event) => {
        setTerraformLogs(prev => [...prev, event]);
      },
      () => {
        setIsDeploying(false);
        loadStatus();
      },
      (err) => {
        setError(err.message);
        setIsDeploying(false);
      }
    );
  };

  if (loading && !status) {
    return (
      <div className="aws-deploy-panel loading">
        <LoadingSpinner />
        <p>Loading AWS status...</p>
      </div>
    );
  }

  const canDeploy = status?.docker_push_success;
  const isDeployed = status?.aws_deployment_status === 'deployed';
  const hasTerraform = status?.aws_deployment_status === 'terraform_generated' || isDeployed;

  return (
    <div className="aws-deploy-panel">
      <div className="aws-deploy-header">
        <h3>☁️ AWS Deployment</h3>
        <span className={`status-badge ${status?.aws_deployment_status || 'not_deployed'}`}>
          {status?.aws_deployment_status?.replace(/_/g, ' ') || 'Not Deployed'}
        </span>
      </div>

      {error && <Alert type="error" message={error} />}

      {!canDeploy && (
        <Alert type="warning" message="Push Docker images first to enable AWS deployment." />
      )}

      {/* Deployed state */}
      {isDeployed && status?.live_alb_url && (
        <div className="aws-deployed-info">
          <div className="info-row">
            <span className="label">🌐 Frontend URL:</span>
            <a 
              href={`http://${status.live_alb_url}`} 
              target="_blank" 
              rel="noopener noreferrer"
              className="alb-url"
            >
              {status.live_alb_url}
            </a>
          </div>
          <div className="info-row">
            <span className="label">📍 Region:</span>
            <span>{status.aws_region}</span>
          </div>
          <div className="aws-actions">
            <Button onClick={handleScaleToZero} disabled={isDeploying} variant="secondary">
              ⏸️ Scale to Zero
            </Button>
            <Button onClick={handleDestroy} disabled={isDeploying} variant="danger">
              🗑️ Destroy
            </Button>
          </div>
        </div>
      )}

      {/* Config form */}
      {showConfig && (
        <div className="aws-config-form">
          <div className="form-group">
            <label>AWS Region</label>
            <select 
              value={config.aws_region}
              onChange={e => setConfig(prev => ({ ...prev, aws_region: e.target.value }))}
            >
              {AWS_REGIONS.map(r => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Docker Hub Username</label>
            <input
              type="text"
              placeholder="e.g., yourusername"
              value={config.docker_repo_prefix}
              onChange={e => setConfig(prev => ({ ...prev, docker_repo_prefix: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label>Database Engine</label>
            <select 
              value={config.db_engine}
              onChange={e => setConfig(prev => ({ ...prev, db_engine: e.target.value }))}
            >
              {DB_ENGINES.map(d => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>

          {config.db_engine === 'mongo' && (
            <div className="form-group">
              <label>MongoDB Connection URL</label>
              <input
                type="password"
                placeholder="mongodb+srv://..."
                value={config.mongo_db_url}
                onChange={e => setConfig(prev => ({ ...prev, mongo_db_url: e.target.value }))}
              />
            </div>
          )}

          {config.db_engine !== 'none' && config.db_engine !== 'mongo' && (
            <div className="form-group">
              <label>RDS Connection URL</label>
              <input
                type="password"
                placeholder="postgresql://..."
                value={config.rds_db_url}
                onChange={e => setConfig(prev => ({ ...prev, rds_db_url: e.target.value }))}
              />
            </div>
          )}

          <div className="form-group">
            <label>Desired Task Count</label>
            <input
              type="number"
              min="1"
              max="10"
              value={config.desired_count}
              onChange={e => setConfig(prev => ({ ...prev, desired_count: parseInt(e.target.value) || 1 }))}
            />
          </div>

          <div className="form-actions">
            <Button onClick={() => setShowConfig(false)} variant="secondary">
              Cancel
            </Button>
            <Button 
              onClick={handleGenerateTerraform} 
              disabled={!config.docker_repo_prefix || loading}
            >
              {loading ? <LoadingSpinner /> : '🏗️ Generate Terraform'}
            </Button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!showConfig && !isDeployed && (
        <div className="aws-actions">
          {!hasTerraform ? (
            <Button 
              onClick={() => setShowConfig(true)} 
              disabled={!canDeploy}
            >
              ⚙️ Configure AWS
            </Button>
          ) : (
            <Button 
              onClick={handleApply} 
              disabled={isDeploying}
            >
              {isDeploying ? <LoadingSpinner /> : '🚀 Deploy to AWS'}
            </Button>
          )}
        </div>
      )}

      {/* Terraform logs */}
      {terraformLogs.length > 0 && (
        <div className="terraform-logs">
          <h4>Terraform Output</h4>
          <div className="log-container">
            {terraformLogs.map((log, i) => (
              <div key={i} className={`log-line ${log.type}`}>
                <span className="stage">[{log.stage}]</span>
                <span className="message">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        .aws-deploy-panel {
          background: var(--bg-secondary, #1e1e2e);
          border-radius: 12px;
          padding: 20px;
          margin-top: 16px;
        }

        .aws-deploy-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
        }

        .aws-deploy-header h3 {
          margin: 0;
          font-size: 1.2rem;
        }

        .status-badge {
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 0.85rem;
          font-weight: 500;
        }

        .status-badge.not_deployed { background: #6b7280; }
        .status-badge.terraform_generated { background: #f59e0b; }
        .status-badge.deploying { background: #3b82f6; }
        .status-badge.deployed { background: #10b981; color: #fff; }
        .status-badge.failed { background: #ef4444; color: #fff; }
        .status-badge.scaled_to_zero { background: #8b5cf6; }

        .aws-deployed-info {
          background: rgba(16, 185, 129, 0.1);
          border: 1px solid rgba(16, 185, 129, 0.3);
          border-radius: 8px;
          padding: 16px;
          margin-bottom: 16px;
        }

        .info-row {
          display: flex;
          gap: 8px;
          margin-bottom: 8px;
        }

        .info-row .label {
          font-weight: 500;
          min-width: 120px;
        }

        .alb-url {
          color: #3b82f6;
          text-decoration: none;
        }

        .alb-url:hover {
          text-decoration: underline;
        }

        .aws-actions {
          display: flex;
          gap: 12px;
          margin-top: 16px;
        }

        .aws-config-form {
          background: rgba(255, 255, 255, 0.05);
          border-radius: 8px;
          padding: 16px;
        }

        .form-group {
          margin-bottom: 16px;
        }

        .form-group label {
          display: block;
          margin-bottom: 6px;
          font-weight: 500;
          font-size: 0.9rem;
        }

        .form-group input,
        .form-group select {
          width: 100%;
          padding: 10px 12px;
          border: 1px solid rgba(255, 255, 255, 0.2);
          border-radius: 6px;
          background: rgba(0, 0, 0, 0.2);
          color: inherit;
          font-size: 0.95rem;
        }

        .form-actions {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          margin-top: 20px;
        }

        .terraform-logs {
          margin-top: 20px;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
          padding-top: 16px;
        }

        .terraform-logs h4 {
          margin: 0 0 12px 0;
          font-size: 0.95rem;
        }

        .log-container {
          background: #0d0d0d;
          border-radius: 8px;
          padding: 12px;
          max-height: 300px;
          overflow-y: auto;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
        }

        .log-line {
          display: flex;
          gap: 8px;
          padding: 2px 0;
        }

        .log-line .stage {
          color: #6b7280;
          min-width: 70px;
        }

        .log-line.error .message { color: #ef4444; }
        .log-line.warning .message { color: #f59e0b; }
        .log-line.success .message { color: #10b981; }
        .log-line.info .message { color: #a5b4fc; }

        .loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          padding: 40px;
        }
      `}</style>
    </div>
  );
};

export default AWSDeployPanel;
