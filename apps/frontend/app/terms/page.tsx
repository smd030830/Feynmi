import type { Metadata } from "next";
import Link from "next/link";
import { LegalDocument, LegalSection } from "@/components/legal-document";

export const metadata: Metadata = { title: "이용약관 · Feynmi" };

export default function TermsPage() {
  return (
    <LegalDocument title="이용약관">
      <LegalSection title="1. 서비스 소개">
        <p>Feynmi(파인마이)는 학습자료를 올리고 개념을 자신의 말로 설명하면 AI가 이해 상태와 피드백을 제공하는 한국어 학습 서비스입니다. 현재 공모전·졸업작품을 위한 PC 웹 시험 서비스로 제공됩니다.</p>
      </LegalSection>
      <LegalSection title="2. 계정과 본인 자료">
        <p>이메일 또는 Google 계정으로 로그인하며, 이메일 가입자는 이메일 인증과 닉네임 설정을 마쳐야 학습 기능을 이용할 수 있습니다. 본인의 계정과 자료는 본인이 관리해야 합니다.</p>
        <p>프로젝트, 학습자료, 답변, 판정과 학습기록은 본인만 접근할 수 있습니다. 다른 학습자에게 자료를 공개하거나 공유하는 기능은 제공하지 않습니다.</p>
      </LegalSection>
      <LegalSection title="3. 개인 학습과 저작권">
        <p>업로드 자료는 본인의 개인 학습을 위해서만 사용해 주세요. 직접 작성했거나 이용 권한이 있는 자료를 올리고, 타인의 저작권이나 개인정보를 침해하는 자료를 올리지 않아야 합니다. 서비스 이용이 자료의 저작권이나 공개·배포 권한을 부여하는 것은 아닙니다.</p>
      </LegalSection>
      <LegalSection title="4. 외부 AI 처리">
        <p>개념 추출, 자료 속 글자 읽기, 답변 평가와 추가 질문·피드백 생성을 위해 자료 내용과 학습 답변이 외부 AI API(OpenAI)로 전송됩니다. 설정된 OpenAI 호환 중계 서비스(OpenRouter)를 거칠 수 있습니다.</p>
        <p>첫 자료 업로드 전에 전송 목적과 범위를 안내하고 별도로 동의를 받습니다. 자세한 수집 항목과 처리 내용은 <Link href="/privacy" className="font-semibold text-primary-strong underline">개인정보 처리방침</Link>에서 확인할 수 있습니다.</p>
      </LegalSection>
      <LegalSection title="5. AI 결과의 확인">
        <p>AI의 글자 인식, 개념 추출과 판정에는 오류가 있을 수 있습니다. 특히 흘림 손글씨와 복잡한 그림은 정확히 읽지 못할 수 있습니다. 결과에 표시된 자료 근거를 원본과 함께 확인해 주세요.</p>
        <p>자료에서 확인되지 않는 내용은 별도로 표시하며, 이해도 점수는 서비스의 학습 기준에 따른 피드백입니다. 학습 결과는 시험 성적이나 자격을 보장하지 않습니다.</p>
      </LegalSection>
      <LegalSection title="6. 계정 관리와 탈퇴">
        <p>설정에서 프로필과 학습 설정, 로그인 기록을 확인하고 모든 기기에서 로그아웃할 수 있습니다. 회원 탈퇴 시 Firebase 계정과 DB의 사용자 데이터, 보관된 원본 자료와 프로필 이미지를 삭제하며 복구할 수 없습니다.</p>
        <p>시험 서비스의 기능이나 안내가 변경되면 이 페이지에서 변경된 내용을 확인할 수 있습니다.</p>
      </LegalSection>
    </LegalDocument>
  );
}
