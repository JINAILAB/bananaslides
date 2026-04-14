import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { FileChip } from "../components/FileChip";
import { Shell } from "../components/Shell";
import { StatusBadge } from "../components/StatusBadge";
import { useI18n } from "../i18n";
import { API_BASE_URL, createJob, fetchJob, prepareJob, processJob } from "../lib/api";
import type { JobMode, JobRecord, JobStatus } from "../lib/types";

type StagedFile = {
  id: string;
  file: File;
  previewUrl: string | null;
  kind: "image" | "pdf" | "unknown";
};

type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

function detectKind(file: File): "image" | "pdf" | "unknown" {
  if (file.type.startsWith("image/")) {
    return "image";
  }
  if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
    return "pdf";
  }
  return "unknown";
}

function releasePreviewUrls(files: StagedFile[]) {
  for (const file of files) {
    if (file.previewUrl) {
      URL.revokeObjectURL(file.previewUrl);
    }
  }
}

function currentTitle(job: JobRecord | null, t: TranslateFn) {
  if (!job) {
    return {
      title: t("upload.title.idle"),
      subtitle: undefined,
    };
  }
  if (job.status === "completed") {
    return {
      title: t("upload.title.completed"),
      subtitle: t("upload.subtitle.completed"),
    };
  }
  if (job.status === "failed") {
    return {
      title: t("upload.title.failed"),
      subtitle: t("upload.subtitle.failed"),
    };
  }
  return {
    title: t("upload.title.processing"),
    subtitle: undefined,
  };
}

export function UploadPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const filesRef = useRef<StagedFile[]>([]);
  const [files, setFiles] = useState<StagedFile[]>([]);
  const [mode, setMode] = useState<JobMode>("auto");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobRecord | null>(null);

  const jobId = searchParams.get("job");
  const totalCount = files.length;
  const estimatedSeconds = useMemo(() => Math.max(20, totalCount * (mode === "auto" ? 15 : 25)), [mode, totalCount]);
  const titleCopy = currentTitle(job, t);
  const processingSteps: Array<{ status: JobStatus; label: string; description: string }> = [
    {
      status: "uploaded",
      label: t("upload.processingSteps.uploaded.label"),
      description: t("upload.processingSteps.uploaded.description"),
    },
    {
      status: "prepared",
      label: t("upload.processingSteps.prepared.label"),
      description: t("upload.processingSteps.prepared.description"),
    },
    {
      status: "processing",
      label: t("upload.processingSteps.processing.label"),
      description: t("upload.processingSteps.processing.description"),
    },
    {
      status: "building_deck",
      label: t("upload.processingSteps.building_deck.label"),
      description: t("upload.processingSteps.building_deck.description"),
    },
    {
      status: "completed",
      label: t("upload.processingSteps.completed.label"),
      description: t("upload.processingSteps.completed.description"),
    },
  ];

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    return () => {
      releasePreviewUrls(filesRef.current);
    };
  }, []);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    const activeJobId = jobId;

    let cancelled = false;

    async function poll() {
      try {
        const nextJob = await fetchJob(activeJobId);
        if (cancelled) {
          return;
        }
        setJob(nextJob);
        setError(null);
        if (nextJob.mode === "review" && nextJob.status === "awaiting_review") {
          navigate(`/jobs/${activeJobId}/review?slide=1`, { replace: true });
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : t("upload.error.loadJob"));
        }
      }
    }

    void poll();
    const handle = window.setInterval(poll, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [jobId, navigate]);

  function appendFiles(nextFiles: FileList | File[]) {
    const staged = Array.from(nextFiles).map((file) => ({
      id: `${file.name}-${file.lastModified}-${Math.random().toString(16).slice(2, 8)}`,
      file,
      previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      kind: detectKind(file),
    }));
    setFiles((current) => [...current, ...staged]);
    setError(null);
  }

  async function handleStart() {
    if (!files.length || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createJob(
        mode,
        files.map((item) => item.file),
      );
      releasePreviewUrls(files);
      setFiles([]);
      setSearchParams({ job: created.job_id }, { replace: true });
      const prepared = await prepareJob(created.job_id);
      setJob(prepared);
      await processJob(created.job_id);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : t("upload.error.startConversion"));
      setSearchParams({}, { replace: true });
    } finally {
      setSubmitting(false);
    }
  }

  const processingJob =
    job &&
    job.status !== "completed" &&
    job.status !== "failed" &&
    !(job.mode === "review" && job.status === "awaiting_review");

  return (
    <Shell title={titleCopy.title} subtitle={titleCopy.subtitle}>
      <div className="space-y-8">
        {!job && (
          <>
            <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr] xl:items-start">
              <section
                className="rounded-[2.5rem] border border-slate-200 bg-white p-8 shadow-soft"
                onDragOver={(event) => {
                  event.preventDefault();
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  appendFiles(event.dataTransfer.files);
                }}
              >
                <div className="rounded-[2rem] border-2 border-dashed border-outline bg-surface-low px-6 py-14 text-center transition hover:border-primary/50 hover:bg-white">
                  <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-white text-primary shadow-soft">
                    <span className="material-symbols-outlined text-5xl">cloud_upload</span>
                  </div>
                  <h2 className="font-headline text-3xl font-extrabold tracking-tight text-slate-900">
                    {t("upload.dropZone.title")}
                  </h2>
                  <p className="mt-3 text-base font-medium text-muted">{t("upload.dropZone.support")}</p>
                  <button
                    onClick={() => inputRef.current?.click()}
                    className="mt-8 rounded-full border border-slate-200 bg-white px-8 py-3 text-sm font-semibold text-slate-800 shadow-sm transition hover:shadow-md"
                  >
                    {t("upload.dropZone.browse")}
                  </button>
                  <input
                    ref={inputRef}
                    type="file"
                    hidden
                    multiple
                    accept=".pdf,image/*,.tif,.tiff,.bmp,.webp"
                    onChange={(event) => {
                      if (event.target.files) {
                        appendFiles(event.target.files);
                        event.target.value = "";
                      }
                    }}
                  />
                </div>

                <div className="mt-6 border-t border-slate-200 pt-5">
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">{t("upload.selectedFiles")}</h3>
                    <span className="text-xs font-medium text-muted">{t("upload.stagedCount", { count: totalCount })}</span>
                  </div>
                  {files.length ? (
                    <div className="flex flex-wrap gap-3">
                      {files.map((item) => (
                        <FileChip
                          key={item.id}
                          name={item.file.name}
                          kind={item.kind}
                          previewUrl={item.previewUrl}
                          onRemove={() => {
                            if (item.previewUrl) {
                              URL.revokeObjectURL(item.previewUrl);
                            }
                            setFiles((current) => current.filter((file) => file.id !== item.id));
                          }}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-[1.5rem] border border-slate-200 bg-surface-low px-5 py-4 text-sm text-muted">
                      {t("upload.emptySelectedFiles")}
                    </div>
                  )}
                </div>
              </section>

              <div className="space-y-6 rounded-[2.5rem] border border-slate-200 bg-white p-8 shadow-soft">
                <div className="space-y-4">
                  <div className="space-y-3">
                    <h2 className="font-headline text-2xl font-extrabold tracking-tight text-slate-900">
                      {t("upload.strategy.title")}
                    </h2>
                    <p className="max-w-xl text-base leading-7 text-muted">
                      {t("upload.strategy.description")}
                    </p>
                  </div>
                  <div className="grid items-stretch gap-4 sm:grid-cols-2">
                    <button
                      onClick={() => setMode("auto")}
                      className={`flex h-[248px] w-full flex-col justify-between rounded-[2rem] border-2 p-6 text-left transition ${
                        mode === "auto"
                          ? "border-primary bg-primary-soft/40 shadow-sm"
                          : "border-slate-200 bg-surface-low hover:border-slate-300"
                      }`}
                    >
                      <div className="mb-3 flex items-start justify-between">
                        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-soft text-primary">
                          <span className="material-symbols-outlined text-[28px]">bolt</span>
                        </div>
                        {mode === "auto" ? <span className="material-symbols-outlined text-primary">check_circle</span> : null}
                      </div>
                      <h3 className="font-headline text-xl font-extrabold text-slate-900">{t("upload.strategy.auto.title")}</h3>
                      <p className="mt-2 text-sm leading-7 text-muted">
                        {t("upload.strategy.auto.description")}
                      </p>
                    </button>

                    <button
                      onClick={() => setMode("review")}
                      className={`flex h-[248px] w-full flex-col justify-between rounded-[2rem] border-2 p-6 text-left transition ${
                        mode === "review"
                          ? "border-primary bg-primary-soft/40 shadow-sm"
                          : "border-slate-200 bg-surface-low hover:border-slate-300"
                      }`}
                    >
                      <div className="mb-3 flex items-start justify-between">
                        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-sky-100 text-sky-700">
                          <span className="material-symbols-outlined text-[28px]">visibility</span>
                        </div>
                        {mode === "review" ? <span className="material-symbols-outlined text-primary">check_circle</span> : null}
                      </div>
                      <h3 className="font-headline text-xl font-extrabold text-slate-900">{t("upload.strategy.review.title")}</h3>
                      <p className="mt-2 text-sm leading-7 text-muted">
                        {t("upload.strategy.review.description")}
                      </p>
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-4 border-t border-slate-200 pt-6">
                  <div className="flex items-center gap-2 text-sm text-muted">
                    <span className="material-symbols-outlined text-base">info</span>
                    <span>
                      {t("upload.estimatedTime")} <strong>{t("common.secondsCount", { count: estimatedSeconds })}</strong>
                    </span>
                  </div>
                  {error ? <p className="text-sm font-medium text-rose-600">{error}</p> : null}
                  <button
                    onClick={handleStart}
                    disabled={!files.length || submitting}
                    className="inline-flex w-fit items-center gap-3 rounded-full bg-hero px-8 py-3.5 font-headline text-base font-extrabold tracking-tight text-white shadow-soft transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submitting ? t("upload.starting") : t("upload.start")}
                    <span className="material-symbols-outlined">arrow_forward</span>
                  </button>
                </div>
              </div>
            </section>
          </>
        )}

        {job && (
          <>
            <section className="grid gap-6 xl:grid-cols-[1.2fr_0.9fr]">
              <div className="rounded-[2.5rem] border border-slate-200 bg-white p-8 shadow-soft">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="font-headline text-2xl font-extrabold tracking-tight text-slate-900">
                      {t("upload.currentJob.title")}
                    </h2>
                    <p className="mt-2 text-sm leading-7 text-muted">
                      {t("upload.currentJob.description", {
                        jobId: job.job_id,
                        mode: t(`mode.${job.mode}`),
                      })}
                    </p>
                  </div>
                  <StatusBadge status={job.status} />
                </div>

                {job.uploads.length > 0 ? (
                  <div className="mt-6 flex flex-wrap gap-3">
                    {job.uploads.map((upload) => (
                      <FileChip
                        key={upload.upload_id}
                        name={upload.original_name}
                        kind={upload.kind === "pdf" ? "pdf" : upload.kind === "image" ? "image" : "unknown"}
                      />
                    ))}
                  </div>
                ) : null}

                {processingJob ? (
                  <div className="mt-8 space-y-3">
                    {processingSteps.map((step) => {
                      const active = job.status === step.status;
                      const completed =
                        processingSteps.findIndex((item) => item.status === job.status) >=
                        processingSteps.findIndex((item) => item.status === step.status);
                      return (
                        <div
                          key={step.status}
                          className="flex items-center gap-4 rounded-[1.5rem] border border-slate-100 bg-surface-low px-5 py-4"
                        >
                          <div
                            className={`flex h-10 w-10 items-center justify-center rounded-full ${
                              active || completed ? "bg-primary text-white" : "bg-slate-200 text-slate-500"
                            }`}
                          >
                            <span className="material-symbols-outlined text-lg">
                              {completed ? "check" : active ? "autorenew" : "radio_button_unchecked"}
                            </span>
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{step.label}</p>
                            <p className="text-sm text-muted">{step.description}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}

                {job.status === "failed" ? (
                  <div className="mt-8 rounded-[1.5rem] border border-rose-200 bg-rose-50 px-5 py-4">
                    <p className="text-sm font-semibold text-rose-700">{t("upload.failure.title")}</p>
                    <p className="mt-2 text-sm text-rose-700">{job.error || t("upload.failure.unknown")}</p>
                  </div>
                ) : null}
              </div>

              <aside className="space-y-6">
                <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-soft">
                  <h3 className="font-headline text-xl font-extrabold text-slate-900">{t("upload.summary.title")}</h3>
                  <dl className="mt-5 space-y-4 text-sm">
                    <div className="flex items-center justify-between">
                      <dt className="text-muted">{t("upload.summary.uploads")}</dt>
                      <dd className="font-semibold text-slate-900">{job.uploads.length}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-muted">{t("upload.summary.slides")}</dt>
                      <dd className="font-semibold text-slate-900">{job.slides.length}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-muted">{t("upload.summary.mode")}</dt>
                      <dd className="font-semibold text-slate-900">{t(`mode.${job.mode}`)}</dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-muted">{t("upload.summary.status")}</dt>
                      <dd className="font-semibold text-slate-900">{t(`status.${job.status}`)}</dd>
                    </div>
                  </dl>
                </section>

                {job.status === "completed" && (
                  <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-soft">
                    <h3 className="font-headline text-xl font-extrabold text-slate-900">{t("upload.download.title")}</h3>
                    <p className="mt-3 text-sm leading-7 text-muted">
                      {t("upload.download.description")}
                    </p>
                    <div className="mt-6 flex flex-wrap gap-3">
                      <a
                        href={`${API_BASE_URL}/jobs/${job.job_id}/download`}
                        className="inline-flex items-center gap-3 rounded-full bg-hero px-6 py-3 font-headline text-sm font-bold text-white shadow-soft"
                      >
                        {t("upload.download.button")}
                        <span className="material-symbols-outlined text-base">sim_card_download</span>
                      </a>
                    </div>
                  </section>
                )}

                {job.status !== "completed" && (
                  <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-soft">
                    <h3 className="font-headline text-xl font-extrabold text-slate-900">{t("upload.next.title")}</h3>
                    <p className="mt-3 text-sm leading-7 text-muted">
                      {t("upload.next.description")}
                    </p>
                  </section>
                )}
              </aside>
            </section>

            {error ? <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</div> : null}
          </>
        )}
      </div>
    </Shell>
  );
}
