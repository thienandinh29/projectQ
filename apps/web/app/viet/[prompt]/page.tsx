import { notFound } from "next/navigation";
import { EssayEditor } from "@/components/english/essay-editor";
import { EnglishShell } from "@/components/english/shell";

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export default async function Page({
  params,
}: {
  params: Promise<{ prompt: string }>;
}) {
  const { prompt } = await params;
  if (!SLUG.test(prompt) || prompt.length > 40) notFound();
  return (
    <EnglishShell active="/viet">
      <EssayEditor promptId={prompt} />
    </EnglishShell>
  );
}
