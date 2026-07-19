import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { requestCode } from "@/lib/api";
import { Mail, KeyRound, Loader2 } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"email" | "code">("email");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleRequestCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await requestCode(email);
      setStep("code");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, code);
      navigate("/chat");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="w-full max-w-sm mx-4">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-slate-900">Homework Helper</h1>
          <p className="text-sm text-slate-500 mt-1">Sign in to get started</p>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          {step === "email" ? (
            <form onSubmit={handleRequestCode} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    className="w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
                  />
                </div>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 px-4 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Send Code
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerify} className="space-y-4">
              <p className="text-sm text-slate-600">
                Code sent to <span className="font-medium">{email}</span>
              </p>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Verification Code</label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="123456"
                    required
                    className="w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
                  />
                </div>
              </div>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 px-4 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Sign In
              </button>
              <button
                type="button"
                onClick={() => { setStep("email"); setCode(""); setError(""); }}
                className="w-full py-2 text-sm text-slate-600 hover:text-slate-900"
              >
                Change email
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
