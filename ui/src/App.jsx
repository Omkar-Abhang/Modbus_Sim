import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Tag, Tooltip } from "antd";
import { MdDeveloperBoard, MdListAlt, MdViewList } from "react-icons/md";
import { api } from "./api";
import Devices from "./pages/Devices";
import Templates from "./pages/Templates";
import TemplateEditor from "./pages/TemplateEditor";
import RequestLog from "./pages/RequestLog";

const NAV = [
  { to: "/devices", label: "Devices", icon: <MdDeveloperBoard /> },
  { to: "/templates", label: "Templates", icon: <MdViewList /> },
  { to: "/logs", label: "Request log", icon: <MdListAlt /> },
];

function App() {
  const { data: info } = useQuery({ queryKey: ["info"], queryFn: () => api.get("/info") });

  return (
    <div className="h-full flex flex-col">
      <header className="h-12 shrink-0 bg-white border-b border-slate-200 px-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="font-semibold text-slate-800">Modbus Device Simulator</span>
        </div>
        {info && (
          <Tooltip title="Use this as the device port when adding the device on the gateway (MOD-TCP)">
            <div className="flex items-center gap-1 text-xs text-slate-500">
              Modbus TCP
              {info.ips.map((ip) => (
                <Tag key={ip} color="blue" className="m-0 font-mono">
                  {ip}:{info.modbus_port}
                </Tag>
              ))}
            </div>
          </Tooltip>
        )}
      </header>

      <div className="flex flex-1 min-h-0">
        <nav className="w-44 shrink-0 bg-white border-r border-slate-200 p-2 flex flex-col gap-1">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-md text-sm no-underline ${
                  isActive ? "bg-[#0F678F] text-white" : "text-slate-700 hover:bg-slate-100"
                }`
              }
            >
              {n.icon}
              {n.label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 min-w-0 overflow-auto p-4">
          <Routes>
            <Route path="/" element={<Navigate to="/devices" replace />} />
            <Route path="/devices" element={<Devices info={info} />} />
            <Route path="/templates" element={<Templates />} />
            <Route path="/templates/:id" element={<TemplateEditor />} />
            <Route path="/logs" element={<RequestLog />} />
            <Route path="*" element={<Navigate to="/devices" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
