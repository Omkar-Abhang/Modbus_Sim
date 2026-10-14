import { useState } from "react";
import { Button, Select, Switch, Table, Tag } from "antd";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

function RequestLog() {
  const queryClient = useQueryClient();
  const [unitId, setUnitId] = useState(null);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [live, setLive] = useState(true);

  const params = new URLSearchParams({ limit: 500, errors_only: errorsOnly });
  if (unitId) params.set("unit_id", unitId);

  const { data: logs = [], isFetching } = useQuery({
    queryKey: ["logs", unitId, errorsOnly],
    queryFn: () => api.get(`/logs?${params}`),
    refetchInterval: live ? 2000 : false,
  });
  const { data: devices = [] } = useQuery({ queryKey: ["devices"], queryFn: () => api.get("/devices") });

  const clear = async () => {
    await api.del("/logs");
    queryClient.invalidateQueries({ queryKey: ["logs"] });
  };

  const columns = [
    {
      title: "Time",
      dataIndex: "ts",
      width: 110,
      render: (ts) => <span className="font-mono text-xs">{new Date(ts * 1000).toLocaleTimeString("en-GB")}</span>,
    },
    { title: "Client", dataIndex: "client", width: 130, render: (c) => <span className="font-mono text-xs">{c || "—"}</span> },
    { title: "Unit", dataIndex: "unit_id", width: 60 },
    { title: "Device", dataIndex: "device", width: 180, render: (d) => d || <span className="text-slate-300">—</span> },
    { title: "Function", dataIndex: "fc_name", width: 150, render: (n, e) => (e.fc ? `${n} (FC${String(e.fc).padStart(2, "0")})` : n) },
    {
      title: "Registers",
      key: "range",
      width: 120,
      render: (_, e) => (e.address != null ? <span className="font-mono text-xs">{e.address}–{e.address + e.count - 1}</span> : "—"),
    },
    {
      title: "Result",
      dataIndex: "ok",
      render: (ok, e) =>
        ok ? (
          <Tag color="green" className="m-0">
            OK
          </Tag>
        ) : (
          <span>
            <Tag color="red" className="m-0 mr-1">
              Error
            </Tag>
            <span className="text-xs text-red-600">{e.error}</span>
          </span>
        ),
    },
  ];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800 m-0">Request log</h2>
          <p className="text-xs text-slate-500 m-0">Last 500 Modbus requests received - see exactly what the gateway reads.</p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            allowClear
            placeholder="All units"
            style={{ width: 200 }}
            value={unitId}
            onChange={setUnitId}
            options={devices.map((d) => ({ value: d.unit_id, label: `${d.unit_id} · ${d.name}` }))}
          />
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <Switch size="small" checked={errorsOnly} onChange={setErrorsOnly} /> Errors only
          </label>
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <Switch size="small" checked={live} onChange={setLive} /> Live
          </label>
          <Button onClick={clear}>Clear</Button>
        </div>
      </div>
      <div className="bg-white rounded-lg shadow-sm">
        <Table
          rowKey="seq"
          size="small"
          loading={isFetching && !logs.length}
          columns={columns}
          dataSource={logs}
          pagination={{ pageSize: 100, hideOnSinglePage: true }}
          locale={{ emptyText: "No requests yet - waiting for the gateway to poll" }}
        />
      </div>
    </div>
  );
}

export default RequestLog;
