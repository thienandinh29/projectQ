import Image from "next/image";
import Link from "next/link";
import { vi } from "@/messages/vi";

const t = vi.english;
const LINKS = [
  { href: "/", label: t.nav.today },
  { href: "/lo-trinh", label: t.nav.roadmap },
  { href: "/tu-vung", label: t.homeToday.vocabTitle },
  { href: "/viet", label: t.nav.writing },
  { href: "/kiem-tra", label: t.nav.levelTest },
  { href: "/gioi-thieu", label: t.about.nav },
  { href: "/kham-pha", label: t.nav.explore },
] as const;

export function EnglishShell({
  active,
  children,
}: {
  active: (typeof LINKS)[number]["href"];
  children: React.ReactNode;
}) {
  return (
    <div className="en-shell">
      <header className="en-header">
        <Link href="/" className="en-brand">
          <Image
            src="/sena.svg"
            width={36}
            height={36}
            alt={vi.sena}
            priority
          />
          <span>
            <strong>{vi.app}</strong>
            <small>{t.brandSub}</small>
          </span>
        </Link>
        <nav className="en-nav" aria-label={vi.app}>
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={link.href === active ? "page" : undefined}
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="en-main">{children}</main>
    </div>
  );
}
