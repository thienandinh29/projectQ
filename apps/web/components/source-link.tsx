import { ExternalLink } from "lucide-react";
import { safeSourceUrl } from "@/lib/safety";
import { vi as t } from "@/messages/vi";

export function SourceLink({
  url,
  title,
  section,
  page,
}: {
  url?: string;
  title?: string;
  section?: string;
  page?: number;
}) {
  const href = safeSourceUrl(url, page);
  if (!href)
    return <span className="source-unavailable">{t.flow.sourceMissing}</span>;
  return (
    <a
      className="source-link"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {title || t.flow.sourceUnknown}
      {section && <span> · {section}</span>}
      <ExternalLink size={13} />
    </a>
  );
}
