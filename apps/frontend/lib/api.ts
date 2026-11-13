import { getFirebaseAuth } from "@/lib/firebase";

// 백엔드 API 호출 (architecture.md 4.2, 8). 호출 직전에 ID 토큰을 받아 Bearer로 붙인다.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

export type Me = {
  nickname: string | null;
  email: string;
  sign_in_provider: "password" | "google.com";
  email_verified: boolean;
  ai_consent_at: string | null;
  avatar_url: string | null;
};

export type ProjectColor = "indigo" | "lavender" | "cyan";

export type StateCounts = {
  understood: number;
  partial: number;
  misconception: number;
  not_studied: number;
};

export type Project = {
  id: string;
  name: string;
  description: string | null;
  color: ProjectColor;
  score: number | null; // 프로젝트 이해도. null이면 학습한 개념이 없음
  state_counts: StateCounts;
  material_count: number;
  created_at: string;
};

export type MaterialStatus =
  | "pending_upload"
  | "queued"
  | "extracting"
  | "generating_concepts"
  | "ready"
  | "failed";

export type Material = {
  id: string;
  title: string;
  file_type: "pdf" | "pptx" | "png" | "jpg";
  size_bytes: number;
  page_count: number | null;
  status: MaterialStatus;
  failure_code: string | null;
  chunk_count: number; // DB에 임베딩까지 저장된 조각 수
  created_at: string;
};

export type MaterialPage = { number: number; text: string };

export type ProjectList = {
  items: Project[];
  next_color: ProjectColor;
};

// code는 architecture.md 8.2의 오류 코드. 네트워크 실패는 "network_error"로 둔다.
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

// 사용자에게 보여줄 한국어 문구는 code로 정한다 (message는 디버깅용).
const MESSAGES: Record<string, string> = {
  network_error: "서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도해주세요.",
  unauthenticated: "로그인이 필요합니다. 다시 로그인해주세요.",
  token_revoked: "로그아웃된 기기입니다. 다시 로그인해주세요.",
  email_not_verified: "이메일 인증을 먼저 완료해주세요.",
  profile_required: "닉네임을 먼저 설정해주세요.",
  validation_error: "입력한 내용을 확인해주세요.",
  not_found: "찾을 수 없거나 접근할 수 없는 항목입니다.",
  invalid_state: "이미 종료되었거나 현재 처리할 수 없는 요청입니다.",
  evaluation_in_progress: "설명을 분석하고 있어요. 잠시 후 다시 확인해주세요.",
  llm_failed: "AI 분석을 완료하지 못했어요. 작성한 답변은 보관되며 다시 보낼 수 있어요.",
  account_deleting: "회원 탈퇴를 처리하고 있어요. 잠시 후 다시 확인해주세요.",
  cloud_unavailable: "계정 서비스를 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
  consent_required: "자료를 올리기 전에 외부 AI 전송 안내에 동의해주세요.",
  unsupported_format: "지원하지 않는 형식입니다. PDF, PPTX, PNG, JPG만 올릴 수 있어요.",
  file_too_large: "파일이 너무 큽니다. 파일당 50MB까지 올릴 수 있어요.",
  empty_file: "빈 파일입니다. 내용이 있는 파일을 올려주세요.",
};

// 분석 실패 사유 (materials.failure_code, PRD FR-1.4, FR-1.7)
const FAILURE_MESSAGES: Record<string, string> = {
  unsupported_format: "지원하지 않는 형식이에요. 파일 내용이 확장자와 다를 수 있어요.",
  file_too_large: "파일이나 그림이 너무 커요.",
  too_many_pages: "쪽수가 너무 많아요. 300쪽(슬라이드)까지 분석할 수 있어요.",
  no_extractable_text: "글자를 찾지 못했어요. 글자가 보이는 자료인지 확인해주세요.",
  corrupted_file: "파일을 열 수 없어요. 손상되었거나 암호가 걸린 파일일 수 있어요.",
  llm_failed: "AI 처리 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
  internal_error: "분석 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
};

export function failureMessage(code: string | null) {
  return FAILURE_MESSAGES[code ?? ""] ?? FAILURE_MESSAGES.internal_error;
}

export function apiErrorMessage(error: unknown) {
  const code = error instanceof ApiError ? error.code : "";
  return MESSAGES[code] ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

async function apiFetch<T>(path: string, init: RequestInit = {}, refreshToken = false) {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new ApiError(401, "unauthenticated", "not signed in");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await user.getIdToken(refreshToken)}`);
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error", "network request failed");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      body?.error?.code ?? "internal_error",
      body?.error?.message ?? response.statusText,
    );
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

// refreshToken: 이메일 인증 직후처럼 토큰의 클레임을 갱신해야 할 때 true
export function getMe(refreshToken = false) {
  return apiFetch<Me>("/me", {}, refreshToken);
}

export function updateProfile(nickname: string) {
  return apiFetch<Me>("/me/profile", { method: "PATCH", body: JSON.stringify({ nickname }) });
}

export function listProjects() {
  return apiFetch<ProjectList>("/projects");
}

export function createProject(name: string, description: string) {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ name, description: description || null }),
  });
}

export function getProject(id: string) {
  return apiFetch<Project>(`/projects/${encodeURIComponent(id)}`);
}

export type ConceptState = "not_studied" | "partial" | "misconception" | "understood";
export type Concept = {
  id: string; title: string; description: string; state: ConceptState; score: number | null;
  material_id: string; material_title: string;
};
export type LearningMessage = {
  id: string; seq: number; role: "question" | "answer"; text: string; created_at: string;
};
export type Evidence = { id: string; material_title: string; page_start: number; page_end: number };
export type Assessment = {
  id: string; seq: number; state: ConceptState; score: number; created_at: string;
  elements: {
    element_id: string; text: string; importance: "core" | "supporting";
    verdict: "met" | "partial" | "missing" | "contradicted";
    learner_quote: string | null; evidence: Evidence[]; note?: string | null;
  }[];
  feedback: {
    correct: string[]; missing_hint?: string[]; missing?: string[]; incorrect?: string[];
    supplement?: string; summary_points?: string[];
    unverified_statements?: { learner_quote: string; note: string }[];
  };
};
export type LearningSession = {
  id: string; concept_id: string; concept_title: string; project_id: string; project_name: string;
  status: "in_progress" | "completed" | "aborted"; end_reason: string | null;
  followups_used: number; started_at: string; ended_at: string | null;
  messages: LearningMessage[]; assessments: Assessment[]; score_change: number | null;
  remaining_core_count: number | null;
  recommendation: null | {
    concept_id: string; concept_title: string; project_id: string; project_name: string;
    state: ConceptState; score: number | null; reason: string;
  };
};
export function listConcepts(projectId: string) {
  return apiFetch<{ items: Concept[]; recommendation: LearningSession["recommendation"] }>(`/projects/${encodeURIComponent(projectId)}/concepts`);
}
export function startSession(conceptId: string) {
  return apiFetch<LearningSession>(`/concepts/${encodeURIComponent(conceptId)}/sessions`, { method: "POST" });
}
export function getSession(id: string) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}`);
}

export function cleanupSessions() {
  return apiFetch<void>("/sessions/cleanup", { method: "POST" });
}

export type WeeklySummary = { weekly_goal_days: number; study_days: boolean[] };
export function getWeeklySummary() {
  return apiFetch<WeeklySummary>("/me/summary");
}
export function getSessionResult(id: string) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}/result`);
}
export function submitAnswer(id: string, text: string) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}/answers`, {
    method: "POST", body: JSON.stringify({ text }),
  });
}
export function abortSession(id: string) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}/abort`, { method: "POST" });
}
// pagehide에서는 비동기 토큰 조회가 끝나기 전에 문서가 닫힐 수 있어 미리 받은 토큰을 쓴다.
export function abortSessionOnExit(id: string, token: string) {
  return fetch(`${API_BASE_URL}/api/v1/sessions/${encodeURIComponent(id)}/abort`, {
    method: "POST", headers: { Authorization: `Bearer ${token}` }, keepalive: true,
  });
}

export type LearningSettings = {
  question_depth: "basic" | "deep"; notifications_enabled: boolean; weekly_goal_days: number;
};
export type LoginEvent = { id: string; occurred_at: string; client_summary: string };
export function getLearningSettings() { return apiFetch<LearningSettings>("/me/settings"); }
export function saveLearningSettings(settings: Partial<LearningSettings>) {
  return apiFetch<LearningSettings>("/me/settings", { method: "PATCH", body: JSON.stringify(settings) });
}
export function getLoginEvents() { return apiFetch<{ items: LoginEvent[] }>("/me/login-events"); }
export function recordLogin() { return apiFetch<LoginEvent>("/me/login-events", { method: "POST" }); }
export function revokeSessions() { return apiFetch<{ ok: boolean }>("/me/revoke-sessions", { method: "POST" }); }
export function deleteAccount() {
  return apiFetch<void>("/me", { method: "DELETE", body: JSON.stringify({ confirm: "탈퇴" }) });
}
export function uploadAvatar(file: File) {
  return apiFetch<{ avatar_url: string }>("/me/avatar", {
    method: "POST", headers: { "Content-Type": file.type }, body: file,
  });
}

export function giveAiConsent() {
  return apiFetch<Me>("/me/ai-consent", { method: "POST" });
}

export function listMaterials(projectId: string) {
  return apiFetch<{ items: Material[] }>(`/projects/${encodeURIComponent(projectId)}/materials`);
}

export function uploadMaterial(projectId: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<Material>(`/projects/${encodeURIComponent(projectId)}/materials`, {
    method: "POST",
    body,
  });
}

export function retryMaterial(materialId: string) {
  return apiFetch<Material>(`/materials/${encodeURIComponent(materialId)}/retry`, {
    method: "POST",
  });
}

export function getMaterialPages(materialId: string) {
  return apiFetch<{ pages: MaterialPage[] }>(`/materials/${encodeURIComponent(materialId)}/pages`);
}
