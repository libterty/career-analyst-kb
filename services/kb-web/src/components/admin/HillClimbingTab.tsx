"use client";

import { useEffect, useState } from "react";
import {
  getHillClimbingPending,
  applyHillClimbingDiffs,
  archiveHillClimbingBatch,
  type HillClimbingDiff,
  type HillClimbingPending,
} from "@/lib/api";

const RISK_LABEL: Record<string, string> = {
  low_risk: "低風險",
  medium_risk: "中風險",
  high_risk: "高風險",
};

const RISK_COLOR: Record<string, string> = {
  low_risk: "bg-green-100 text-green-700",
  medium_risk: "bg-yellow-100 text-yellow-700",
  high_risk: "bg-red-100 text-red-700",
};

export default function HillClimbingTab() {
  const [data, setData] = useState<HillClimbingPending | null>(null);
  const [loading, setLoading] = useState(true);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const d = await getHillClimbingPending();
      setData(d);
      setApproved(new Set(d.diffs.map((d) => d.id)));
    } catch {
      setError("無法載入 hill-climbing 資料");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function toggleDiff(id: string) {
    setApproved((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleApply() {
    if (approved.size === 0) return;
    setApplying(true);
    setError(null);
    setResult(null);
    try {
      const res = await applyHillClimbingDiffs([...approved]);
      setResult(
        `✅ 已套用 ${res.applied.length} 筆（ID: ${res.applied.join(", ")}）` +
          (res.missed.length
            ? `；${res.missed.length} 筆未匹配（ID: ${res.missed.join(", ")}）`
            : "") +
          (res.archived ? "\n📦 批次已自動封存。" : "") +
          `\n${res.note}`,
      );
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "套用失敗");
    } finally {
      setApplying(false);
    }
  }

  async function handleArchive() {
    setArchiving(true);
    setError(null);
    setResult(null);
    try {
      await archiveHillClimbingBatch();
      setResult("📦 批次已封存，待審核佇列已清空。");
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "封存失敗");
    } finally {
      setArchiving(false);
    }
  }

  if (loading) {
    return (
      <div className="text-gray-500 text-sm py-8 text-center">載入中…</div>
    );
  }

  if (error && !data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
        {error}
      </div>
    );
  }

  const diffs = data?.diffs ?? [];

  return (
    <div className="space-y-6">
      {/* Summary */}
      {data && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-blue-800">
              Hill Climbing — 待審核 Prompt 差異
            </span>
            {data.overall_accuracy != null && (
              <span className="text-xs text-blue-600">
                評估準確率：{(data.overall_accuracy * 100).toFixed(1)}%
              </span>
            )}
          </div>
          {data.generated_at && (
            <p className="text-xs text-blue-600 mb-1">
              產生於 {new Date(data.generated_at).toLocaleString("zh-TW")}
            </p>
          )}
          <p className="text-sm text-blue-700">{data.summary}</p>
        </div>
      )}

      {/* Result / error */}
      {result && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-xl px-4 py-3 text-sm whitespace-pre-wrap">
          {result}
        </div>
      )}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Diff list */}
      {diffs.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-6">
          目前沒有待審核的差異
        </p>
      ) : (
        <>
          <div className="space-y-4">
            {diffs.map((diff) => (
              <DiffCard
                key={diff.id}
                diff={diff}
                checked={approved.has(diff.id)}
                onToggle={() => toggleDiff(diff.id)}
              />
            ))}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={handleApply}
              disabled={applying || approved.size === 0}
              className="px-5 py-2 bg-purple-700 hover:bg-purple-800 text-white rounded-xl text-sm font-medium transition disabled:opacity-50"
            >
              {applying ? "套用中…" : `套用已核准的 ${approved.size} 筆差異`}
            </button>
            <button
              onClick={() => setApproved(new Set(diffs.map((d) => d.id)))}
              className="px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition"
            >
              全選
            </button>
            <button
              onClick={() => setApproved(new Set())}
              className="px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition"
            >
              全取消
            </button>
            <button
              onClick={handleArchive}
              disabled={archiving}
              className="ml-auto px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition disabled:opacity-50"
              title="封存此批次，不套用差異"
            >
              {archiving ? "封存中…" : "📦 封存此批次"}
            </button>
          </div>
        </>
      )}

      {/* Apply log */}
      {(data?.apply_log?.length ?? 0) > 0 && (
        <div className="pt-4 border-t border-gray-200">
          <h3 className="text-sm font-medium text-gray-700 mb-3">套用記錄</h3>
          <div className="space-y-2">
            {[...(data?.apply_log ?? [])].reverse().map((entry, i) => (
              <div
                key={i}
                className="flex items-start gap-3 text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2"
              >
                <span className="shrink-0 text-gray-400">
                  {new Date(entry.timestamp).toLocaleString("zh-TW")}
                </span>
                <span>
                  {entry.outcome === "applied" ? "✅" : "⚠️"} 套用{" "}
                  <span className="font-medium text-gray-700">
                    [{entry.applied.join(", ")}]
                  </span>
                  {entry.missed?.length > 0 && (
                    <span className="text-yellow-600">
                      {" "}
                      · 未匹配 [{entry.missed.join(", ")}]
                    </span>
                  )}
                  {entry.applied_by && (
                    <span className="text-gray-400">
                      {" "}
                      · by {entry.applied_by}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DiffCard({
  diff,
  checked,
  onToggle,
}: {
  diff: HillClimbingDiff;
  checked: boolean;
  onToggle: () => void;
}) {
  const riskClass = RISK_COLOR[diff.risk] ?? "bg-gray-100 text-gray-600";

  return (
    <div
      className={`border rounded-xl p-4 transition ${
        checked ? "border-purple-300 bg-purple-50" : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          className="mt-1 w-4 h-4 accent-purple-700 cursor-pointer flex-shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-xs font-mono text-gray-400">#{diff.id}</span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full font-medium ${riskClass}`}
            >
              {RISK_LABEL[diff.risk] ?? diff.risk}
            </span>
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">
              {diff.target_category}
            </span>
          </div>
          <p className="text-sm text-gray-700 mb-3">{diff.rationale}</p>
          <div className="grid grid-cols-1 gap-2 text-xs font-mono">
            <div>
              <span className="text-red-500 font-semibold mr-1">−</span>
              <span className="bg-red-50 text-red-800 px-2 py-1 rounded break-all">
                {diff.original_excerpt}
              </span>
            </div>
            <div>
              <span className="text-green-600 font-semibold mr-1">+</span>
              <span className="bg-green-50 text-green-800 px-2 py-1 rounded break-all">
                {diff.replacement}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
