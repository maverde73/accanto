import Link from "next/link";

import { can } from "@/lib/presence";

type Tab = "presenza" | "mappa" | "contatto";

/** Tabs appear only where the grant allows them.
 *
 * A caregiver without location should not see a Map tab that leads to an empty
 * page: the absence of the tab is itself the honest answer.
 */
export function BottomNav({
  subjectId,
  active,
  scopes,
}: {
  subjectId: string;
  active: Tab;
  scopes: string[];
}) {
  const tabs: Array<{ key: Tab; label: string; href: string; visible: boolean }> = [
    { key: "presenza", label: "Presenza", href: `/s/${subjectId}`, visible: true },
    {
      key: "mappa",
      label: "Mappa",
      href: `/s/${subjectId}/mappa`,
      visible: can(scopes, "location:coarse") || can(scopes, "location:precise"),
    },
    {
      key: "contatto",
      label: "Contatto",
      href: `/s/${subjectId}/contatto`,
      visible: can(scopes, "escalation:notify"),
    },
  ];

  return (
    <nav className="bottomnav">
      {tabs
        .filter((tab) => tab.visible)
        .map((tab) => (
          <Link
            key={tab.key}
            href={tab.href}
            className="navitem"
            data-active={tab.key === active}
            aria-current={tab.key === active ? "page" : undefined}
          >
            <span className="navdot" />
            <span>{tab.label}</span>
          </Link>
        ))}
    </nav>
  );
}
