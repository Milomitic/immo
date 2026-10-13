"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from "lucide-react";

interface ImageLightboxProps {
  images: string[];
  initialIndex?: number;
  open: boolean;
  onClose: () => void;
  title?: string;
}

const SWIPE_MIN_PX = 50;

export function ImageLightbox({ images, initialIndex = 0, open, onClose, title }: ImageLightboxProps) {
  const [index, setIndex] = useState(initialIndex);
  const [zoom, setZoom] = useState(1);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const touchStartX = useRef<number | null>(null);

  useEffect(() => {
    if (open) {
      setIndex(initialIndex);
      setZoom(1);
    }
  }, [open, initialIndex]);

  const next = useCallback(() => {
    setIndex((i) => (i + 1) % images.length);
    setZoom(1);
  }, [images.length]);

  const prev = useCallback(() => {
    setIndex((i) => (i - 1 + images.length) % images.length);
    setZoom(1);
  }, [images.length]);

  // Parents pass onClose inline; reading it through a ref keeps the effects
  // below from re-running (and re-grabbing focus) on every parent render.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  // Modal focus: start on "Chiudi", hand focus back to the opener on close.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(z + 0.25, 3));
      else if (e.key === "-") setZoom((z) => Math.max(z - 0.25, 1));
      // Focus trap: Tab and Shift+Tab cycle through the dialog's buttons.
      else if (e.key === "Tab" && dialogRef.current) {
        const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled])")];
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && (active === first || !dialogRef.current.contains(active))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (active === last || !dialogRef.current.contains(active))) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    // Lock scroll while open
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, next, prev]);

  if (!open || images.length === 0) return null;

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center"
      onClick={onClose}
      onTouchStart={(e) => {
        touchStartX.current = e.touches[0].clientX;
      }}
      onTouchEnd={(e) => {
        // Swipe between photos; at zoom > 1 a drag pans the image instead.
        const start = touchStartX.current;
        touchStartX.current = null;
        if (start === null || zoom > 1 || images.length < 2) return;
        const dx = e.changedTouches[0].clientX - start;
        if (dx <= -SWIPE_MIN_PX) next();
        else if (dx >= SWIPE_MIN_PX) prev();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title || "Galleria immagini"}
    >
      {/* Screen readers hear the position change; the visible counter is
          in the top bar. */}
      <p className="sr-only" aria-live="polite">
        Foto {index + 1} di {images.length}
      </p>

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3 text-white bg-gradient-to-b from-black/60 to-transparent">
        <div className="text-sm font-medium truncate mr-4" aria-hidden="true">
          {title ? <span className="opacity-80">{title} · </span> : null}
          <span>
            {index + 1} / {images.length}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.max(z - 0.25, 1));
            }}
            disabled={zoom <= 1}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Riduci zoom"
          >
            <ZoomOut className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setZoom((z) => Math.min(z + 0.25, 3));
            }}
            disabled={zoom >= 3}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Aumenta zoom"
          >
            <ZoomIn className="h-5 w-5" />
          </button>
          <button
            ref={closeRef}
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Chiudi"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Image */}
      <div
        className="relative max-w-[95vw] max-h-[90vh] overflow-auto flex items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={images[index]}
          alt={`Foto ${index + 1} di ${images.length}`}
          referrerPolicy="no-referrer"
          style={{ transform: `scale(${zoom})`, transition: "transform 0.15s ease-out" }}
          className="max-w-[95vw] max-h-[90vh] object-contain cursor-zoom-in select-none"
          onClick={(e) => {
            e.stopPropagation();
            setZoom((z) => (z >= 2 ? 1 : z + 0.5));
          }}
          draggable={false}
        />
      </div>

      {/* Nav buttons */}
      {images.length > 1 && (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              prev();
            }}
            className="absolute left-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Foto precedente"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              next();
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Foto successiva"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        </>
      )}
    </div>
  );
}
