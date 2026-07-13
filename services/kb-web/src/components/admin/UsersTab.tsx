"use client";

import { useEffect, useState, useCallback } from "react";
import type { User } from "@/types";
import {
  getUsers,
  createUser,
  updateUserPassword,
  updateUserMaxSessions,
  deleteUser,
} from "@/lib/api";
import Modal from "@/components/ui/Modal";
import Toast from "@/components/ui/Toast";

export default function UsersTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);
  const [modal, setModal] = useState<"create" | "pwd" | "maxSessions" | null>(null);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // form fields
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "user">("user");
  const [pwdValue, setPwdValue] = useState("");
  const [maxSessionsValue, setMaxSessionsValue] = useState(20);

  const load = useCallback(async () => {
    try { setUsers(await getUsers()); } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  function showToast(msg: string, type: "success" | "error" = "success") {
    setToast({ msg, type });
  }

  async function handleCreate() {
    try {
      await createUser({ username: newUsername, password: newPassword, role: newRole });
      showToast(`已新增使用者 ${newUsername}`);
      setModal(null);
      setNewUsername(""); setNewPassword(""); setNewRole("user");
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "新增失敗", "error");
    }
  }

  async function handlePwd() {
    if (!selectedUser) return;
    try {
      await updateUserPassword(selectedUser.id, pwdValue);
      showToast("密碼已更新");
      setModal(null); setPwdValue("");
    } catch (e: unknown) {
      showToast((e as Error).message || "更新失敗", "error");
    }
  }

  async function handleMaxSessions() {
    if (!selectedUser) return;
    try {
      await updateUserMaxSessions(selectedUser.id, maxSessionsValue);
      showToast("上限已更新");
      setModal(null);
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "更新失敗", "error");
    }
  }

  async function handleDelete(user: User) {
    if (!confirm(`確定要刪除使用者 ${user.username}？`)) return;
    try {
      await deleteUser(user.id);
      showToast(`已刪除 ${user.username}`);
      load();
    } catch (e: unknown) {
      showToast((e as Error).message || "刪除失敗", "error");
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-gray-700">使用者管理</h2>
        <button
          onClick={() => setModal("create")}
          className="px-4 py-2 bg-blue-700 hover:bg-blue-800 text-white text-sm rounded-lg transition"
        >
          + 新增使用者
        </button>
      </div>

      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              {["用戶名", "角色", "狀態", "最大對話數", "操作"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-800">{u.username}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${u.role === "admin" ? "bg-purple-100 text-purple-700" : "bg-blue-100 text-blue-700"}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {u.is_active ? "啟用" : "停用"}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-600">{u.max_sessions}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setSelectedUser(u); setPwdValue(""); setModal("pwd"); }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      改密碼
                    </button>
                    <button
                      onClick={() => { setSelectedUser(u); setMaxSessionsValue(u.max_sessions); setModal("maxSessions"); }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      對話上限
                    </button>
                    <button
                      onClick={() => handleDelete(u)}
                      className="text-xs text-red-500 hover:underline"
                    >
                      刪除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Create Modal */}
      {modal === "create" && (
        <Modal title="新增使用者" onClose={() => setModal(null)}>
          <div className="flex flex-col gap-3">
            <input placeholder="用戶名" value={newUsername} onChange={(e) => setNewUsername(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <input type="password" placeholder="密碼" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <select value={newRole} onChange={(e) => setNewRole(e.target.value as "admin" | "user")}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
            <div className="flex gap-2 mt-2">
              <button onClick={handleCreate} className="flex-1 bg-blue-700 hover:bg-blue-800 text-white py-2 rounded-lg text-sm transition">新增</button>
              <button onClick={() => setModal(null)} className="flex-1 border py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition">取消</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Change Password Modal */}
      {modal === "pwd" && selectedUser && (
        <Modal title={`更改密碼：${selectedUser.username}`} onClose={() => setModal(null)}>
          <div className="flex flex-col gap-3">
            <input type="password" placeholder="新密碼" value={pwdValue} onChange={(e) => setPwdValue(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <div className="flex gap-2">
              <button onClick={handlePwd} className="flex-1 bg-blue-700 hover:bg-blue-800 text-white py-2 rounded-lg text-sm transition">更新</button>
              <button onClick={() => setModal(null)} className="flex-1 border py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition">取消</button>
            </div>
          </div>
        </Modal>
      )}

      {/* Max Sessions Modal */}
      {modal === "maxSessions" && selectedUser && (
        <Modal title={`對話上限：${selectedUser.username}`} onClose={() => setModal(null)}>
          <div className="flex flex-col gap-3">
            <input type="number" min={1} max={200} value={maxSessionsValue} onChange={(e) => setMaxSessionsValue(Number(e.target.value))}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            <div className="flex gap-2">
              <button onClick={handleMaxSessions} className="flex-1 bg-blue-700 hover:bg-blue-800 text-white py-2 rounded-lg text-sm transition">更新</button>
              <button onClick={() => setModal(null)} className="flex-1 border py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition">取消</button>
            </div>
          </div>
        </Modal>
      )}

      {toast && <Toast message={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}
