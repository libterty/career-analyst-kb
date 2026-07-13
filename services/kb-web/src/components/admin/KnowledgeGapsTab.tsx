"use client";

import { useEffect, useState } from "react";
import { getKnowledgeGaps, updateKnowledgeGapStatus } from "@/lib/api";
import type { KnowledgeGap, KnowledgeGapStatus } from "@/types";

const STATUS_LABEL: Record<KnowledgeGapStatus, string> = {
  open: "待處理",
  reviewed: "已檢視",
  resolved: "已解決",
};

const STATUS_COLOR: Record<KnowledgeGapStatus, string> = {
  open: "bg-red-100 text-red-700",
  reviewed: "bg-yellow-100 text-yellow-700",
  resolved: "bg-green-100 text-green-700",
};

const NEXT_STATUS: Record<KnowledgeGapStatus, KnowledgeGapStatus> = {
  open: "reviewed",
  reviewed: "resolved",
  resolved: "open",
};

export default function KnowledgeGapsTab() {
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [filter, setFilter] = useState<KnowledgeGapStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const status = filter === "all" ? undefined : filter;
      const data = await getKnowledgeGaps(status);
      setGaps(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "載入失敗");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function handleStatusToggle(gap: KnowledgeGap) {
    const next = NEXT_STATUS[gap.status];
    setUpdatingId(gap.id);
    try {
      const updated = await updateKnowledgeGapStatus(gap.id, next);
      setGaps((prev) => prev.map((g) => (g.id === gap.id ? updated : g)));
    } catch {
      setError("更新狀態失敗");
    } finally {
      setUpdatingId(null);
    }
  }

  const counts = gaps.reduce(
    (acc, g) => ({ ...acc, [g.status]: (acc[g.status] ?? 0) + 1 }),
    {} as Record<string, number>,
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-3 text-sm">
          <span className="text-red-600 font-medium">
            待處理 {counts.open ?? 0}
          </span>
          <span className="text-yellow-600 font-medium">
            已檢視 {counts.reviewed ?? 0}
          </span>
          <span className="text-green-600 font-medium">
            已解決 {counts.resolved ?? 0}
          </span>
        </div>
        <div className="flex gap-1">
          {(["all", "open", "reviewed", "resolved"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 text-sm rounded transition ${
                filter === s
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {s === "all" ? "全部" : STATUS_LABEL[s]}
            </button>
          ))}
          <button
            onClick={load}
            className="px-3 py-1 text-sm bg-gray-100 text-gray-600 hover:bg-gray-200 rounded transition ml-2"
          >
            重新整理
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-gray-400 py-8 text-center">載入中…</div>
      ) : gaps.length === 0 ? (
        <div className="text-sm text-gray-400 py-8 text-center">
          沒有知識缺口記錄
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-500 text-xs uppercase tracking-wide">
                <th className="px-3 py-2 border-b border-gray-200">問題</th>
                <th className="px-3 py-2 border-b border-gray-200 w-24">
                  Agent
                </th>
                <th className="px-3 py-2 border-b border-gray-200 w-20">
                  觸發原因
                </th>
                <th className="px-3 py-2 border-b border-gray-200 w-16 text-center">
                  次數
                </th>
                <th className="px-3 py-2 border-b border-gray-200 w-16 text-center">
                  品質
                </th>
                <th className="px-3 py-2 border-b border-gray-200 w-24">
                  最後出現
                </th>
                <th className="px-3 py-2 border-b border-gray-200 w-28 text-center">
                  狀態
                </th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((gap) => (
                <tr
                  key={gap.id}
                  className="border-b border-gray-100 hover:bg-gray-50"
                >
                  <td className="px-3 py-2 max-w-xs">
                    <span
                      className="block truncate"
                      title={gap.redacted_question}
                    >
                      {gap.redacted_question}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 text-xs">
                    {gap.agent_name}
                  </td>
                  <td className="px-3 py-2 text-gray-500 text-xs">
                    {gap.trigger}
                  </td>
                  <td className="px-3 py-2 text-center font-medium">
                    {gap.occurrences}
                  </td>
                  <td className="px-3 py-2 text-center text-gray-500">
                    {gap.quality_score != null
                      ? gap.quality_score.toFixed(1)
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-gray-400 text-xs">
                    {new Date(gap.last_seen_at).toLocaleDateString("zh-TW")}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <button
                      onClick={() => handleStatusToggle(gap)}
                      disabled={updatingId === gap.id}
                      className={`px-2 py-0.5 rounded text-xs font-medium transition ${STATUS_COLOR[gap.status]} ${updatingId === gap.id ? "opacity-50 cursor-not-allowed" : "hover:opacity-80 cursor-pointer"}`}
                    >
                      {updatingId === gap.id
                        ? "…"
                        : STATUS_LABEL[gap.status]}
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
