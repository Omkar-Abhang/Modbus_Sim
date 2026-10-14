import { useState } from "react";
import { App, Badge, Button, Empty, Popconfirm, Switch, Table, Tag, Tooltip } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MdAdd, MdDelete, MdEdit, MdRouter, MdShowChart } from "react-icons/md";
import { api } from "../api";
import DeviceFormModal from "../components/DeviceFormModal";
import DeviceValuesDrawer from "../components/DeviceValuesDrawer";
import GatewayHelper from "../components/GatewayHelper";

function ago(ts) {
  if (!ts) return null;
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}

function PollStatus({ d }) {
  if (!d.enabled) return <Badge status="default" text={<span className="text-xs text-slate-400">Disabled</span>} />;
  if (!d.last_poll) return <Badge status="warning" text={<span className="text-xs">Waiting for gateway</span>} />;
  const fresh = Date.now() / 1000 - d.last_poll < 120;
  return (
    <Tooltip title={d.last_client ? `Last request from ${d.last_client}` : undefined}>
      <Badge
        status={fresh ? "success" : "error"}
        text={<span className="text-xs">{fresh ? "Polled" : "Stopped"} {ago(d.last_poll)}</span>}
      />
    </Tooltip>
  );
}

function Devices({ info }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [formDevice, setFormDevice] = useState(undefined); // undefined = closed, null = new
  const [valuesId, setValuesId] = useState(null);
  const [gatewayDevice, setGatewayDevice] = useState(null);

  const { data: devices = [], isLoading } = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.get("/devices"),
    refetchInterval: 3000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["devices"] });

  const save = useMutation({
    mutationFn: (body) => (formDevice ? api.put(`/devices/${formDevice.id}`, body) : api.post("/devices", body)),
    onSuccess: (d) => {
      message.success(`${d.name} saved · unit ${d.unit_id}`);
      setFormDevice(undefined);
      refresh();
    },
    onError: (e) => message.error(e.message),
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }) => api.patch(`/devices/${id}/enabled`, { enabled }),
    onSuccess: refresh,
    onError: (e) => message.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id) => api.del(`/devices/${id}`),
    onSuccess: refresh,
    onError: (e) => message.error(e.message),
  });

  const columns = [
    { title: "Unit", dataIndex: "unit_id", width: 70, sorter: (a, b) => a.unit_id - b.unit_id },
    { title: "Name", dataIndex: "name", render: (n) => <span className="font-medium">{n}</span> },
    {
      title: "Template",
      dataIndex: "template_name",
      render: (name, d) => (
        <div className="flex items-center gap-1">
          <a onClick={() => navigate(`/templates/${d.template_id}`)}>{name}</a>
          {!d.tcp_ready && (
            <Tooltip title="Not a MOD-TCP template: the gateway cannot poll it over the network">
              <Tag color="red" className="m-0 text-[10px]">
                not TCP
              </Tag>
            </Tooltip>
          )}
        </div>
      ),
    },
    {
      title: "Enabled",
      dataIndex: "enabled",
      width: 80,
      render: (enabled, d) => <Switch size="small" checked={enabled} onChange={(v) => toggle.mutate({ id: d.id, enabled: v })} />,
    },
    { title: "Gateway polling", key: "poll", width: 190, render: (_, d) => <PollStatus d={d} /> },
    {
      title: <Tooltip title="Modbus requests in the last minute (one per batch)">Req/min</Tooltip>,
      dataIndex: "requests_per_min",
      width: 80,
      align: "right",
    },
    {
      title: "Errors",
      dataIndex: "errors",
      width: 70,
      align: "right",
      render: (n, d) =>
        n ? (
          <Tooltip title={d.last_error}>
            <span className="text-red-600 font-medium">{n}</span>
          </Tooltip>
        ) : (
          <span className="text-slate-300">0</span>
        ),
    },
    {
      title: "",
      key: "actions",
      width: 200,
      render: (_, d) => (
        <div className="flex gap-1 justify-end">
          <Tooltip title="Live values & simulation">
            <Button size="small" icon={<MdShowChart />} onClick={() => setValuesId(d.id)}>
              Values
            </Button>
          </Tooltip>
          <Tooltip title="How to add this device on the gateway">
            <Button size="small" icon={<MdRouter />} onClick={() => setGatewayDevice(d)} />
          </Tooltip>
          <Button size="small" icon={<MdEdit />} onClick={() => setFormDevice(d)} />
          <Popconfirm title={`Delete ${d.name}?`} onConfirm={() => remove.mutate(d.id)}>
            <Button size="small" danger icon={<MdDelete />} />
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800 m-0">Simulated devices</h2>
          <p className="text-xs text-slate-500 m-0">
            All devices share one Modbus TCP port; the gateway selects a device by its unit id (slave_id).
          </p>
        </div>
        <Button type="primary" icon={<MdAdd />} onClick={() => setFormDevice(null)}>
          Add device
        </Button>
      </div>

      <div className="bg-white rounded-lg shadow-sm">
        <Table
          rowKey="id"
          size="middle"
          loading={isLoading}
          columns={columns}
          dataSource={devices}
          pagination={false}
          locale={{
            emptyText: (
              <Empty description="No simulated devices yet">
                <Button type="primary" onClick={() => setFormDevice(null)}>
                  Add the first device
                </Button>
              </Empty>
            ),
          }}
        />
      </div>

      <DeviceFormModal
        open={formDevice !== undefined}
        device={formDevice}
        saving={save.isPending}
        onCancel={() => setFormDevice(undefined)}
        onSave={(body) => save.mutate(body)}
      />
      <DeviceValuesDrawer device={devices.find((d) => d.id === valuesId)} onClose={() => setValuesId(null)} />
      <GatewayHelper device={gatewayDevice} info={info} onClose={() => setGatewayDevice(null)} />
    </div>
  );
}

export default Devices;
