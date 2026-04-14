import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import bananaMark from "../assets/banana-mark.png";
import { useI18n } from "../i18n";

export function Shell({
  title,
  subtitle,
  children,
  contentWidth = "default",
  contentPadding = "default",
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  contentWidth?: "default" | "wide" | "full";
  contentPadding?: "default" | "flush-left";
}) {
  const { locale, setLocale, finalizeLocaleSelection, isLocaleBannerVisible, localeOptions, t } = useI18n();
  const widthClass =
    contentWidth === "full" ? "max-w-none" : contentWidth === "wide" ? "max-w-[1600px]" : "max-w-6xl";
  const paddingClass = contentPadding === "flush-left" ? "py-10 pr-6 pl-0 lg:pr-10 lg:pl-0" : "px-6 py-10 lg:px-10";

  return (
    <div className="min-h-screen bg-surface text-ink">
      <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-slate-50/80 backdrop-blur-xl">
        <div className="flex h-16 w-full items-center pr-6 pl-10 lg:pr-10 lg:pl-12">
          <Link to="/" className="inline-flex items-center gap-1 font-headline text-xl font-extrabold tracking-tight">
            <img src={bananaMark} alt="" aria-hidden="true" className="h-11 w-auto shrink-0 object-contain" />
            <span>
              <span className="text-[#CA8A04]">banana</span>
              <span className="text-slate-900">slides</span>
            </span>
          </Link>
        </div>
        <div
          className={`overflow-hidden border-t border-slate-200/80 bg-white/90 transition-[max-height,opacity] duration-300 ${
            isLocaleBannerVisible ? "max-h-40 opacity-100" : "max-h-0 opacity-0"
          }`}
        >
          <div className="flex flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-10">
            <p className="max-w-3xl text-sm leading-6 text-slate-700">{t("language.banner.message")}</p>
            <div className="flex flex-wrap items-center gap-3">
              <select
                value={locale}
                aria-label={t("language.banner.selectAria")}
                onChange={(event) => setLocale(event.target.value as typeof locale)}
                className="min-w-[13rem] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-900"
              >
                {localeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={finalizeLocaleSelection}
                className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800"
              >
                {t("language.banner.continue")}
              </button>
              <button
                type="button"
                aria-label={t("language.banner.closeAria")}
                onClick={finalizeLocaleSelection}
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className={paddingClass}>
        <div className={`mx-auto ${widthClass}`}>
          {(title || subtitle) && (
            <header className="mb-10 space-y-3">
              {subtitle ? (
                <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-muted">{subtitle}</p>
              ) : null}
              {title ? (
                <h1 className="font-headline text-4xl font-extrabold tracking-tight text-ink md:text-5xl">
                  {title}
                </h1>
              ) : null}
            </header>
          )}
          {children}
        </div>
      </main>
    </div>
  );
}
