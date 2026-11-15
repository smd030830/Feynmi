import type { Metadata } from "next";
import { LegalDocument, LegalSection } from "@/components/legal-document";

export const metadata: Metadata = { title: "개인정보 처리방침 · Feynmi" };

export default function PrivacyPage() {
  return (
    <LegalDocument title="개인정보 처리방침">
      <LegalSection title="1. 처리하는 정보">
        <ul className="list-disc space-y-2 pl-5">
          <li>계정: 이메일, 로그인 수단, 이메일 인증 상태, 닉네임, 선택한 프로필 이미지</li>
          <li>학습자료: 프로젝트 이름과 설명, 업로드한 원본 파일, 추출 텍스트·그림 글자와 근거 위치, 개념과 채점 기준</li>
          <li>학습기록: 질문과 답변, 요소별 판정, 이해 상태와 점수, 피드백, 세션 시작·종료 시각</li>
          <li>서비스 설정: AI 질문 난이도, 학습 알림, 주간 학습 목표, 외부 AI 전송 동의 시각</li>
          <li>로그인 기록: 로그인 시각과 브라우저·운영체제 요약. 로그인 기록에 IP 주소를 저장하지 않습니다.</li>
        </ul>
      </LegalSection>
      <LegalSection title="2. 이용 목적">
        <p>로그인과 본인 확인, 본인 자료에 대한 접근 제한, 자료 분석과 학습 피드백 제공, 학습 현황·통계·기록 표시, 계정과 설정 관리, 회원 탈퇴 처리를 위해 정보를 사용합니다.</p>
      </LegalSection>
      <LegalSection title="3. 외부 AI로 전송하는 내용">
        <p>OpenAI API에 자료에서 추출한 텍스트와 필요한 이미지, 개념·채점 기준, 관련 근거, 현재 세션에서 제출한 학습 답변을 전송해 개념 추출·글자 읽기·답변 평가·추가 질문·피드백을 처리합니다. 설정에 따라 OpenRouter 중계를 거쳐 OpenAI 모델을 호출할 수 있습니다.</p>
        <p>이메일, 닉네임이나 프로필 이미지를 학습 평가 입력으로 사용하지 않습니다. 다만 학습자료나 답변에 직접 적은 개인정보는 자료 내용의 일부로 전송될 수 있으므로, 불필요한 개인정보는 업로드 전에 지워 주세요. 첫 업로드 전에 외부 AI 전송 동의를 받습니다.</p>
      </LegalSection>
      <LegalSection title="4. 인증과 보관">
        <p>인증에는 Firebase Authentication을 사용합니다. 프로젝트와 학습기록은 데이터베이스에, 업로드 원본과 프로필 이미지는 비공개 Cloud Storage에 보관합니다.</p>
        <p>본인 계정으로만 자신의 자료와 기록에 접근할 수 있도록 인증을 확인합니다. 업로드한 자료를 다른 학습자에게 공개하는 기능은 제공하지 않습니다.</p>
      </LegalSection>
      <LegalSection title="5. 보관 기간과 삭제">
        <p>계정을 이용하는 동안 학습을 이어서 확인할 수 있도록 자료와 기록을 보관합니다. 회원 탈퇴 시 Firebase 계정, DB의 모든 사용자 데이터, Cloud Storage의 원본 자료와 프로필 이미지를 삭제합니다. 삭제한 데이터는 복구할 수 없습니다.</p>
        <p>외부 저장소나 인증 서비스의 오류로 삭제가 완료되지 않으면 계정을 삭제 중으로 유지해 일반 이용을 막고 삭제를 재시도합니다.</p>
      </LegalSection>
      <LegalSection title="6. 정보 확인과 설정">
        <p>설정에서 닉네임과 프로필 이미지를 변경하고 최근 로그인 기록을 확인할 수 있습니다. 학습기록 메뉴에서 자신의 답변과 결과를 확인할 수 있으며, 학습 알림을 끄거나 모든 기기에서 로그아웃하고 회원 탈퇴를 요청할 수 있습니다.</p>
      </LegalSection>
    </LegalDocument>
  );
}
