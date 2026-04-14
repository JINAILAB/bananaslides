import type { JobStatus } from "../lib/types";
import { useI18n } from "../i18n";

const CLASSES: Record<JobStatus, string> = {
  uploaded: "bg-slate-100 text-slate-700",
  prepared: "bg-slate-100 text-slate-700",
  processing: "bg-primary-soft text-primary",
  awaiting_review: "bg-sky-100 text-sky-700",
  rebuilding_slide: "bg-amber-100 text-amber-700",
  building_deck: "bg-amber-100 text-amber-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const { t } = useI18n();
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${CLASSES[status]}`}>
      {t(`status.${status}`)}
    </span>
  );
}
