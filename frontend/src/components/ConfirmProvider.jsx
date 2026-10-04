import { createContext, useContext, useRef, useState, useCallback } from "react";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogFooter,
  AlertDialogTitle, AlertDialogDescription, AlertDialogAction, AlertDialogCancel,
} from "@/components/ui/alert-dialog";

const ConfirmContext = createContext(() => Promise.resolve(false));

export const useConfirm = () => useContext(ConfirmContext);

const DEFAULTS = {
  title: "Confirmar a ação",
  description: "Cette action est irréversible.",
  confirmLabel: "Confirmar",
  cancelLabel: "Cancelar",
  destructive: true,
};

export function ConfirmProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [opts, setOpts] = useState(DEFAULTS);
  const resolver = useRef(null);

  const confirm = useCallback((options = {}) => {
    setOpts({ ...DEFAULTS, ...options });
    setOpen(true);
    return new Promise((resolve) => { resolver.current = resolve; });
  }, []);

  const done = (val) => {
    setOpen(false);
    if (resolver.current) { resolver.current(val); resolver.current = null; }
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <AlertDialog open={open} onOpenChange={(o) => { if (!o) done(false); }}>
        <AlertDialogContent data-testid="confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle data-testid="confirm-dialog-title">{opts.title}</AlertDialogTitle>
            <AlertDialogDescription data-testid="confirm-dialog-desc">{opts.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => done(false)} data-testid="confirm-dialog-cancel">
              {opts.cancelLabel}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => done(true)}
              data-testid="confirm-dialog-confirm"
              className={opts.destructive ? "bg-red-600 hover:bg-red-700 focus:ring-red-600" : ""}>
              {opts.confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ConfirmContext.Provider>
  );
}

export default ConfirmProvider;
