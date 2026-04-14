import { useI18n } from "../i18n";

export function FileChip({
  name,
  kind,
  previewUrl,
  onRemove,
}: {
  name: string;
  kind: "image" | "pdf" | "unknown";
  previewUrl?: string | null;
  onRemove?: () => void;
}) {
  const { t } = useI18n();

  return (
    <div className="flex items-center gap-3 rounded-full border border-slate-200 bg-white px-4 py-2 shadow-sm">
      <div className="h-7 w-7 overflow-hidden rounded-lg bg-slate-100">
        {kind === "image" && previewUrl ? (
          <img src={previewUrl} alt={name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-500">
            <span className="material-symbols-outlined text-base">{kind === "pdf" ? "picture_as_pdf" : "draft"}</span>
          </div>
        )}
      </div>
      <span className="max-w-[220px] truncate text-sm font-semibold text-slate-800">{name}</span>
      {onRemove ? (
        <button
          onClick={onRemove}
          aria-label={t("common.removeFile", { name })}
          className="rounded-full p-1 text-slate-400 transition hover:bg-slate-100 hover:text-rose-500"
        >
          <span className="material-symbols-outlined text-sm">close</span>
        </button>
      ) : null}
    </div>
  );
}
