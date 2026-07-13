"use client";

import { useEffect } from "react";

interface ToastProps {
  message: string;
  type?: "success" | "error" | "info";
  onClose: () => void;
}

export default function Toast({ message, type = "info", onClose }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onClose, 3000);
    return () => clearTimeout(t);
  }, [onClose]);

  const bg =
    type === "success"
      ? "bg-green-600"
      : type === "error"
      ? "bg-red-600"
      : "bg-blue-600";

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 ${bg} text-white px-4 py-3 rounded-xl shadow-lg text-sm flex items-center gap-3 max-w-xs`}
    >
      <span className="flex-1">{message}</span>
      <button onClick={onClose} className="text-white/80 hover:text-white text-lg leading-none">
        ×
      </button>
    </div>
  );
}
