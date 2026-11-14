import { EnglishShell } from "@/components/english/shell";
import { WritingHome } from "@/components/english/writing-home";

export default function Page() {
  return (
    <EnglishShell active="/viet">
      <WritingHome />
    </EnglishShell>
  );
}
