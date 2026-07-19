import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import DebugPage from "./pages/DebugPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center h-screen text-gray-400">Loading...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/chat" element={<ProtectedRoute><ChatPage /></ProtectedRoute>} />
        <Route path="/debug" element={<ProtectedRoute><DebugPage /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/chat" replace />} />
      </Routes>
    </AuthProvider>
  );
}
