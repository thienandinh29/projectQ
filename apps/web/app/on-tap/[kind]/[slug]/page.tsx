import { notFound } from "next/navigation";
import { RunPage } from "@/components/english/run-page";
import { EnglishShell } from "@/components/english/shell";

const KINDS = { "cot-moc": "milestone", phan: "practice" } as const;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export default async function Page({
  params,
}: {
  params: Promise<{ kind: string; slug: string }>;
}) {
  const { kind, slug } = await params;
  const run = KINDS[kind as keyof typeof KINDS];
  if (!run || !SLUG.test(slug)) notFound();
  return (
    <EnglishShell active="/lo-trinh">
      <RunPage kind={run} slug={slug} />
    </EnglishShell>
  );
}
