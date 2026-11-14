import { About } from "@/components/english/about";
import { EnglishShell } from "@/components/english/shell";

export default function Page() {
  return (
    <EnglishShell active="/gioi-thieu">
      <About />
    </EnglishShell>
  );
}
