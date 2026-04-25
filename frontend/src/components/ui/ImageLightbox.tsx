"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from "lucide-react";

interface ImageLightboxProps {
  images: string[];
  initialIndex?: number;
  open: boolean;
  onClose: () => void;
  title?: string;
}

export function ImageLightbox({ images, initialIndex = 0, open, onClose, title }: ImageLightboxProps) {
  const [index, setIndex] = useState(initialIndex);
  const [zoom, setZoom] = useState(1);

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

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
      else if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(z + 0.25, 3));
      else if (e.key === "-") setZoom((z) => Math.max(z - 0.25, 1));
    };
    window.addEventListener("keydown", onKey);
    // Lock scroll while open
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, next, prev, onClose]);

  if (!open || images.length === 0) return null;

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title || "Galleria immagini"}
    >
      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3 text-white bg-gradient-to-b from-black/60 to-transparent">
        <div className="text-sm font-medium truncate mr-4">
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
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors disabled:opacity-40"
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
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors disabled:opacity-40"
            aria-label="Aumenta zoom"
          >
            <ZoomIn className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-white/10 transition-colors"
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
          alt={`Foto ${index + 1}`}
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
            className="absolute left-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
            aria-label="Precedente"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              next();
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
            aria-label="Successivo"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        </>
      )}
    </div>
  );
}
