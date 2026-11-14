import { EnglishHome } from "@/components/english/home";
import { EnglishShell } from "@/components/english/shell";

export default function Page() {
  return (
    <EnglishShell active="/">
      <EnglishHome />
    </EnglishShell>
  );
}
