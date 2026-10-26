"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LoaderCircle, AlertCircle, MessageSquareText, Package, Headphones, ShieldCheck } from "lucide-react";
import { buildApiUrl } from "@/lib/api";
import { useAdminLocale } from "@/lib/admin-locale";
import type { AdminLocale } from "@/lib/admin-copy";

const loginCopy = {
  th: {
    title: "เข้าสู่ระบบ", subtitle: "เข้าสู่พื้นที่ทำงานบริการลูกค้าของคุณ",
    headline: "ทีม AI 24x7\nเพื่อบริการลูกค้าที่ดีกว่า", caption: "เชื่อมทีม AI ความรู้ และช่องทางสนทนาของลูกค้าไว้ด้วยกัน",
    username: "ชื่อผู้ใช้", password: "รหัสผ่าน", submit: "เข้าสู่ระบบ", loading: "กำลังเข้าสู่ระบบ",
    show: "แสดงรหัสผ่าน", hide: "ซ่อนรหัสผ่าน", help: "หากเข้าใช้งานไม่ได้ โปรดติดต่อผู้ดูแลระบบ",
    invalid: "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", failed: "เข้าสู่ระบบไม่สำเร็จ โปรดลองอีกครั้ง",
    products: "ข้อมูลสินค้า", warranty: "รับประกัน", voice: "เสียง", language: "ภาษา",
  },
  en: {
    title: "Welcome back", subtitle: "Sign in to your customer service workspace.",
    headline: "Your 24x7 AI team.\nFor better customer service.", caption: "Connect your AI team, company knowledge, and customer conversations.",
    username: "Username", password: "Password", submit: "Sign in", loading: "Signing in",
    show: "Show password", hide: "Hide password", help: "Need access? Contact your administrator.",
    invalid: "Incorrect username or password", failed: "Unable to sign in. Please try again.",
    products: "Product information", warranty: "Warranty", voice: "Voice", language: "Language",
  },
} satisfies Record<AdminLocale, Record<string, string>>;

export default function AdminLoginPage() {
  const router = useRouter();
  const { locale, setLocale } = useAdminLocale();
  const copy = loginCopy[locale];
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<"invalid" | "failed" | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setLoading(true);
    try {
      const response = await fetch(buildApiUrl("/api/admin/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!response.ok) {
        setError(response.status === 401 ? "invalid" : "failed");
        return;
      }
      const data = await response.json();
      localStorage.setItem("adminToken", data.access_token);
      localStorage.setItem("adminUsername", data.username);
      localStorage.setItem("isSuperAdmin", data.is_super_admin ? "1" : "0");
      localStorage.setItem("isOperatorOnly", data.is_operator_only ? "1" : "0");
      localStorage.setItem("isViewerOnly", data.is_viewer_only ? "1" : "0");
      localStorage.setItem("canManageUsers", data.can_manage_users ? "1" : "0");
      router.push("/admin");
    } catch {
      setError("failed");
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "h-12 w-full rounded-xl border border-slate-200 bg-white px-4 text-base text-slate-900 shadow-sm outline-none transition focus:border-sky-600 focus:ring-4 focus:ring-sky-600/10 disabled:bg-slate-50 disabled:text-slate-500";

  return (
    <main className="min-h-[100svh] bg-[#edf3fa] p-3 text-slate-900 sm:p-5">
      <div className="mx-auto flex min-h-[calc(100svh-1.5rem)] max-w-[1600px] flex-col rounded-[24px] border border-[#dce7f3] bg-white shadow-[0_12px_50px_-30px_rgba(40,76,120,0.25)] sm:min-h-[calc(100svh-2.5rem)]">
      <header className="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-6 px-6 py-6 sm:px-10 lg:px-16">
        <div className="flex items-center gap-3">
          <img src="/servio_logo.png" alt="Servio" width="128" height="40" className="h-auto w-28 sm:w-32" />
          <span className="hidden border-l border-slate-200 pl-3 text-xs text-slate-500 sm:inline">by Softnix</span>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-500">
          <span>{copy.language}</span>
          <select aria-label={copy.language} value={locale} onChange={e => { if (e.target.value === "th" || e.target.value === "en") setLocale(e.target.value); }} className="rounded-lg border border-slate-200 bg-white px-2 py-2 text-sm text-slate-700 outline-none focus-visible:ring-2 focus-visible:ring-sky-600">
            <option value="th">ไทย</option><option value="en">EN</option>
          </select>
        </label>
      </header>
      <div className="mx-auto grid w-full max-w-[1440px] flex-1 items-center px-6 pb-10 sm:px-10 lg:grid-cols-2 lg:gap-10 lg:px-10 lg:py-2">
        <section className="flex min-w-0 flex-col lg:px-4">
        <div className="mx-auto flex w-full max-w-[400px] flex-col justify-center py-10 sm:py-12 lg:py-6">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">{copy.title}</h1>
          <p className="mt-3 text-sm leading-6 text-slate-500">{copy.subtitle}</p>
          <form className="mt-9 space-y-5" onSubmit={handleLogin} aria-busy={loading}>
            <div className="space-y-2">
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">{copy.username}</label>
              <input id="username" name="username" type="text" autoComplete="username" autoCapitalize="none" spellCheck={false} required disabled={loading} className={inputClass} value={username} onChange={e => setUsername(e.target.value)} />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">{copy.password}</label>
              <div className="relative">
                <input id="password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required disabled={loading} className={`${inputClass} pr-14`} value={password} onChange={e => setPassword(e.target.value)} />
                <button type="button" aria-label={showPassword ? copy.hide : copy.show} aria-pressed={showPassword} title={showPassword ? copy.hide : copy.show} onClick={() => setShowPassword(!showPassword)} className="absolute inset-y-1 right-1 flex w-11 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-50 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-600">
                  {showPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
                </button>
              </div>
            </div>
            {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-3 text-sm leading-6 text-red-700"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" /><span>{copy[error]}</span></div>}
            <button type="submit" disabled={loading} className="flex h-12 w-full items-center justify-center gap-3 rounded-xl bg-[#155bea] px-5 text-sm font-semibold text-white shadow-[0_4px_14px_rgba(20,125,181,0.16)] transition hover:bg-[#104bca] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-600/25 disabled:cursor-wait disabled:opacity-60">
              {loading ? <><LoaderCircle size={18} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />{copy.loading}</> : <>{copy.submit}<ArrowRight size={18} aria-hidden="true" /></>}
            </button>
          </form>
          <p className="mt-7 text-center text-xs leading-6 text-slate-500">{copy.help}</p>
        </div>
        </section>
        <aside className="relative hidden min-w-0 self-center overflow-hidden rounded-[24px] border border-[#d7e8fa] bg-[#e3f1ff] px-8 py-6 lg:flex lg:flex-col lg:items-center lg:justify-center lg:gap-4 xl:px-12">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_55%,rgba(117,177,251,0.28),transparent_65%)]" />
          <h2 className="relative text-center text-[clamp(1.5rem,1.8vw,2rem)] font-semibold leading-[1.35] tracking-tight text-[#18344f] whitespace-pre-line">{copy.headline}</h2>
          <div aria-hidden="true" className="relative aspect-square w-full max-w-[clamp(280px,40svh,320px)] shrink-0">
            {["w-[42%]", "w-[62%]", "w-[82%]", "w-full"].map(size => <div key={size} className={`absolute left-1/2 top-1/2 aspect-square -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80 ${size}`} />)}
            <div className="absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-[6px] border-[#f4f9ff] bg-white shadow-[0_10px_40px_rgba(41,112,208,0.22)]"><img src="/servio_logo.png" alt="" className="h-auto w-[84px]" /></div>
            <div className="absolute left-1/2 top-[1%] flex w-12 -translate-x-1/2 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white text-[#2673d9] shadow-sm"><MessageSquareText size={25} /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">Web Chat</span></div>
            <div className="absolute left-[3%] top-[29%] flex w-12 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white shadow-sm"><img src="/icons8-line-48.png" alt="" className="h-9 w-9" /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">LINE</span></div>
            <div className="absolute right-[1%] top-[29%] flex w-12 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white shadow-sm"><img src="/icons8-facebook-messenger-48.png" alt="" className="h-9 w-9" /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">Messenger</span></div>
            <div className="absolute bottom-[17%] left-[6%] flex w-12 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white text-[#2673d9] shadow-sm"><Headphones size={25} /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">{copy.voice}</span></div>
            <div className="absolute bottom-[17%] right-[2%] flex w-12 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white text-[#2673d9] shadow-sm"><Package size={25} /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">{copy.products}</span></div>
            <div className="absolute bottom-0 left-1/2 flex w-12 -translate-x-1/2 flex-col items-center gap-2"><span className="flex h-12 w-12 items-center justify-center rounded-full border border-[#e1ecfa] bg-white text-[#2673d9] shadow-sm"><ShieldCheck size={25} /></span><span className="whitespace-nowrap text-xs font-medium text-[#365574]">{copy.warranty}</span></div>
          </div>
          <p style={{ margin: 0 }} className="relative max-w-sm text-center text-sm leading-6 text-[#44617d]">{copy.caption}</p>
        </aside>
      </div>
      <footer className="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-4 px-6 py-5 text-[11px] text-slate-500 sm:px-10 lg:px-16"><span>Servio by Softnix</span><span>AI for Customer Service</span></footer>
      </div>
    </main>
  );
}
