import { EnglishShell } from "@/components/english/shell";
import { VocabSession } from "@/components/english/vocab-session";

export default function Page() {
  return (
    <EnglishShell active="/tu-vung">
      <VocabSession />
    </EnglishShell>
  );
}
