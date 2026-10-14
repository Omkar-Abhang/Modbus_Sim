import { useState } from "react";
import { App, Button, Drawer, Empty, Table, Tag, Tooltip } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MdEdit, MdRestartAlt } from "react-icons/md";
import { api } from "../api";
import { MODE_COLORS, simSummary } from "../registerTypes";
import SimEditor from "./SimEditor";

// Live values of one device + per-zone simulation overrides
function DeviceValuesDrawer({ device, onClose }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(null); // { zone, sim }

  const { data, isLoading } = useQuery({
    queryKey: ["values", device?.id],
    queryFn: () => api.get(`/devices/${device.id}/values`),
    enabled: !!device,
    refetchInterval: 2000,
  });

  const saveOverrides = useMutation({
    mutationFn: (overrides) => api.put(`/devices/${device.id}`, { ...device, overrides }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["values", device.id] });
      queryClient.invalidateQueries({ queryKey: ["devices"] });
      setEditing(null);
    },
    onError: (e) => message.error(e.message),
  });

  const clearWrites = useMutation({
    mutationFn: () => api.del(`/devices/${device.id}/writes`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["values", device.id] }),
  });

  const setOverride = (zone, sim) => {
    const overrides = { ...(device.overrides || {}) };
    if (sim) overrides[zone] = sim;
    else delete overrides[zone];
    saveOverrides.mutate(overrides);
  };

  const columns = [
    { title: "Zone", dataIndex: "zone", width: 110, render: (z, r) => <Tooltip title={r.name}><span className="font-medium">{z}</span></Tooltip> },
    { title: "Addr", dataIndex: "register_address", width: 70, render: (a, r) => (r.kind === "bit" && r.bit ? `${a}.${r.bit}` : a) },
    { title: "Type", dataIndex: "kind", width: 80, render: (k) => <span className="text-xs text-slate-500">{k}</span> },
    {
      title: "Value",
      dataIndex: "value",
      width: 110,
      align: "right",
      render: (v) => <span className="font-mono">{v ?? "—"}</span>,
    },
    {
      title: <Tooltip title="What the gateway decodes from the registers (after type conversion and multiplier)">Gateway reads</Tooltip>,
      dataIndex: "gateway_value",
      width: 110,
      align: "right",
      render: (v) => <span className="font-mono text-[#0F678F]">{v ?? "—"}</span>,
    },
    {
      title: "Raw",
      dataIndex: "words",
      width: 120,
      render: (w) => <span className="font-mono text-[11px] text-slate-500">{w.join(" ")}</span>,
    },
    {
      title: "Simulation",
      key: "sim",
      render: (_, r) =>
        editing?.zone === r.zone ? (
          <div className="flex items-center gap-1">
            <SimEditor value={editing.sim} onChange={(sim) => setEditing({ zone: r.zone, sim })} />
            <Button size="small" type="primary" loading={saveOverrides.isPending} onClick={() => setOverride(r.zone, editing.sim)}>
              Save
            </Button>
            <Button size="small" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <Tag color={MODE_COLORS[r.sim.mode]} className="m-0">
              {r.sim.mode}
            </Tag>
            <span className="text-xs text-slate-600">{simSummary(r.sim)}</span>
            {r.overridden && <Tag className="m-0 text-[10px]" color="orange">device override</Tag>}
            <Tooltip title="Change for this device only">
              <Button size="small" type="text" icon={<MdEdit />} onClick={() => setEditing({ zone: r.zone, sim: r.sim })} />
            </Tooltip>
            {r.overridden && (
              <Tooltip title="Back to template setting">
                <Button size="small" type="text" icon={<MdRestartAlt />} onClick={() => setOverride(r.zone, null)} />
              </Tooltip>
            )}
          </div>
        ),
    },
  ];

  return (
    <Drawer
      title={device ? `${device.name} · unit ${device.unit_id} · ${device.template_name}` : ""}
      open={!!device}
      onClose={() => {
        setEditing(null);
        onClose();
      }}
      width="min(1100px, 95vw)"
      destroyOnClose
    >
      <Table
        size="small"
        rowKey="zone"
        loading={isLoading}
        columns={columns}
        dataSource={data?.zones || []}
        pagination={false}
        scroll={{ y: "calc(100vh - 300px)" }}
      />
      <div className="mt-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-semibold text-slate-700">Values written by the gateway (FC05/06/15/16)</span>
          <Button size="small" disabled={!data?.writes?.length} onClick={() => clearWrites.mutate()}>
            Clear writes
          </Button>
        </div>
        {data?.writes?.length ? (
          <div className="flex flex-wrap gap-1">
            {data.writes.map((w) => (
              <Tag key={`${w.table}-${w.address}`} className="font-mono">
                {w.table} {w.address} = {w.value}
              </Tag>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No writes" className="my-2" />
        )}
      </div>
    </Drawer>
  );
}

export default DeviceValuesDrawer;
