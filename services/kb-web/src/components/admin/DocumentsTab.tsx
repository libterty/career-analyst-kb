"use client";

import { useEffect, useRef, useState } from "react";
import { getDocuments, uploadDocument, deleteDocument } from "@/lib/api";
import type { DocumentItem } from "@/types";

export default function DocumentsTab() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDocs(await getDocuments());
    } catch {
      setError("無法載入文件列表");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await uploadDocument(file);
      setSuccess(`已上傳「${result.filename}」，共 ${result.chunks} 個區塊`);
      await load();
    } catch (err: unknown) {
      setError((err as Error).message ?? "上傳失敗");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(doc: DocumentItem) {
    if (!confirm(`確定要刪除「${doc.filename}」嗎？此操作無法復原。`)) return;
    setError(null);
    setSuccess(null);
    try {
      await deleteDocument(doc.id);
      setSuccess(`已刪除「${doc.filename}」`);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
    } catch {
      setError("刪除失敗");
    }
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-2 rounded text-sm">
          {success}
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">
          知識庫文件（{docs.length} 份）
        </h2>
        <label
          className={`cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded text-sm font-medium text-white transition ${
            uploading
              ? "bg-blue-400 cursor-not-allowed"
              : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {uploading ? "上傳中…" : "📤 上傳文件"}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.pptx"
            className="hidden"
            disabled={uploading}
            onChange={handleUpload}
          />
        </label>
      </div>

      {loading ? (
        <div className="text-center py-10 text-gray-400 text-sm">載入中…</div>
      ) : docs.length === 0 ? (
        <div className="text-center py-10 text-gray-400 text-sm">
          尚無文件，請上傳 PDF / DOCX / PPTX
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-100 text-gray-600 text-left">
                <th className="px-4 py-2 font-medium">檔案名稱</th>
                <th className="px-4 py-2 font-medium text-right">頁數</th>
                <th className="px-4 py-2 font-medium text-right">區塊數</th>
                <th className="px-4 py-2 font-medium">上傳時間</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr
                  key={doc.id}
                  className="border-t border-gray-100 hover:bg-gray-50"
                >
                  <td className="px-4 py-2 font-mono text-xs text-gray-800 max-w-xs truncate">
                    {doc.filename}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600">
                    {doc.pages}
                  </td>
                  <td className="px-4 py-2 text-right text-gray-600">
                    {doc.chunk_count}
                  </td>
                  <td className="px-4 py-2 text-gray-500 text-xs">
                    {new Date(doc.uploaded_at).toLocaleString("zh-TW")}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => handleDelete(doc)}
                      className="text-red-500 hover:text-red-700 text-xs font-medium transition"
                    >
                      刪除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
