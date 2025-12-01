import {
  UserRegisterRequest,
  UserLoginRequest,
  User,
  AuthResponse,
  TokenResponse,
  ProjectUploadResponse,
  ProjectListResponse,
  ExtractionResponse,
  AnalysisResponse,
  DockerChatResponse,
  DockerContextResponse,
  DockerfileInfo,
} from "../types/api";

const rawApiBase =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://localhost:8000/api";
const API_BASE_URL = rawApiBase.endsWith("/api")
  ? rawApiBase.replace(/\/+$/, "")
  : `${rawApiBase.replace(/\/+$/, "")}/api`;

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem("auth_token");
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem("auth_token", token);
  }

  getToken(): string | null {
    return this.token || localStorage.getItem("auth_token");
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem("auth_token");
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    const token = this.getToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    return headers;
  }

  private async handleResponse(response: Response) {
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || "API request failed");
    }
    return response.json();
  }

  // ============ AUTH ENDPOINTS ============
  async register(data: UserRegisterRequest): Promise<AuthResponse> {
    const response = await fetch(`${API_BASE_URL}/auth/register`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    return this.handleResponse(response);
  }

  async login(credentials: UserLoginRequest): Promise<TokenResponse> {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(credentials),
    });
    const data = await this.handleResponse(response);
    this.setToken(data.access_token);
    return data;
  }

  async getCurrentUser(): Promise<{ success: boolean; user: User }> {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      method: "GET",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async verifyToken(): Promise<boolean> {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/verify`, {
        method: "GET",
        headers: this.getHeaders(),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  // ============ UPLOAD ENDPOINTS ============
  async uploadProject(
    file: File,
    projectName?: string
  ): Promise<ProjectUploadResponse> {
    const formData = new FormData();
    formData.append("file", file);
    if (projectName) {
      formData.append("project_name", projectName);
    }

    const token = this.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE_URL}/upload/`, {
      method: "POST",
      headers,
      body: formData,
    });
    return this.handleResponse(response);
  }

  async getProjects(): Promise<ProjectListResponse> {
    const response = await fetch(`${API_BASE_URL}/upload/projects`, {
      method: "GET",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async getProject(projectId: string) {
    const response = await fetch(
      `${API_BASE_URL}/upload/projects/${projectId}`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async deleteProject(projectId: string) {
    const response = await fetch(
      `${API_BASE_URL}/upload/projects/${projectId}`,
      {
        method: "DELETE",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  // ============ EXTRACT ENDPOINTS ============
  async extractProject(projectId: string): Promise<ExtractionResponse> {
    const response = await fetch(`${API_BASE_URL}/extract/${projectId}`, {
      method: "POST",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async getExtractionStatus(projectId: string) {
    const response = await fetch(
      `${API_BASE_URL}/extract/${projectId}/status`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async getExtractedFiles(projectId: string) {
    const response = await fetch(`${API_BASE_URL}/extract/${projectId}/files`, {
      method: "GET",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async cleanupExtraction(projectId: string) {
    const response = await fetch(
      `${API_BASE_URL}/extract/${projectId}/cleanup`,
      {
        method: "DELETE",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  // ============ ANALYSIS ENDPOINTS ============
  async analyzeProject(
    projectId: string,
    useML: boolean = true,
    force: boolean = false
  ): Promise<AnalysisResponse> {
    const params = new URLSearchParams();
    params.append("use_ml", useML.toString());
    params.append("force", force.toString());

    const response = await fetch(
      `${API_BASE_URL}/analyze/${projectId}?${params}`,
      {
        method: "POST",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async getAnalysisResults(projectId: string) {
    const response = await fetch(`${API_BASE_URL}/analyze/${projectId}`, {
      method: "GET",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async getProjectMetadata(projectId: string) {
    const response = await fetch(
      `${API_BASE_URL}/analyze/${projectId}/metadata`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async getAllMetadata(framework?: string, language?: string) {
    const params = new URLSearchParams();
    if (framework) params.append("framework", framework);
    if (language) params.append("language", language);

    const response = await fetch(
      `${API_BASE_URL}/analyze/metadata/all?${params}`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async getMetadataStatistics() {
    const response = await fetch(
      `${API_BASE_URL}/analyze/metadata/statistics`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async exportMetadata(projectId: string, format: "json" | "yaml" = "json") {
    const response = await fetch(
      `${API_BASE_URL}/analyze/${projectId}/export?format=${format}`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  // ============ DOCKER DEPLOY (Llama 3.1) ============
  async getDockerContext(projectId: string): Promise<DockerContextResponse> {
    const response = await fetch(
      `${API_BASE_URL}/docker/${projectId}/context`,
      {
        method: "GET",
        headers: this.getHeaders(),
      }
    );
    return this.handleResponse(response);
  }

  async sendDockerChat(
    projectId: string,
    payload: { message: string; logs?: string[]; instructions?: string }
  ): Promise<DockerChatResponse> {
    const response = await fetch(`${API_BASE_URL}/docker/${projectId}/chat`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    return this.handleResponse(response);
  }

  async readProjectFile(
    projectId: string,
    path: string
  ): Promise<{ success: boolean; path: string; content: string }> {
    const url = new URL(`${API_BASE_URL}/docker/${projectId}/file`);
    url.searchParams.set("path", path);
    const response = await fetch(url.toString(), {
      method: "GET",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }

  async writeProjectFile(
    projectId: string,
    payload: { path: string; content: string }
  ): Promise<{ success: boolean; path: string }> {
    const response = await fetch(`${API_BASE_URL}/docker/${projectId}/file`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(payload),
    });
    return this.handleResponse(response);
  }

  // ============ FILE / FOLDER CRUD (Deploy explorer) ============
  async createProjectFile(
    projectId: string,
    path: string,
    content: string
  ): Promise<{ success: boolean; path: string }> {
    return this.writeProjectFile(projectId, { path, content });
  }

  async createProjectFolder(
    projectId: string,
    path: string
  ): Promise<{ success: boolean; path: string }> {
    const response = await fetch(`${API_BASE_URL}/docker/${projectId}/folder`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify({ path }),
    });
    return this.handleResponse(response);
  }

  async deleteProjectPath(
    projectId: string,
    path: string
  ): Promise<{ success: boolean; path: string }> {
    const url = new URL(`${API_BASE_URL}/docker/${projectId}/path`);
    url.searchParams.set("path", path);
    const response = await fetch(url.toString(), {
      method: "DELETE",
      headers: this.getHeaders(),
    });
    return this.handleResponse(response);
  }
}

export const apiClient = new ApiClient();
