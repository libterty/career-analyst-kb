"use client";

import { useEffect, useState, useCallback } from "react";
import type { SystemPrompt } from "@/types";
import {
  getSystemPrompts,
  activatePrompt,
  createPrompt,
  updatePrompt,
  deletePrompt,
} from "@/lib/api";
import Modal from "@/components/ui/Modal";
import Toast from "@/components/ui/Toast";

export default function PromptsTab() {
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [selected, setSelected] = useState<SystemPrompt | null>(null);
  const [formName, setFormName] = useState("");
  const [formContent, setFormContent] = useState("");

  const load = useCallback(async () => {
    try { setPrompts(await getSystemPrompts()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  function showToast(msg: string, type: "success" | "error" = "success") {
    setToast({ msg, type });
  }

  async function handleActivate(p: SystemPrompt) {
    try {
      await activatePrompt(p.id);
      showToast(`已啟用：${p.name}`);
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "操作失敗", "error");
    }
  }

  async function handleCreate() {
    try {
      await createPrompt({ name: formName, content: formContent });
      showToast("已新增 Prompt");
      setModal(null); setFormName(""); setFormContent("");
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "新增失敗", "error");
    }
  }

  async function handleEdit() {
    if (!selected) return;
    try {
      await updatePrompt(selected.id, { name: formName, content: formContent });
      showToast("已更新 Prompt");
      setModal(null);
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "更新失敗", "error");
    }
  }

  async function handleDelete(p: SystemPrompt) {
    if (!confirm(`確定要刪除 Prompt「${p.name}」？`)) return;
    try {
      await deletePrompt(p.id);
      showToast(`已刪除：${p.name}`);
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "刪除失敗", "error");
    }
  }

  function openEdit(p: SystemPrompt) {
    setSelected(p);
    setFormName(p.name);
    setFormContent(p.content);
    setModal("edit");
  }

  function openCreate() {
    setFormName(""); setFormContent("");
    setModal("create");
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-700">系統 Prompt 管理</h2>
        <button
          onClick={openCreate}
          className="px-4 py-2 bg-blue-700 hover:bg-blue-800 text-white text-sm rounded-lg transition"
        >
          + 新增 Prompt
        </button>
      </div>

      <div className="flex flex-col gap-3">
        {prompts.map((p) => (
          <div key={p.id} className="bg-white rounded-xl shadow p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-semibold text-gray-800 text-sm">{p.name}</span>
                  {p.is_active && (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">啟用中</span>
                  )}
                </div>
                <p className="text-xs text-gray-500 font-mono whitespace-pre-wrap line-clamp-3">{p.content}</p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                {!p.is_active && (
                  <button onClick={() => handleActivate(p)} className="text-xs text-green-600 hover:underline">啟用</button>
                )}
                <button onClick={() => openEdit(p)} className="text-xs text-blue-600 hover:underline">編輯</button>
                <button onClick={() => handleDelete(p)} className="text-xs text-red-500 hover:underline">刪除</button>
              </div>
            </div>
          </div>
        ))}
        {prompts.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-8">尚無 Prompt</p>
        )}
      </div>

      {(modal === "create" || modal === "edit") && (
        <Modal
          title={modal === "create" ? "新增 Prompt" : `編輯：${selected?.name}`}
          onClose={() => setModal(null)}
        >
          <div className="flex flex-col gap-3">
            <input
              placeholder="名稱"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <textarea
              placeholder="Prompt 內容"
              value={formContent}
              onChange={(e) => setFormContent(e.target.value)}
              rows={8}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 font-mono resize-y"
            />
            <div className="flex gap-2">
              <button
                onClick={modal === "create" ? handleCreate : handleEdit}
                className="flex-1 bg-blue-700 hover:bg-blue-800 text-white py-2 rounded-lg text-sm transition"
              >
                {modal === "create" ? "新增" : "更新"}
              </button>
              <button onClick={() => setModal(null)} className="flex-1 border py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition">
                取消
              </button>
            </div>
          </div>
        </Modal>
      )}

      {toast && <Toast message={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}
