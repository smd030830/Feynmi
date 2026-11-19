import type { Schemas } from "@feynmi/api-types";
import { signOut } from "firebase/auth";
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

export type ProjectColor = Schemas["ProjectColor"];

export type StateCounts = Schemas["StateCounts"];

export type Project = Schemas["ProjectResponse"];

export type MaterialStatus = Schemas["MaterialStatus"];

export type Material = Schemas["MaterialResponse"];


export type ProjectList = Schemas["ProjectListResponse"];

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
  session_idle_timeout: "오랫동안 활동이 없어 로그아웃됐어요. 다시 로그인해주세요.",
  email_not_verified: "이메일 인증을 먼저 완료해주세요.",
  profile_required: "닉네임을 먼저 설정해주세요.",
  validation_error: "입력한 내용을 확인해주세요.",
  not_found: "찾을 수 없거나 접근할 수 없는 항목입니다.",
  invalid_state: "이미 종료되었거나 현재 처리할 수 없는 요청입니다.",
  evaluation_in_progress: "설명을 분석하고 있어요. 잠시 후 다시 확인해주세요.",
  llm_failed: "AI 분석을 완료하지 못했어요. 작성한 답변은 보관되며 다시 보낼 수 있어요.",
  off_topic_response: "현재 질문과 관련 없는 답변이에요. 학습 중인 개념을 내 말로 설명해주세요. 점수와 현재 질문은 그대로예요.",
  answer_filter_unavailable: "답변 관련성을 확인하지 못했어요. 입력한 내용을 그대로 두고 다시 시도해주세요. 점수와 현재 질문은 그대로예요.",
  account_deleting: "회원 탈퇴를 처리하고 있어요. 잠시 후 다시 확인해주세요.",
  cloud_unavailable: "계정 서비스를 연결하지 못했어요. 잠시 후 다시 시도해주세요.",
  consent_required: "자료를 올리기 전에 외부 AI 전송 안내에 동의해주세요.",
  unsupported_format:
    "지원하지 않는 형식입니다. PDF, PPTX, HWP, HWPX, DOCX, TXT, PNG, JPG, HEIC만 올릴 수 있어요. (.ppt·.doc는 새 형식으로 저장해 주세요)",
  file_too_large: "파일이 너무 큽니다. 파일당 50MB까지 올릴 수 있어요.",
  empty_file: "빈 파일입니다. 내용이 있는 파일을 올려주세요.",
  original_missing: "보관된 원본 파일을 찾을 수 없어요. 자료를 다시 올려주세요.",
  upload_failed: "파일을 올리지 못했어요. 네트워크를 확인한 뒤 다시 올려주세요.",
  upload_missing: "파일 업로드가 끝나지 않았어요. 다시 올려주세요.",
  storage_unavailable: "자료 저장소가 설정되지 않았어요. 관리자에게 문의해주세요.",
  material_busy: "업로드나 분석이 진행 중인 자료는 완료된 뒤 삭제할 수 있어요.",
  project_busy: "자료 업로드·분석이나 답변 평가가 끝난 뒤 프로젝트를 삭제해주세요.",
  assessment_in_progress: "답변을 평가하고 있어요. 평가가 끝난 뒤 다시 삭제해주세요.",
};

// 분석 실패 사유 (materials.failure_code, PRD FR-1.4, FR-1.7)
const FAILURE_MESSAGES: Record<string, string> = {
  unsupported_format: "지원하지 않는 형식이에요. 파일 내용이 확장자와 다를 수 있어요.",
  file_too_large: "파일이나 그림이 너무 커요.",
  too_many_pages: "쪽수가 너무 많아요. 300쪽(슬라이드)까지 분석할 수 있어요.",
  no_extractable_text: "글자를 찾지 못했어요. 글자가 보이는 자료인지 확인해주세요.",
  corrupted_file: "파일을 열 수 없어요. 손상되었거나 암호가 걸린 파일일 수 있어요.",
  llm_failed: "AI 처리 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
  ai_unavailable: "현재 AI 분석을 사용할 수 없어요. 서비스 연결이 준비된 뒤 다시 시도해주세요.",
  internal_error: "분석 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
};

// 사진·손글씨는 기본 글자 인식(Tesseract)이 거의 못 읽어, 엉터리 글자 대신 실패로 처리된다
const IMAGE_NO_TEXT =
  "사진이나 손글씨 속 글자를 읽지 못했어요. 인쇄된 글자가 또렷하게 보이는 캡처나 스캔으로 다시 올려주세요.";

export function failureMessage(code: string | null, fileType?: Material["file_type"]) {
  if (code === "no_extractable_text" && (fileType === "png" || fileType === "jpg" || fileType === "heic")) {
    return IMAGE_NO_TEXT;
  }
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
    if (response.status === 401 && body?.error?.code === "session_idle_timeout") {
      const auth = getFirebaseAuth();
      if (auth.currentUser === user) {
        await signOut(auth).then(() => {
          if (!auth.currentUser) window.location.replace("/login?notice=session-expired");
        }).catch(() => { /* 다음 확인에서 로그아웃을 다시 시도한다. */ });
      }
    }
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

export function checkLoginSession(background = true) {
  return apiFetch<void>("/me/session", {
    cache: "no-store",
    headers: background ? { "X-Feynmi-Background": "1" } : undefined,
  });
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

export function deleteProject(id: string) {
  return apiFetch<void>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export type ConceptState = "not_studied" | "partial" | "misconception" | "understood";
export type Concept = {
  id: string; title: string; description: string; state: ConceptState; score: number | null;
  material_id: string; material_title: string;
};
export type AnswerConfidence = Schemas["AnswerConfidence"];
export type LearningMessage = {
  id: string; seq: number; role: "question" | "answer"; text: string; created_at: string;
  confidence?: AnswerConfidence | null;
};
export type Evidence = { id: string; material_title: string; page_start: number; page_end: number; text?: string; basis_only?: boolean };
export type Assessment = {
  id: string; seq: number; state: ConceptState; score: number; created_at: string;
  answer_message_id?: string | null;
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
  concept_available?: boolean;
  project_available?: boolean;
  status: "in_progress" | "completed" | "aborted"; end_reason: string | null;
  followups_used: number; started_at: string; ended_at: string | null;
  messages: LearningMessage[]; assessments: Assessment[]; score_change: number | null;
  remaining_core_count: number | null;
  hint_source?: { material_title: string; page_start: number | null; page_end: number | null };
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

export type LearningRecord = {
  id: string;
  concept_id: string;
  concept_title: string;
  project_id: string;
  project_name: string;
  project_available?: boolean;
  started_at: string;
  ended_at: string | null;
  score: number | null;
  status: "completed" | "aborted";
};
export type RecordPage = { items: LearningRecord[]; total: number; next_cursor: string | null };

export function listRecords(projectId?: string, cursor?: string) {
  const path = projectId ? `/projects/${encodeURIComponent(projectId)}/records` : "/records";
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<RecordPage>(path + query);
}

export function deleteRecord(sessionId: string) {
  return apiFetch<void>(`/records/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
}

export function cleanupSessions() {
  return apiFetch<void>("/sessions/cleanup", { method: "POST" });
}

export type WeeklySummary = Schemas["WeeklySummary"];
export type LearningStats = Schemas["LearningStats"];
export function getLearningStats() {
  return apiFetch<LearningStats>("/me/stats");
}
export type HomeData = {
  stats: LearningStats;
  projects: Project[];
  next_color: ProjectColor;
  recommendation: LearningSession["recommendation"];
  weak_concepts: NonNullable<LearningSession["recommendation"]>[];
  notifications: { kind: "goal" | "review"; message: string; concept_id: string | null }[];
};
export function getHome() {
  return apiFetch<HomeData>("/home");
}
export function getWeeklySummary() {
  return apiFetch<WeeklySummary>("/me/summary");
}
export function getSessionResult(id: string) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}/result`);
}
export function submitAnswer(id: string, text: string, confidence?: AnswerConfidence) {
  return apiFetch<LearningSession>(`/sessions/${encodeURIComponent(id)}/answers`, {
    method: "POST", body: JSON.stringify({ text, confidence }),
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

export type LearningSettings = Schemas["SettingsResponse"];
export type LoginEvent = Schemas["LoginEventResponse"];
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

export function listMaterials(projectId: string, background = false) {
  return apiFetch<{ items: Material[] }>(`/projects/${encodeURIComponent(projectId)}/materials`, {
    headers: background ? { "X-Feynmi-Background": "1" } : undefined,
  });
}

type UploadUrl = Schemas["UploadUrlResponse"];

// 업로드 세 단계 (architecture 7.1): 주소 받기 → 저장소에 직접 PUT → 완료 알림(분석 시작)
export async function uploadMaterial(projectId: string, file: File) {
  const target = await apiFetch<UploadUrl>(
    `/projects/${encodeURIComponent(projectId)}/materials/upload-url`,
    {
      method: "POST",
      body: JSON.stringify({ filename: file.name, size: file.size, content_type: file.type }),
    },
  );
  let put: Response;
  try {
    put = await fetch(target.upload_url, {
      method: "PUT",
      headers: target.required_headers,
      body: file,
    });
  } catch {
    throw new ApiError(0, "upload_failed", "storage upload request failed");
  }
  if (!put.ok) {
    // 서명된 크기 범위를 넘으면 저장소가 거절한다
    throw new ApiError(put.status, put.status === 400 ? "file_too_large" : "upload_failed", put.statusText);
  }
  return apiFetch<Material>(
    `/materials/${encodeURIComponent(target.material_id)}/upload-complete`,
    { method: "POST" },
  );
}

export function retryMaterial(materialId: string) {
  return apiFetch<Material>(`/materials/${encodeURIComponent(materialId)}/retry`, {
    method: "POST",
  });
}

export function deleteMaterial(materialId: string) {
  return apiFetch<void>(`/materials/${encodeURIComponent(materialId)}`, { method: "DELETE" });
}

