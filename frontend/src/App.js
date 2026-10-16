import { WorkspaceFooter } from "@/components/workspace/WorkspaceFooter";
import { useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { DefaultSEO } from "@/seo/DefaultSEO";
import "@/App.css";
import "@/styles/workspace.css";
import WorkspaceNavigation from "@/components/workspace/WorkspaceNavigation";
import { PermissionNotice } from "@/components/workspace/PermissionNotice";
import { usePermissions } from "@/context/PermissionContext";
import { routePermission, meetsLevel } from "@/components/workspace/navigation";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { BillingProvider, useBilling } from "@/context/BillingContext";
import { PermissionProvider } from "@/context/PermissionContext";
import { WhiteLabelProvider } from "@/context/WhiteLabelContext";
import { ConfirmProvider } from "@/components/ConfirmProvider";
import { OfflineProvider } from "@/context/OfflineContext";
import AuthCallback from "@/components/AuthCallback";
import { Nav, Footer } from "@/components/Nav";
import HelpChatbot from "@/components/HelpChatbot";
import { StudyRunning } from "@/components/StudyRunning";
import { AgentsRunning } from "@/components/AgentsRunning";
import LandingPro from "@/pages/LandingPro";
import LandingParticuliers from "@/pages/LandingParticuliers";
import LandingMetre from "@/pages/LandingMetre";
import LandingPortugal from "@/pages/LandingPortugal";
import { RouteSkeleton } from "@/components/Skeleton";
import { initTheme } from "@/components/ThemeToggle";
import AutorizacaoObras from "@/pages/AutorizacaoObras";
import SubscrevePublic from "@/pages/SubscrevePublic";
import RadarChantiers from "@/pages/RadarChantiers";
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
import PhotoAnalyse from "@/pages/PhotoAnalyse";
import AgentsHub from "@/pages/AgentsHub";
import QuoteScanner from "@/pages/QuoteScanner";
import Admin from "@/pages/Admin";
import PedidosHub from "@/pages/admin/PedidosHub";
import {
  PedidosContactos, PedidosOrcamentos, PedidosIA,
  PedidosAutorizacoes, PedidosDownloads, PedidosCalculos,
} from "@/pages/admin/PedidosByKind";
import SavingsCalculator from "@/pages/SavingsCalculator";
import { ExpenseAdminPanel } from "@/components/admin/ExpenseAdminPanel";
import NotFound from "@/pages/NotFound";
import { MentionsLegales, Confidentialite, CGV } from "@/pages/LegalPages";
import AppPrivacy from "@/pages/AppPrivacy";
import DeleteAccountPage from "@/pages/DeleteAccountPage";
import RfqPublic from "@/pages/RfqPublic";
import DpgfPage from "@/pages/DpgfPage";
import DocIntelPage from "@/pages/DocIntelPage";
import Welcome from "@/pages/Welcome";
import Pricing from "@/pages/Pricing";
import ProOffer from "@/pages/ProOffer";
import Help from "@/pages/Help";
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
import ProspectionLanding from "@/pages/ProspectionLanding";
import PcSignPage from "@/pages/PcSignPage";
import PcDashboard from "@/pages/PcDashboard";
import CotesControl from "@/pages/CotesControl";
import Preferences from "@/pages/Preferences";
import SharedEstimate from "@/pages/SharedEstimate";
import Account from "@/pages/Account";
import QuoteTracking from "@/pages/QuoteTracking";
import PublicEstimation from "@/pages/PublicEstimation";
import Renovation from "@/pages/Renovation";
import Structuro from "@/pages/Structuro";
import StructureCalc from "@/pages/StructureCalc";
import BetDossier from "@/pages/BetDossier";
import PlanReader from "@/pages/PlanReader";
import StairCalculator from "@/pages/StairCalculator";
import Demo from "@/pages/Demo";
// Rotas pesadas via lazy loading para code-splitting
const AssistantLazy = lazy(() => import("@/pages/Assistant"));
const PlanTakeoffLazy = lazy(() => import("@/pages/PlanTakeoff"));
const StructuroHouseLazy = lazy(() => import("@/pages/StructuroHouse"));
import AppsHub from "@/pages/AppsHub";
import MedicaoRapida from "@/pages/MedicaoRapida";
import BottomTabBar from "@/components/mobile/BottomTabBar";
import MicFab from "@/components/mobile/MicFab";
import BtpSolver from "@/pages/BtpSolver";
import PlansPro from "@/pages/PlansPro";
import CompanyPage from "@/pages/CompanyPage";
import CompanyPublic from "@/pages/CompanyPublic";
import { PortalLogin, PortalAccept, PortalChantier } from "@/pages/Portal";
import PhotoMeasure from "@/pages/PhotoMeasure";
import ProVerified from "@/pages/ProVerified";
import ProUpsell from "@/pages/ProUpsell";
import VerifyEmail from "@/pages/VerifyEmail";
import TechAnalysis from "@/pages/TechAnalysis";
import Profitability from "@/pages/Profitability";
import PlanCompare from "@/pages/PlanCompare";
import Blog from "@/pages/Blog";
import BlogPost from "@/pages/BlogPost";
import LocalLanding from "@/pages/LocalLanding";
import Referrals from "@/pages/Referrals";
import ReviewCollect from "@/pages/ReviewCollect";
import MyReviews from "@/pages/MyReviews";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import Chantiers from "@/pages/Chantiers";
import ChantierDetail from "@/pages/ChantierDetail";
import Library from "@/pages/Library";
import QuoteEditor from "@/pages/QuoteEditor";
import Invoices from "@/pages/Invoices";
import Trash from "@/pages/Trash";
import GrowthPage from "@/growth/GrowthPage";
import PlanAnalysis from "@/pages/PlanAnalysis";
import EInvoicing from "@/pages/EInvoicing";
import HR from "@/pages/HR";
import WorkerApp from "@/pages/WorkerApp";
import SharedCalc from "@/pages/SharedCalc";
import PriceCatalog from "@/pages/PriceCatalog";
import SiteTracking from "@/pages/SiteTracking";
import Planning from "@/pages/Planning";
import RenderStudio from "@/pages/RenderStudio";
import MyLeads from "@/pages/MyLeads";
import RenderShare from "@/pages/RenderShare";
import Comparatif from "@/pages/Comparatif";
import Situations from "@/pages/Situations";
import Entreprise from "@/pages/Entreprise";
import { CITY_LIST } from "@/lib/cities";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import PostalPaymentReturn from "@/pages/PostalPaymentReturn";
import { useAppConfig } from "@/hooks/useAppConfig";
import { I18nProvider } from "@/context/I18nContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { MobileTabBar } from "@/components/pwa/MobileTabBar";
import CookieConsent from "@/components/CookieConsent";
import { DomTranslator } from "@/components/DomTranslator";

const PostalFeature = ({ children }) => {
  const { config, ready } = useAppConfig();
  if (!ready) return null;
  return config.postal_enabled ? children : <Navigate to="/dashboard" replace />;
};

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
  const { tier } = useBilling();
  const permissions = usePermissions();
  const location = useLocation();
  if (loading)
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  const isPro = meetsLevel(user, tier, "pro");
  if (!isPro) return <Navigate to="/passez-pro" replace />;
  if (user.role === "worker" && location.pathname !== "/pointage") return <Navigate to="/pointage" replace />;
  const feature = routePermission(location.pathname, location.search);
  if (permissions.loading || permissions.error || !permissions.active || (feature && !permissions.can(feature))) {
    return <Shell><PermissionNotice denied /></Shell>;
  }
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
  const subscribed = meetsLevel(user, tier, "particulier_payant");
  if (!subscribed) return <Navigate to="/passez-pro?feature=analyse" replace />;
  return children;
};

// Accès réservé aux offres « Business » (équipes) — et admin.
const BusinessRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const { tier } = useBilling();
  if (loading)
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (!meetsLevel(user, tier, "business")) return <Navigate to="/passez-pro?feature=business" replace />;
  return children;
};

const Shell = ({ children }) => {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const assistant = pathname === "/assistant";
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  if (!user) return <><Nav /><main className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 pb-28 md:pb-10">{children}</main><Footer /><HelpChatbot /></>;
  return <div className={`workspace${assistant ? " workspace-chat" : ""}`}>
    <WorkspaceNavigation />
    <div className="workspace-content">
      <main key={user.user_id} id="workspace-main" tabIndex={-1} className="workspace-main">{children}</main>
      {!assistant && <WorkspaceFooter />}
    </div>
    {!assistant && <HelpChatbot />}
    <AgentsRunning />
    <StudyRunning />
  </div>;
};

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <>
    <DefaultSEO />
    <Routes>
      <Route path="/" element={<LandingPro />} />
      <Route path="/demo" element={<Demo />} />
      <Route path="/apps" element={<Shell><AppsHub /></Shell>} />
      <Route path="/medicao-rapida" element={<Shell><MedicaoRapida /></Shell>} />
      <Route path="/particulares" element={<LandingParticuliers />} />
      <Route path="/particuliers" element={<Navigate to="/particulares" replace />} />
      <Route path="/medicoes" element={<LandingMetre />} />
      <Route path="/metre" element={<Navigate to="/medicoes" replace />} />
      <Route path="/economies" element={<Shell><SavingsCalculator /></Shell>} />
      <Route path="/portugal" element={<Shell><LandingPortugal /></Shell>} />
      <Route path="/particulares/autorizacao-obras" element={<Shell><AutorizacaoObras /></Shell>} />
      <Route path="/subscrever/:token" element={<SubscrevePublic />} />
      <Route path="/radar" element={<Shell><RadarChantiers /></Shell>} />
      <Route path="/radar/courrier/retour" element={<Protected><Shell><PostalFeature><PostalPaymentReturn /></PostalFeature></Shell></Protected>} />
      <Route path="/investisseurs" element={<Investors />} />
      <Route path="/fonctionnalites" element={<Features />} />
      <Route path="/login" element={<Login />} />
      <Route path="/inscription" element={<Login />} />
      <Route path="/reinitialiser" element={<ResetPassword />} />
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimation" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculadoras" element={<Shell><Calculators /></Shell>} />
      <Route path="/calculateurs" element={<Navigate to="/calculadoras" replace />} />
      <Route path="/precos" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/prix" element={<Navigate to="/precos" replace />} />
      <Route path="/mon-catalogue" element={<ProRoute><Shell><PriceCatalog /></Shell></ProRoute>} />
      <Route path="/appro" element={<ProRoute><Shell><TechAnalysis /></Shell></ProRoute>} />
      <Route path="/rentabilite" element={<ProRoute><Shell><Profitability /></Shell></ProRoute>} />
      <Route path="/suivi-chantier" element={<ProRoute><Shell><SiteTracking /></Shell></ProRoute>} />
      <Route path="/planning" element={<ProRoute><Shell><Planning /></Shell></ProRoute>} />
      <Route path="/agents" element={<Protected><Shell><AgentsHub /></Shell></Protected>} />
      <Route path="/rendu-ia" element={<SubscriberRoute><Shell><RenderStudio /></Shell></SubscriberRoute>} />
      <Route path="/mes-demandes" element={<ProRoute><Shell><MyLeads /></Shell></ProRoute>} />
      <Route path="/diy" element={<Shell><Diy /></Shell>} />
      <Route path="/coach" element={<Shell><Coach /></Shell>} />
      <Route path="/photo" element={<Shell><PhotoAnalyse /></Shell>} />
      <Route path="/planos" element={<Shell><Pricing /></Shell>} />
      <Route path="/tarifs" element={<Navigate to="/planos" replace />} />
      <Route path="/pro" element={<Shell><ProOffer /></Shell>} />
      <Route path="/aide" element={<Shell><Help /></Shell>} />
      <Route path="/comparatif" element={<Shell><Comparatif /></Shell>} />
      <Route path="/blog" element={<Shell><Blog /></Shell>} />
      {/* Artigos FR legacy — redirect 301 para /blog (noindex via BlogPost quando o slug não existe) */}
      {[
        "cout-extension-maison-2026", "estimer-chantier-5-min", "cout-renovation-2026",
        "devis-tva-10-mode-emploi", "guide-metre-2d", "abattre-mur-porteur-reglementation",
        "permis-construire-2026", "re2020-renovation-guide", "chauffage-re2020-quel-choix",
        "prime-cee-2026-guide", "dpe-obligatoire-2026",
      ].map((slug) => (
        <Route key={`fr-${slug}`} path={`/blog/${slug}`} element={<Navigate to="/blog" replace />} />
      ))}
      <Route path="/blog/:slug" element={<Shell><BlogPost /></Shell>} />
      {CITY_LIST.map((c) => (
        <Route key={`pt-${c.slug}`} path={`/orcamento-obras-${c.slug}`}
               element={<Shell><LocalLanding /></Shell>} />
      ))}
      {/* Páginas de cidades FR legacy — redirect 301 para a landing principal */}
      {[
        "paris", "lyon", "marseille", "toulouse", "bordeaux",
        "nantes", "nice", "strasbourg", "rennes", "montpellier",
      ].map((city) => (
        <Route key={`fr-city-${city}`} path={`/devis-travaux-${city}`}
               element={<Navigate to="/" replace />} />
      ))}
      {CITY_LIST.map((c) => (
        <Route key={c.slug} path={`/devis-travaux-${c.slug}`}
               element={<Navigate to={`/orcamento-obras-${c.slug}`} replace />} />
      ))}
      <Route path="/devis-travaux-:city" element={<Navigate to="/" replace />} />
      <Route path="/parrainage" element={<Protected><Shell><Referrals /></Shell></Protected>} />
      <Route path="/parrainage" element={<Protected><Shell><Referral /></Shell></Protected>} />
      <Route path="/inviter" element={<Protected><Shell><Invite /></Shell></Protected>} />
      <Route path="/equipe" element={<BusinessRoute><Shell><Team /></Shell></BusinessRoute>} />
      <Route path="/devis" element={<ProRoute><Shell><QuoteTracking /></Shell></ProRoute>} />
      <Route path="/factures" element={<ProRoute><Shell><Invoices /></Shell></ProRoute>} />
      <Route path="/corbeille" element={<ProRoute><Shell><Trash /></Shell></ProRoute>} />
      <Route path="/factures-electroniques" element={<ProRoute><Shell><EInvoicing /></Shell></ProRoute>} />
      <Route path="/situations" element={<BusinessRoute><Shell><Situations /></Shell></BusinessRoute>} />
      <Route path="/entreprise" element={<BusinessRoute><Shell><Entreprise /></Shell></BusinessRoute>} />
      <Route path="/rh" element={<BusinessRoute><Shell><HR /></Shell></BusinessRoute>} />
      <Route path="/pointage" element={<ProRoute><WorkerApp /></ProRoute>} />
      <Route path="/mes-avis" element={<ProRoute><Shell><MyReviews /></Shell></ProRoute>} />
      <Route path="/clients" element={<ProRoute><Shell><Clients /></Shell></ProRoute>} />
      <Route path="/clients/:clientId" element={<ProRoute><Shell><ClientDetail /></Shell></ProRoute>} />
      <Route path="/chantiers" element={<ProRoute><Shell><Chantiers /></Shell></ProRoute>} />
      <Route path="/chantiers/:chantierId" element={<ProRoute><Shell><ChantierDetail /></Shell></ProRoute>} />
      <Route path="/bibliotheque" element={<ProRoute><Shell><Library /></Shell></ProRoute>} />
      <Route path="/devis-editeur" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/devis-editeur/:docId" element={<ProRoute><Shell><QuoteEditor /></Shell></ProRoute>} />
      <Route path="/scanner-devis" element={<SubscriberRoute><Shell><QuoteScanner /></Shell></SubscriberRoute>} />
      <Route path="/e/:token" element={<PublicEstimation />} />
      <Route path="/entreprise/:slug" element={<CompanyPublic />} />
      <Route path="/espace" element={<PortalLogin />} />
      <Route path="/espace/invitation/:token" element={<PortalAccept />} />
      <Route path="/espace/:ref" element={<PortalChantier />} />
      <Route path="/ma-page" element={<ProRoute><Shell><CompanyPage /></Shell></ProRoute>} />
      <Route path="/estimation-partagee/:token" element={<SharedEstimate />} />
      <Route path="/rendu/:token" element={<RenderShare />} />
      <Route path="/sign/:token" element={<SignQuote />} />
      <Route path="/prospection/:token" element={<ProspectionLanding />} />
      <Route path="/fiche/:shareId" element={<SharedCalc />} />
      <Route path="/avis/:token" element={<ReviewCollect />} />
      <Route path="/etude/:token" element={<PcSignPage />} />
      <Route path="/etudes-pc" element={<ProRoute><Shell><PcDashboard /></Shell></ProRoute>} />
      <Route path="/controle-cotes" element={<ProRoute><Shell><CotesControl /></Shell></ProRoute>} />
      <Route path="/assistant" element={<SubscriberRoute><Shell><Suspense fallback={<RouteSkeleton />}><AssistantLazy /></Suspense></Shell></SubscriberRoute>} />
      <Route path="/preferences" element={<Protected><Shell><Preferences /></Shell></Protected>} />
      <Route path="/compte" element={<Protected><Shell><Account /></Shell></Protected>} />
      <Route path="/dpgf" element={<ProRoute><Shell><DpgfPage /></Shell></ProRoute>} />
      <Route path="/analyse-documents" element={<ProRoute><Shell><DocIntelPage /></Shell></ProRoute>} />
      <Route path="/pc" element={<ProRoute><Shell><PcDashboard /></Shell></ProRoute>} />
      <Route path="/plan" element={<ProRoute><Shell><Suspense fallback={<RouteSkeleton />}><PlanTakeoffLazy /></Suspense></Shell></ProRoute>} />
      <Route path="/renovation" element={<ProRoute><Shell><Renovation /></Shell></ProRoute>} />
      <Route path="/structuro" element={<ProRoute><Shell><Structuro /></Shell></ProRoute>} />
      <Route path="/structuro/calcul" element={<ProRoute><Shell><StructureCalc /></Shell></ProRoute>} />
      <Route path="/structuro-bet" element={<ProRoute><Shell><BetDossier /></Shell></ProRoute>} />
      <Route path="/estudo-moradia" element={<ProRoute><Shell><Suspense fallback={<RouteSkeleton />}><StructuroHouseLazy /></Suspense></Shell></ProRoute>} />
      <Route path="/structuro/lecture-plan" element={<ProRoute><Shell><PlanReader /></Shell></ProRoute>} />
      <Route path="/escaliers" element={<ProRoute><Shell><StairCalculator /></Shell></ProRoute>} />
      <Route path="/btp-solver" element={<Protected><Shell><BtpSolver /></Shell></Protected>} />
      <Route path="/plans-pro" element={<ProRoute><Shell><PlansPro /></Shell></ProRoute>} />
      <Route path="/mesure-photo" element={<SubscriberRoute><Shell><PhotoMeasure /></Shell></SubscriberRoute>} />
      <Route path="/pro-verifie/:userId" element={<Shell><ProVerified /></Shell>} />
      <Route path="/passez-pro" element={<Protected><Shell><ProUpsell /></Shell></Protected>} />
      <Route path="/verifier-email/:token" element={<Shell><VerifyEmail /></Shell>} />
      <Route path="/plan/compare" element={<ProRoute><Shell><PlanCompare /></Shell></ProRoute>} />
      <Route path="/marketplace" element={<Shell><Marketplace /></Shell>} />
      <Route path="/pro" element={<Protected><Shell><ProPortal /></Shell></Protected>} />
      <Route path="/pro/paiement/succes" element={<Protected><Shell><PaymentSuccess /></Shell></Protected>} />
      <Route path="/developpeurs" element={<BusinessRoute><Shell><ApiKeys /></Shell></BusinessRoute>} />
      <Route path="/docs" element={<Shell><Docs /></Shell>} />
      <Route path="/enterprise" element={<Shell><Enterprise /></Shell>} />
      <Route path="/fournisseur" element={<ProRoute><Shell><SupplierPortal /></Shell></ProRoute>} />
      <Route path="/paiement/succes" element={<Shell><PaymentSuccess /></Shell>} />
      <Route path="/paiement/annule" element={<Shell><PaymentCancel /></Shell>} />
      <Route path="/dashboard" element={<Protected><Shell><Dashboard /></Shell></Protected>} />
      <Route path="/bienvenue" element={<Protected><Shell><Welcome /></Shell></Protected>} />
      <Route path="/projet/:id" element={<Protected><Shell><ProjectDetail /></Shell></Protected>} />
      <Route path="/admin" element={<Protected admin><Shell><Admin /></Shell></Protected>} />
      <Route path="/admin/pedidos" element={<Protected admin><Shell><PedidosHub /></Shell></Protected>} />
      <Route path="/admin/contactos" element={<Protected admin><Shell><PedidosContactos /></Shell></Protected>} />
      <Route path="/admin/orcamentos" element={<Protected admin><Shell><PedidosOrcamentos /></Shell></Protected>} />
      <Route path="/admin/ia" element={<Protected admin><Shell><PedidosIA /></Shell></Protected>} />
      <Route path="/admin/autorizacoes" element={<Protected admin><Shell><PedidosAutorizacoes /></Shell></Protected>} />
      <Route path="/admin/downloads" element={<Protected admin><Shell><PedidosDownloads /></Shell></Protected>} />
      <Route path="/admin/calculos" element={<Protected admin><Shell><PedidosCalculos /></Shell></Protected>} />
      <Route path="/admin/despesas" element={<Protected admin><Shell><ExpenseAdminPanel standalone /></Shell></Protected>} />
      <Route path="/admin/growth" element={<Protected><Shell><GrowthPage /></Shell></Protected>} />
      <Route path="/analyse/:planId" element={<ProRoute><Shell><PlanAnalysis /></Shell></ProRoute>} />
      <Route path="/mentions-legales" element={<Shell><MentionsLegales /></Shell>} />
      <Route path="/confidentialite" element={<Shell><Confidentialite /></Shell>} />
      <Route path="/privacy" element={<Shell><AppPrivacy /></Shell>} />
      <Route path="/app-privacy" element={<Shell><AppPrivacy /></Shell>} />
      <Route path="/confidentialite-apps" element={<Shell><AppPrivacy /></Shell>} />
      <Route path="/eliminar-conta" element={<Shell><DeleteAccountPage /></Shell>} />
      <Route path="/suppression-compte" element={<Navigate to="/eliminar-conta" replace />} />
      <Route path="/delete-account" element={<Shell><DeleteAccountPage /></Shell>} />
      <Route path="/account-deletion" element={<Shell><DeleteAccountPage /></Shell>} />
      <Route path="/eliminar-dados" element={<Shell><DeleteAccountPage /></Shell>} />
      <Route path="/suppression-donnees" element={<Navigate to="/eliminar-dados" replace />} />
      <Route path="/data-deletion" element={<Shell><DeleteAccountPage /></Shell>} />
      <Route path="/appel-offres/:token" element={<RfqPublic />} />
      <Route path="/cgv" element={<Shell><CGV /></Shell>} />
      <Route path="*" element={<Shell><NotFound /></Shell>} />
    </Routes>
    </>
  );
}

// Tema inicial: Automático (segue prefers-color-scheme) por defeito.
try { initTheme(); } catch { /* ignorar em SSR */ }

function App() {
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
                      <OfflineProvider>
                        <AppRouter />
                        <MobileTabBar />
                        <BottomTabBar />
                        <MicFab />
                        <InstallPrompt />
                        <CookieConsent />
                        <DomTranslator />
                        <Toaster position="top-right" richColors />
                      </OfflineProvider>
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

