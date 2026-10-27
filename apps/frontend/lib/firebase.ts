import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

let auth: Auth | undefined;

// 처음 쓸 때 초기화한다. 모듈을 불러올 때 초기화하면 환경변수가 없는 빌드(CI)의 사전 렌더링이 실패한다.
export function getFirebaseAuth() {
  if (!auth) {
    const app = getApps().length
      ? getApp()
      : initializeApp({
          apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
          authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
          projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
          appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
        });
    auth = getAuth(app);
    // 재설정 메일과 구글 로그인 창을 한국어로 띄운다
    auth.languageCode = "ko";
  }
  return auth;
}
