import { FailureScreen } from "@/components/failure-screen";

export default function NotFound() {
  return <FailureScreen title="페이지를 찾을 수 없어요" description="주소가 올바른지 확인하거나 홈에서 원하는 프로젝트를 찾아주세요." />;
}
