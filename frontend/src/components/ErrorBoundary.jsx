import React from "react";
import { AlertTriangle, RefreshCw, Home } from "lucide-react";

/**
 * Global error boundary — prevents white screens by catching any React render
 * error and displaying a branded fallback with a reload button.
 *
 * Wrapped at the App root so any uncaught render error in any page is caught.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log to console — in production, could ship to a monitoring endpoint.
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info);
    this.setState({ info });
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null, info: null });
    window.location.reload();
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null, info: null });
    window.location.href = "/";
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const msg = this.state.error?.message || "Une erreur inattendue est survenue.";

    return (
      <div
        className="min-h-screen grid place-items-center bg-background text-foreground px-5"
        data-testid="error-boundary-fallback"
      >
        <div className="max-w-md w-full surface p-8 grid gap-4 text-center">
          <div className="h-14 w-14 mx-auto grid place-items-center bg-destructive/15 rounded-full">
            <AlertTriangle className="h-7 w-7 text-destructive" />
          </div>
          <div>
            <p className="overline text-destructive">Oups</p>
            <h1 className="font-display text-2xl font-bold mt-2">
              Une erreur s'est produite
            </h1>
            <p className="text-sm text-muted-foreground mt-2">
              Nous avons rencontré un problème d'affichage. Essayez de recharger
              la page — vos données sont en sécurité.
            </p>
          </div>
          <p className="text-[11px] text-muted-foreground bg-secondary/30 p-2 rounded-sm font-mono break-words">
            {msg.slice(0, 220)}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={this.handleReload}
              data-testid="error-boundary-reload-btn"
              className="rounded-sm bg-primary text-white text-sm font-semibold h-10 flex items-center justify-center gap-2 hover:bg-orange-600 transition-colors"
            >
              <RefreshCw className="h-4 w-4" /> Recharger
            </button>
            <button
              onClick={this.handleGoHome}
              data-testid="error-boundary-home-btn"
              className="rounded-sm border border-border text-sm font-semibold h-10 flex items-center justify-center gap-2 hover:bg-secondary transition-colors"
            >
              <Home className="h-4 w-4" /> Accueil
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
