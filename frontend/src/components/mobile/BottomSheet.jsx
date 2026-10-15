import { useEffect } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";

/**
 * BottomSheet reutilizável — modal em desktop (centro), bottom sheet em mobile.
 * Headless: o conteúdo é passado via `children`. O cabeçalho opcional via `title`.
 *
 * Props:
 *  - open: boolean
 *  - onClose: () => void
 *  - title?: string
 *  - children: ReactNode
 *  - size?: "sm" | "md" | "lg" (desktop width)
 *  - testId?: string
 */
export default function BottomSheet({
  open,
  onClose,
  title,
  children,
  size = "md",
  testId = "bottom-sheet",
}) {
  // Bloqueia scroll do body quando aberto (mobile — comportamento de bottom sheet)
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const widthClass =
    size === "sm" ? "md:max-w-md" : size === "lg" ? "md:max-w-2xl" : "md:max-w-lg";

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[80] bg-black/50 flex items-end md:items-center justify-center md:p-6"
          onClick={onClose}
          data-testid={`${testId}-backdrop`}
        >
          <motion.div
            key="sheet"
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.4 }}
            onDragEnd={(_, info) => {
              if (info.offset.y > 120 || info.velocity.y > 500) onClose?.();
            }}
            initial={{ y: "100%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "100%", opacity: 0 }}
            transition={{ type: "spring", damping: 32, stiffness: 320 }}
            onClick={(e) => e.stopPropagation()}
            className={`w-full ${widthClass} md:w-full bg-card text-foreground rounded-t-2xl md:rounded-2xl shadow-2xl max-h-[90vh] md:max-h-[85vh] overflow-hidden flex flex-col pb-safe`}
            role="dialog"
            aria-modal="true"
            aria-label={title || "Painel"}
            data-testid={testId}
          >
            <div className="flex md:hidden justify-center pt-2 pb-1" data-testid={`${testId}-handle`}>
              <div className="h-1 w-10 rounded-full bg-muted-foreground/30" />
            </div>
            {title && (
              <div className="px-5 py-3 border-b border-border">
                <h2 className="text-base font-semibold">{title}</h2>
              </div>
            )}
            <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
