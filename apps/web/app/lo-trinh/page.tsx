import { RoadmapView } from "@/components/english/roadmap-view";
import { EnglishShell } from "@/components/english/shell";

export default function Page() {
  return (
    <EnglishShell active="/lo-trinh">
      <RoadmapView />
    </EnglishShell>
  );
}
