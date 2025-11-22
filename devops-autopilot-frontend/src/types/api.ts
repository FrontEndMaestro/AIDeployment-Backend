// ============ AUTH TYPES ============
export interface UserRegisterRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface UserLoginRequest {
  username: string;
  password: string;
}

export interface User {
  user_id: string;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  is_admin?: boolean;
  workspace_path?: string;
  created_at: string;
}

export interface AuthResponse {
  success: boolean;
  message: string;
  user?: User;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// ============ PROJECT TYPES ============
export interface ProjectMetadata {
  framework: string;
  language: string;
  runtime?: string;
  dependencies: string[];
  port?: number; // still the "main" port (backend_port)
  build_command?: string;
  start_command?: string;
  env_variables: string[];
  dockerfile: boolean;
  docker_compose: boolean;
  detected_files: string[];

  // ML / detection confidence
  ml_confidence?: {
    language: number;
    framework: number;
    method?: string; // mirrors detection_confidence.method when present
  };
  detection_confidence?: {
    language: number;
    framework: number;
    method?: string;
  };
  detection_method?: string; // kept for backwards compatibility if used anywhere

  // NEW FIELDS (from detector.py)
  backend_port?: number;
  frontend_port?: number;
  database?: string;
  database_port?: number | null;
  databases?: string[];
  database_detection?: {
    [dbName: string]: {
      score: number;
      evidence: string[];
    };
  };
}

export interface LogEntry {
  message: string;
  timestamp: string;
}

export interface Project {
  _id: string;
  project_name: string;
  file_name: string;
  file_size: number;
  upload_date: string;
  status:
    | "uploaded"
    | "extracting"
    | "extracted"
    | "analyzing"
    | "analyzed"
    | "completed"
    | "failed";
  extracted_path?: string;
  extraction_date?: string;
  files_count: number;
  folders_count: number;
  metadata: ProjectMetadata;
  analysis_date?: string;
  analysis_logs?: string[];
  logs: LogEntry[];
}

export interface ProjectUploadResponse {
  success: boolean;
  message: string;
  data: {
    project_id: string;
    project_name: string;
    file_name: string;
    file_size: string;
    upload_date: string;
  };
}

export interface ProjectListResponse {
  success: boolean;
  count: number;
  projects: Project[];
}

export interface ExtractionResponse {
  success: boolean;
  message: string;
  data: {
    project_id: string;
    project_name: string;
    extracted_path: string;
    files_count: number;
    folders_count: number;
    extraction_date: string;
  };
}

export interface AnalysisResponse {
  success: boolean;
  message: string;
  data: {
    project_id: string;
    project_name: string;
    framework: string;
    language: string;
    runtime: string | null;
    dependencies: string[];
    port?: number;
    build_command?: string;
    start_command?: string;
    ml_confidence?: {
      language: number;
      framework: number;
      method?: string;
    };
    analysis_date: string;
    ml_enabled?: boolean;

    // NEW (optional) – mirrors metadata
    backend_port?: number;
    frontend_port?: number;
    database?: string;
    databases?: string[];
    database_port?: number | null;
    env_variables?: string[];
    dockerfile?: boolean;
    docker_compose?: boolean;
    detected_files?: string[];
  };
}

export interface ApiError {
  success: false;
  message: string;
  error?: string;
}
