import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
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
import Landing from "@/pages/Landing";
import LandingParticuliers from "@/pages/LandingParticuliers";
import LandingMetre from "@/pages/LandingMetre";
import LandingPortugal from "@/pages/LandingPortugal";
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
import QuoteScanner from "@/pages/QuoteScanner";
import Admin from "@/pages/Admin";
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
import ProspectionLanding from "@/pages/ProspectionLanding";
import PcSignPage from "@/pages/PcSignPage";
import PcDashboard from "@/pages/PcDashboard";
import CotesControl from "@/pages/CotesControl";
import Account from "@/pages/Account";
import QuoteTracking from "@/pages/QuoteTracking";
import PublicEstimation from "@/pages/PublicEstimation";
import PlanTakeoff from "@/pages/PlanTakeoff";
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
import { CITY_LIST } from "@/lib/cities";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import { I18nProvider } from "@/context/I18nContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { MobileTabBar } from "@/components/pwa/MobileTabBar";
import CookieConsent from "@/components/CookieConsent";
import { DomTranslator } from "@/components/DomTranslator";

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

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/particuliers" element={<LandingParticuliers />} />
      <Route path="/metre" element={<LandingMetre />} />
      <Route path="/portugal" element={<Shell><LandingPortugal /></Shell>} />
      <Route path="/radar" element={<Shell><RadarChantiers /></Shell>} />
      <Route path="/investisseurs" element={<Investors />} />
      <Route path="/fonctionnalites" element={<Features />} />
      <Route path="/login" element={<Login />} />
      <Route path="/inscription" element={<Login />} />
      <Route path="/reinitialiser" element={<ResetPassword />} />
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimation" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculateurs" element={<Shell><Calculators /></Shell>} />
      <Route path="/prix" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/mon-catalogue" element={<ProRoute><Shell><PriceCatalog /></Shell></ProRoute>} />
      <Route path="/appro" element={<ProRoute><Shell><TechAnalysis /></Shell></ProRoute>} />
      <Route path="/rentabilite" element={<ProRoute><Shell><Profitability /></Shell></ProRoute>} />
      <Route path="/suivi-chantier" element={<ProRoute><Shell><SiteTracking /></Shell></ProRoute>} />
      <Route path="/rendu-ia" element={<ProRoute><Shell><RenderStudio /></Shell></ProRoute>} />
      <Route path="/mes-demandes" element={<ProRoute><Shell><MyLeads /></Shell></ProRoute>} />
      <Route path="/diy" element={<Shell><Diy /></Shell>} />
      <Route path="/coach" element={<Shell><Coach /></Shell>} />
      <Route path="/photo" element={<Shell><PhotoAnalyse /></Shell>} />
      <Route path="/tarifs" element={<Shell><Pricing /></Shell>} />
      <Route path="/comparatif" element={<Shell><Comparatif /></Shell>} />
      <Route path="/blog" element={<Shell><Blog /></Shell>} />
      <Route path="/blog/:slug" element={<Shell><BlogPost /></Shell>} />
      <Route path="/devis-travaux-:city" element={<Shell><LocalLanding /></Shell>} />
      {CITY_LIST.map((c) => (
        <Route key={c.slug} path={`/devis-travaux-${c.slug}`}
               element={<Shell><LocalLanding /></Shell>} />
      ))}
      <Route path="/parrainage" element={<Protected><Shell><Referrals /></Shell></Protected>} />
      <Route path="/parrainage" element={<Protected><Shell><Referral /></Shell></Protected>} />
      <Route path="/inviter" element={<Protected><Shell><Invite /></Shell></Protected>} />
      <Route path="/equipe" element={<ProRoute><Shell><Team /></Shell></ProRoute>} />
      <Route path="/devis" element={<ProRoute><Shell><QuoteTracking /></Shell></ProRoute>} />
      <Route path="/factures" element={<ProRoute><Shell><Invoices /></Shell></ProRoute>} />
      <Route path="/factures-electroniques" element={<ProRoute><Shell><EInvoicing /></Shell></ProRoute>} />
      <Route path="/situations" element={<ProRoute><Shell><Situations /></Shell></ProRoute>} />
      <Route path="/entreprise" element={<ProRoute><Shell><Entreprise /></Shell></ProRoute>} />
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
      <Route path="/prospection/:token" element={<ProspectionLanding />} />
      <Route path="/fiche/:shareId" element={<SharedCalc />} />
      <Route path="/avis/:token" element={<ReviewCollect />} />
      <Route path="/etude/:token" element={<PcSignPage />} />
      <Route path="/etudes-pc" element={<ProRoute><Shell><PcDashboard /></Shell></ProRoute>} />
      <Route path="/controle-cotes" element={<ProRoute><Shell><CotesControl /></Shell></ProRoute>} />
      <Route path="/compte" element={<Protected><Shell><Account /></Shell></Protected>} />
      <Route path="/pc" element={<ProRoute><Shell><PcDashboard /></Shell></ProRoute>} />
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
      <Route path="/mentions-legales" element={<Shell><MentionsLegales /></Shell>} />
      <Route path="/confidentialite" element={<Shell><Confidentialite /></Shell>} />
      <Route path="/cgv" element={<Shell><CGV /></Shell>} />
      <Route path="*" element={<Shell><NotFound /></Shell>} />
    </Routes>
  );
}

// Thème : mode jour par défaut ; le mode sombre n'est appliqué que s'il a été choisi explicitement.
if (localStorage.getItem("construpilot_theme") === "dark") {
  document.documentElement.classList.add("dark");
} else {
  document.documentElement.classList.remove("dark");
}

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
                      <AppRouter />
                      <MobileTabBar />
                      <InstallPrompt />
                      <CookieConsent />
                      <DomTranslator />
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
