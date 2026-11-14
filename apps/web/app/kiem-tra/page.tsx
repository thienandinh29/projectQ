import { LevelTest } from "@/components/english/level-test";
import { EnglishShell } from "@/components/english/shell";

export default function Page() {
  return (
    <EnglishShell active="/kiem-tra">
      <LevelTest />
    </EnglishShell>
  );
}
