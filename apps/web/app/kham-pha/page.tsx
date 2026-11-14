import { Workspace } from "@/components/workspace";
import { getWebConfig } from "@/lib/config";
export const dynamic = "force-dynamic";
export default function Page() {
  return <Workspace config={getWebConfig()} />;
}
