import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import React, { useEffect } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { BillingProvider, useBilling } from "@/context/BillingContext";
import { PermissionProvider } from "@/context/PermissionContext";
import { WhiteLabelProvider } from "@/context/WhiteLabelContext";
import { ConfirmProvider } from "@/components/ConfirmProvider";
import AuthCallback from "@/components/AuthCallback";
import { Nav, Footer } from "@/components/Nav";
import HelpChatbot from "@/components/HelpChatbot";
import LandingParticuliers from "@/pages/LandingParticuliers";
import LandingPortugal from "@/pages/LandingPortugal";
import Investors from "@/pages/Investors";
import Features from "@/pages/Features";
import Login from "@/pages/Login";
import ResetPassword from "@/pages/ResetPassword";
import Dashboard from "@/pages/Dashboard";
import Estimator from "@/pages/Estimator";
import SmartProject from "@/pages/SmartProject";
import ProjectDetail from "@/pages/ProjectDetail";
import Calculators from "@/pages/Calculators";
import PriceSearch from "@/pages/PriceSearch";
import Diy from "@/pages/Diy";
import Coach from "@/pages/Coach";
import BtpSolver from "@/pages/BtpSolver";
import PhotoAnalyse from "@/pages/PhotoAnalyse";
import QuoteScanner from "@/pages/QuoteScanner";
import Admin from "@/pages/Admin";
import AdminSecrets from "@/pages/AdminSecrets";
import NotFound from "@/pages/NotFound";
import { MentionsLegales, Confidentialite, CGV } from "@/pages/LegalPages";
import Welcome from "@/pages/Welcome";
import Pricing from "@/pages/Pricing";
import Referral from "@/pages/Referral";
import Marketplace from "@/pages/Marketplace";
import ProPortal from "@/pages/ProPortal";
import ApiKeys from "@/pages/ApiKeys";
import Docs from "@/pages/Docs";
import Enterprise from "@/pages/Enterprise";
import SupplierPortal from "@/pages/SupplierPortal";
import Invite from "@/pages/Invite";
import Team from "@/pages/Team";
import SignQuote from "@/pages/SignQuote";
import PcSignPage from "@/pages/PcSignPage";
import PcDashboard from "@/pages/PcDashboard";
import Account from "@/pages/Account";
import QuoteTracking from "@/pages/QuoteTracking";
import PublicEstimation from "@/pages/PublicEstimation";
import PlanTakeoff from "@/pages/PlanTakeoff";
import PhotoMeasure from "@/pages/PhotoMeasure";
import ProVerified from "@/pages/ProVerified";
import ProUpsell from "@/pages/ProUpsell";
import VerifyEmail from "@/pages/VerifyEmail";
import TechAnalysis from "@/pages/TechAnalysis";
import PlanCompare from "@/pages/PlanCompare";
import Blog from "@/pages/Blog";
import BlogPost from "@/pages/BlogPost";
// LocalLanding (rotas /devis-travaux-:city) removida — era SEO local FR.
import Referrals from "@/pages/Referrals";
import ReviewCollect from "@/pages/ReviewCollect";
import MyReviews from "@/pages/MyReviews";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import Library from "@/pages/Library";
import QuoteEditor from "@/pages/QuoteEditor";
import Invoices from "@/pages/Invoices";
import EInvoicing from "@/pages/EInvoicing";
import HR from "@/pages/HR";
import WorkerApp from "@/pages/WorkerApp";
import SharedCalc from "@/pages/SharedCalc";
import PriceCatalog from "@/pages/PriceCatalog";
import SiteTracking from "@/pages/SiteTracking";
import RenderStudio from "@/pages/RenderStudio";
import MyLeads from "@/pages/MyLeads";
import RenderShare from "@/pages/RenderShare";
import Comparatif from "@/pages/Comparatif";
import Situations from "@/pages/Situations";
import Entreprise from "@/pages/Entreprise";
// CITY_LIST removida com as rotas SEO locais FR (100% PT-PT).
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import { I18nProvider } from "@/context/I18nContext";
import { DomTranslator } from "@/components/DomTranslator";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { MobileTabBar } from "@/components/pwa/MobileTabBar";
import CookieConsent from "@/components/CookieConsent";

const Protected = ({ children, admin }) => {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (admin && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
};

const ProRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  const isPro = user.account_type !== "particulier" || user.role === "admin";
  if (!isPro) return <Navigate to="/passez-pro" replace />;
  return children;
};

// Accès réservé aux abonnés : pros/admins OU particuliers avec un forfait payant.
const SubscriberRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const { tier } = useBilling();
  if (loading)
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  const isPro = user.account_type !== "particulier" || user.role === "admin";
  const subscribed = tier && tier !== "free";
  if (!isPro && !subscribed) return <Navigate to="/passez-pro?feature=analyse" replace />;
  return children;
};

const Shell = ({ children }) => (
  <>
    <Nav />
    <main className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 pb-28 md:pb-10">{children}</main>
    <Footer />
    <HelpChatbot />
  </>
);

/** Redirect externo: envia o utilizador para uma URL fora da SPA
 *  (ex.: webmail PTISP em webmail.construpilot.pt). */
function ExternalRedirect({ to }) {
  useEffect(() => { window.location.replace(to); }, [to]);
  return (
    <div style={{ padding: "3rem", textAlign: "center", fontFamily: "system-ui" }}>
      <p style={{ fontSize: 16, color: "#334155" }}>A redirecionar para o webmail…</p>
      <p style={{ marginTop: 12 }}>
        <a href={to} style={{ color: "#FF5A00", textDecoration: "underline" }}>
          Se não fores redirecionado automaticamente, clica aqui
        </a>
      </p>
    </div>
  );
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<LandingPortugal />} />
      <Route path="/fr" element={<Navigate to="/" replace />} />
      <Route path="/particuliers" element={<LandingParticuliers />} />
      <Route path="/portugal" element={<Shell><LandingPortugal /></Shell>} />
      <Route path="/investidores" element={<Investors />} />
      <Route path="/funcionalidades" element={<Features />} />
      <Route path="/login" element={<Login />} />
      <Route path="/registo" element={<Login />} />
      <Route path="/redefinir" element={<ResetPassword />} />
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimativa" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculadoras" element={<Shell><Calculators /></Shell>} />
      <Route path="/precos" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/mon-catalogue" element={<ProRoute><Shell><PriceCatalog /></Shell></ProRoute>} />
      <Route path="/appro" element={<ProRoute><Shell><TechAnalysis /></Shell></ProRoute>} />
      <Route path="/suivi-chantier" element={<ProRoute><Shell><SiteTracking /></Shell></ProRoute>} />
      <Route path="/rendu-ia" element={<ProRoute><Shell><RenderStudio /></Shell></ProRoute>} />
      <Route path="/mes-demandes" element={<ProRoute><Shell><MyLeads /></Shell></ProRoute>} />
      <Route path="/diy" element={<Shell><Diy /></Shell>} />
      <Route path="/coach" element={<Shell><Coach /></Shell>} />
      <Route path="/btp-solver" element={<Shell><BtpSolver /></Shell>} />
      <Route path="/photo" element={<Shell><PhotoAnalyse /></Shell>} />
      <Route path="/tarifs" element={<Shell><Pricing /></Shell>} />
      <Route path="/comparatif" element={<Shell><Comparatif /></Shell>} />
      <Route path="/blog" element={<Shell><Blog /></Shell>} />
      <Route path="/blog/:slug" element={<Shell><BlogPost /></Shell>} />
      {/* Rotas SEO locais FR removidas (100% PT-PT) — mantidas como redirect para /. */}
      <Route path="/devis-travaux-:city" element={<Navigate to="/" replace />} />
      <Route path="/parrainage" element={<Protected><Shell><Referrals /></Shell></Protected>} />
      <Route path="/inviter" element={<Protected><Shell><Invite /></Shell></Protected>} />
      <Route path="/equipe" element={<ProRoute><Shell><Team /></Shell></ProRoute>} />
      <Route path="/devis" element={<Navigate to="/orcamentos" replace />} />
      <Route path="/factures" element={<Navigate to="/faturas" replace />} />
      <Route path="/factures-electroniques" element={<ProRoute><Shell><EInvoicing /></Shell></ProRoute>} />
      <Route path="/situations" element={<ProRoute><Shell><Situations /></Shell></ProRoute>} />
      <Route path="/entreprise" element={<Navigate to="/empresa" replace />} />
      <Route path="/rh" element={<ProRoute><Shell><HR /></Shell></ProRoute>} />
      <Route path="/pointage" element={<ProRoute><WorkerApp /></ProRoute>} />
      <Route path="/mes-avis" element={<ProRoute><Shell><MyReviews /></Shell></ProRoute>} />
      <Route path="/clients" element={<ProRoute><Shell><Clients /></Shell></ProRoute>} />
      <Route path="/clients/:clientId" element={<ProRoute><Shell><ClientDetail /></Shell></ProRoute>} />
      <Route path="/bibliotheque" element={<ProRoute><Shell><Library /></Shell></ProRoute>} />
      <Route path="/devis-editeur" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/devis-editeur/:docId" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/scanner-devis" element={<SubscriberRoute><Shell><QuoteScanner /></Shell></SubscriberRoute>} />
      <Route path="/e/:token" element={<PublicEstimation />} />
      <Route path="/rendu/:token" element={<RenderShare />} />
      <Route path="/sign/:token" element={<SignQuote />} />
      <Route path="/fiche/:shareId" element={<SharedCalc />} />
      <Route path="/avis/:token" element={<ReviewCollect />} />
      <Route path="/etude/:token" element={<PcSignPage />} />
      <Route path="/estudos-lc" element={<ProRoute><Shell><PcDashboard /></Shell></ProRoute>} />
      <Route path="/etudes-pc" element={<Navigate to="/estudos-lc" replace />} />
      <Route path="/compte" element={<Protected><Shell><Account /></Shell></Protected>} />
      <Route path="/pc" element={<Navigate to="/estudos-lc" replace />} />
      <Route path="/plan" element={<ProRoute><Shell><PlanTakeoff /></Shell></ProRoute>} />
      <Route path="/mesure-photo" element={<ProRoute><Shell><PhotoMeasure /></Shell></ProRoute>} />
      <Route path="/pro-verifie/:userId" element={<Shell><ProVerified /></Shell>} />
      <Route path="/passez-pro" element={<Protected><Shell><ProUpsell /></Shell></Protected>} />
      <Route path="/verifier-email/:token" element={<Shell><VerifyEmail /></Shell>} />
      <Route path="/plan/compare" element={<ProRoute><Shell><PlanCompare /></Shell></ProRoute>} />
      <Route path="/marketplace" element={<Shell><Marketplace /></Shell>} />
      <Route path="/pro" element={<Protected><Shell><ProPortal /></Shell></Protected>} />
      <Route path="/pro/paiement/succes" element={<Protected><Shell><PaymentSuccess /></Shell></Protected>} />
      <Route path="/developpeurs" element={<ProRoute><Shell><ApiKeys /></Shell></ProRoute>} />
      <Route path="/docs" element={<Shell><Docs /></Shell>} />
      <Route path="/enterprise" element={<Shell><Enterprise /></Shell>} />
      <Route path="/fournisseur" element={<ProRoute><Shell><SupplierPortal /></Shell></ProRoute>} />
      <Route path="/paiement/succes" element={<Shell><PaymentSuccess /></Shell>} />
      <Route path="/paiement/annule" element={<Shell><PaymentCancel /></Shell>} />
      <Route path="/dashboard" element={<Protected><Shell><Dashboard /></Shell></Protected>} />
      <Route path="/bienvenue" element={<Protected><Shell><Welcome /></Shell></Protected>} />
      <Route path="/projet/:id" element={<Protected><Shell><ProjectDetail /></Shell></Protected>} />
      <Route path="/admin" element={<Protected admin><Shell><Admin /></Shell></Protected>} />
      <Route path="/admin/secrets" element={<Protected admin><Shell><AdminSecrets /></Shell></Protected>} />
      <Route path="/mentions-legales" element={<Shell><MentionsLegales /></Shell>} />
      <Route path="/confidentialite" element={<Shell><Confidentialite /></Shell>} />
      <Route path="/cgv" element={<Shell><CGV /></Shell>} />
      {/* PTISP webmail — usando URL genérico .ptisp.com porque o subdomínio do cliente
          (webmail.construpilot.pt) usa cert SSL partilhado que dispara avisos de antivírus
          (ex.: Kaspersky). Utilizador pode pedir cert Let's Encrypt para
          webmail.construpilot.pt via painel PTISP. */}
      <Route path="/webmail" element={<ExternalRedirect to="https://mail.ptisp.com" />} />
      <Route path="/mail" element={<ExternalRedirect to="https://mail.ptisp.com" />} />
      <Route path="/roundcube" element={<ExternalRedirect to="https://mail.ptisp.com" />} />
      <Route path="/rainloop" element={<ExternalRedirect to="https://mail.ptisp.com" />} />
      {/* Aliases directos para a caixa de correio interna (config SMTP saída) → abrem o modal em /empresa */}
      <Route path="/caixa-correio" element={<Navigate to="/empresa?open=mailbox" replace />} />
      <Route path="/caixa-de-correio" element={<Navigate to="/empresa?open=mailbox" replace />} />
      <Route path="/mailbox" element={<Navigate to="/empresa?open=mailbox" replace />} />
      {/* Client-side 301-style redirects FR/EN -> PT canonical (SEO signal via _redirects file if host supports it) */}
      <Route path="/investisseurs" element={<Navigate to="/investidores" replace />} />
      <Route path="/investors" element={<Navigate to="/investidores" replace />} />
      <Route path="/calculateurs" element={<Navigate to="/calculadoras" replace />} />
      <Route path="/calculators" element={<Navigate to="/calculadoras" replace />} />
      <Route path="/prix" element={<Navigate to="/precos" replace />} />
      <Route path="/prices" element={<Navigate to="/precos" replace />} />
      <Route path="/estimation" element={<Navigate to="/estimativa" replace />} />
      <Route path="/inscription" element={<Navigate to="/registo" replace />} />
      <Route path="/reinitialiser" element={<Navigate to="/redefinir" replace />} />
      <Route path="/fonctionnalites" element={<Navigate to="/funcionalidades" replace />} />
      {/* PT-PT route aliases */}
      <Route path="/planta" element={<ProRoute><Shell><PlanTakeoff /></Shell></ProRoute>} />
      <Route path="/plans" element={<ProRoute><Shell><PlanTakeoff /></Shell></ProRoute>} />
      <Route path="/faturas" element={<ProRoute><Shell><Invoices /></Shell></ProRoute>} />
      <Route path="/invoices" element={<ProRoute><Shell><Invoices /></Shell></ProRoute>} />
      <Route path="/faturacao-eletronica" element={<ProRoute><Shell><EInvoicing /></Shell></ProRoute>} />
      <Route path="/e-invoicing" element={<ProRoute><Shell><EInvoicing /></Shell></ProRoute>} />
      <Route path="/situacoes" element={<ProRoute><Shell><Situations /></Shell></ProRoute>} />
      <Route path="/empresa" element={<ProRoute><Shell><Entreprise /></Shell></ProRoute>} />
      <Route path="/render-ia" element={<ProRoute><Shell><RenderStudio /></Shell></ProRoute>} />
      <Route path="/render-studio" element={<ProRoute><Shell><RenderStudio /></Shell></ProRoute>} />
      <Route path="/features" element={<Features />} />
      <Route path="/conta" element={<Protected><Shell><Account /></Shell></Protected>} />
      <Route path="/orcamentos" element={<ProRoute><Shell><QuoteTracking /></Shell></ProRoute>} />
      <Route path="/orcamento-editor" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/orcamento-editor/:docId" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/equipa" element={<ProRoute><Shell><Team /></Shell></ProRoute>} />
      <Route path="/biblioteca" element={<ProRoute><Shell><Library /></Shell></ProRoute>} />
      <Route path="/obra" element={<ProRoute><Shell><SiteTracking /></Shell></ProRoute>} />
      <Route path="*" element={<Shell><NotFound /></Shell>} />
    </Routes>
  );
}

function App() {
  useEffect(() => {
    const saved = localStorage.getItem("construpilot_theme");
    if (saved !== "light") document.documentElement.classList.add("dark");
  }, []);

  return (
    <div className="App">
      <ErrorBoundary>
        <BrowserRouter>
          <I18nProvider>
            <AuthProvider>
              <BillingProvider>
                <PermissionProvider>
                  <WhiteLabelProvider>
                    <ConfirmProvider>
                      <DomTranslator />
                      <AppRouter />
                      <MobileTabBar />
                      <InstallPrompt />
                      <CookieConsent />
                      <Toaster position="top-right" richColors />
                    </ConfirmProvider>
                  </WhiteLabelProvider>
                </PermissionProvider>
              </BillingProvider>
            </AuthProvider>
          </I18nProvider>
        </BrowserRouter>
      </ErrorBoundary>
    </div>
  );
}

export default App;
