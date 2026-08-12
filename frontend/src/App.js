import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
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
      <Route path="/smart-project" element={<Shell><SmartProject /></Shell>} />
      <Route path="/estimation" element={<Shell><Estimator /></Shell>} />
      <Route path="/calculateurs" element={<Shell><Calculators /></Shell>} />
      <Route path="/prix" element={<Shell><PriceSearch /></Shell>} />
      <Route path="/diy" element={<Shell><Diy /></Shell>} />
      <Route path="/coach" element={<Shell><Coach /></Shell>} />
      <Route path="/photo" element={<Shell><PhotoAnalyse /></Shell>} />
      <Route path="/devis" element={<Shell><QuoteScanner /></Shell>} />
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
          <AppRouter />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
