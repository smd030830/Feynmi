import { ApiError, getMe, type Me } from "@/lib/api";

// 계정 조회만 재시도한다. 가입·업로드 등 쓰기 요청은 자동으로 반복하지 않는다.
export async function loadAccount(refreshToken = false): Promise<Me> {
  try {
    return await getMe(refreshToken);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401 && error.code === "unauthenticated" && !refreshToken) {
      return getMe(true);
    }
    if ([0, 429, 502, 503, 504].includes(error.status)) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return getMe(refreshToken);
    }
    throw error;
  }
}
