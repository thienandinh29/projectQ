import { notFound } from "next/navigation";
import { EssayView } from "@/components/english/essay-view";
import { EnglishShell } from "@/components/english/shell";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!UUID.test(id)) notFound();
  return (
    <EnglishShell active="/viet">
      <EssayView essayId={id} />
    </EnglishShell>
  );
}
