import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { BillingProvider } from "@/context/BillingContext";
import { WhiteLabelProvider } from "@/context/WhiteLabelContext";
import AuthCallback from "@/components/AuthCallback";
import { Nav, Footer } from "@/components/Nav";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
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
import PublicEstimation from "@/pages/PublicEstimation";
import PlanTakeoff from "@/pages/PlanTakeoff";
import PlanCompare from "@/pages/PlanCompare";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";

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
    <main className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10">{children}</main>
    <Footer />
  </>
);

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/inscription" element={<Login />} />
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimation" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculateurs" element={<Shell><Calculators /></Shell>} />
      <Route path="/prix" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/diy" element={<Shell><Diy /></Shell>} />
      <Route path="/coach" element={<Shell><Coach /></Shell>} />
      <Route path="/photo" element={<Shell><PhotoAnalyse /></Shell>} />
      <Route path="/devis" element={<Shell><QuoteScanner /></Shell>} />
      <Route path="/tarifs" element={<Shell><Pricing /></Shell>} />
      <Route path="/parrainage" element={<Protected><Shell><Referral /></Shell></Protected>} />
      <Route path="/inviter" element={<Protected><Shell><Invite /></Shell></Protected>} />
      <Route path="/equipe" element={<Protected><Shell><Team /></Shell></Protected>} />
      <Route path="/e/:token" element={<PublicEstimation />} />
      <Route path="/sign/:token" element={<SignQuote />} />
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
      <BrowserRouter>
        <AuthProvider>
          <BillingProvider>
            <WhiteLabelProvider>
              <AppRouter />
              <Toaster position="top-right" richColors />
            </WhiteLabelProvider>
          </BillingProvider>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
