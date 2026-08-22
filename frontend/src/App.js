import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { BillingProvider } from "@/context/BillingContext";
import { PermissionProvider } from "@/context/PermissionContext";
import { WhiteLabelProvider } from "@/context/WhiteLabelContext";
import AuthCallback from "@/components/AuthCallback";
import { Nav, Footer } from "@/components/Nav";
import Landing from "@/pages/Landing";
import LandingParticuliers from "@/pages/LandingParticuliers";
import Investors from "@/pages/Investors";
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
import TechAnalysis from "@/pages/TechAnalysis";
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
import HR from "@/pages/HR";
import WorkerApp from "@/pages/WorkerApp";
import SharedCalc from "@/pages/SharedCalc";
import PriceCatalog from "@/pages/PriceCatalog";
import SiteTracking from "@/pages/SiteTracking";
import Comparatif from "@/pages/Comparatif";
import Situations from "@/pages/Situations";
import Entreprise from "@/pages/Entreprise";
import { CITY_LIST } from "@/lib/cities";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import { I18nProvider } from "@/context/I18nContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { InstallPrompt } from "@/components/pwa/InstallPrompt";
import { MobileTabBar } from "@/components/pwa/MobileTabBar";

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

const Shell = ({ children }) => (
  <>
    <Nav />
    <main className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 pb-28 md:pb-10">{children}</main>
    <Footer />
  </>
);

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/particuliers" element={<LandingParticuliers />} />
      <Route path="/investisseurs" element={<Investors />} />
      <Route path="/login" element={<Login />} />
      <Route path="/inscription" element={<Login />} />
      <Route path="/reinitialiser" element={<ResetPassword />} />
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimation" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculateurs" element={<Shell><Calculators /></Shell>} />
      <Route path="/prix" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/mon-catalogue" element={<Protected><Shell><PriceCatalog /></Shell></Protected>} />
      <Route path="/appro" element={<Protected><Shell><TechAnalysis /></Shell></Protected>} />
      <Route path="/suivi-chantier" element={<Protected><Shell><SiteTracking /></Shell></Protected>} />
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
      <Route path="/equipe" element={<Protected><Shell><Team /></Shell></Protected>} />
      <Route path="/devis" element={<Protected><Shell><QuoteTracking /></Shell></Protected>} />
      <Route path="/factures" element={<Protected><Shell><Invoices /></Shell></Protected>} />
      <Route path="/situations" element={<Protected><Shell><Situations /></Shell></Protected>} />
      <Route path="/entreprise" element={<Protected><Shell><Entreprise /></Shell></Protected>} />
      <Route path="/rh" element={<Protected><Shell><HR /></Shell></Protected>} />
      <Route path="/pointage" element={<Protected><WorkerApp /></Protected>} />
      <Route path="/mes-avis" element={<Protected><Shell><MyReviews /></Shell></Protected>} />
      <Route path="/clients" element={<Protected><Shell><Clients /></Shell></Protected>} />
      <Route path="/clients/:clientId" element={<Protected><Shell><ClientDetail /></Shell></Protected>} />
      <Route path="/bibliotheque" element={<Protected><Shell><Library /></Shell></Protected>} />
      <Route path="/devis-editeur" element={<Protected><Shell><QuoteEditor /></Shell></Protected>} />
      <Route path="/devis-editeur/:docId" element={<Protected><Shell><QuoteEditor /></Shell></Protected>} />
      <Route path="/scanner-devis" element={<Shell><QuoteScanner /></Shell>} />
      <Route path="/e/:token" element={<PublicEstimation />} />
      <Route path="/sign/:token" element={<SignQuote />} />
      <Route path="/fiche/:shareId" element={<SharedCalc />} />
      <Route path="/avis/:token" element={<ReviewCollect />} />
      <Route path="/etude/:token" element={<PcSignPage />} />
      <Route path="/etudes-pc" element={<Protected><Shell><PcDashboard /></Shell></Protected>} />
      <Route path="/compte" element={<Protected><Shell><Account /></Shell></Protected>} />
      <Route path="/pc" element={<Protected><Shell><PcDashboard /></Shell></Protected>} />
      <Route path="/plan" element={<Protected><Shell><PlanTakeoff /></Shell></Protected>} />
      <Route path="/plan/compare" element={<Protected><Shell><PlanCompare /></Shell></Protected>} />
      <Route path="/marketplace" element={<Shell><Marketplace /></Shell>} />
      <Route path="/pro" element={<Protected><Shell><ProPortal /></Shell></Protected>} />
      <Route path="/pro/paiement/succes" element={<Protected><Shell><PaymentSuccess /></Shell></Protected>} />
      <Route path="/developpeurs" element={<Protected><Shell><ApiKeys /></Shell></Protected>} />
      <Route path="/docs" element={<Shell><Docs /></Shell>} />
      <Route path="/enterprise" element={<Shell><Enterprise /></Shell>} />
      <Route path="/fournisseur" element={<Protected><Shell><SupplierPortal /></Shell></Protected>} />
      <Route path="/paiement/succes" element={<Shell><PaymentSuccess /></Shell>} />
      <Route path="/paiement/annule" element={<Shell><PaymentCancel /></Shell>} />
      <Route path="/dashboard" element={<Protected><Shell><Dashboard /></Shell></Protected>} />
      <Route path="/projet/:id" element={<Protected><Shell><ProjectDetail /></Shell></Protected>} />
      <Route path="/admin" element={<Protected admin><Shell><Admin /></Shell></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
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
                    <AppRouter />
                    <MobileTabBar />
                    <InstallPrompt />
                    <Toaster position="top-right" richColors />
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
