"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/auth";
import { getMe } from "@/lib/api";
import UsersTab from "@/components/admin/UsersTab";
import PromptsTab from "@/components/admin/PromptsTab";
import DocumentsTab from "@/components/admin/DocumentsTab";
import HillClimbingTab from "@/components/admin/HillClimbingTab";

type Tab = "users" | "prompts" | "documents" | "hillclimbing";

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("users");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.push("/login");
      return;
    }
    getMe()
      .then((me) => {
        if (me.role !== "admin") router.push("/");
        else setReady(true);
      })
      .catch(() => router.push("/login"));
  }, [router]);

  if (!ready) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500 text-sm">載入中…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-blue-700 text-white px-6 py-3 flex items-center gap-3 shadow-md">
        <span className="text-2xl">⚙️</span>
        <h1 className="text-xl font-bold">管理面板</h1>
        <div className="ml-auto flex gap-3">
          <a
            href="/"
            className="text-sm opacity-80 hover:opacity-100 hover:underline"
          >
            ← 返回聊天
          </a>
        </div>
      </header>

      <div className="max-w-5xl mx-auto p-6">
        <div className="flex gap-1 border-b border-gray-200 mb-6">
          {(["users", "prompts", "documents", "hillclimbing"] as Tab[]).map(
            (t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition ${
                  tab === t
                    ? "bg-white border border-b-white text-blue-700 -mb-px"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {t === "users"
                  ? "👥 使用者"
                  : t === "prompts"
                    ? "📝 系統 Prompt"
                    : t === "documents"
                      ? "📄 文件"
                      : "🔬 Prompt 調整"}
              </button>
            ),
          )}
        </div>

        {tab === "users" && <UsersTab />}
        {tab === "prompts" && <PromptsTab />}
        {tab === "documents" && <DocumentsTab />}
        {tab === "hillclimbing" && <HillClimbingTab />}
      </div>
    </div>
  );
}
