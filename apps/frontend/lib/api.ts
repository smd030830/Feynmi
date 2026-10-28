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
};

export function apiErrorMessage(error: unknown) {
  const code = error instanceof ApiError ? error.code : "";
  return MESSAGES[code] ?? "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.";
}

async function apiFetch<T>(path: string, init: RequestInit = {}, refreshToken = false) {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new ApiError(401, "unauthenticated", "not signed in");

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${await user.getIdToken(refreshToken)}`);
  if (init.body) headers.set("Content-Type", "application/json");

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
  return (await response.json()) as T;
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
