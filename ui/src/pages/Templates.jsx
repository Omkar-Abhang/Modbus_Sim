import { useMemo, useState } from "react";
import { App, Button, Checkbox, Input, Popconfirm, Segmented, Table, Tag, Tooltip, Upload } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MdAdd, MdContentCopy, MdDelete, MdEdit, MdFileDownload, MdFileUpload, MdSearch } from "react-icons/md";
import { api, downloadTemplates, uploadTemplates } from "../api";

function Templates() {
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("tcp");
  const [onlyTcp, setOnlyTcp] = useState(false);
  const [selected, setSelected] = useState([]);

  const { data: templates = [], isLoading } = useQuery({ queryKey: ["templates"], queryFn: () => api.get("/templates") });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["templates"] });

  const clone = useMutation({
    mutationFn: (t) => api.post(`/templates?clone_from=${t.id}`, { name: `${t.name} (sim)` }),
    onSuccess: (t) => {
      refresh();
      navigate(`/templates/${t.id}`);
    },
    onError: (e) => message.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id) => api.del(`/templates/${id}`),
    onSuccess: refresh,
    onError: (e) => message.error(e.message),
  });

  const rows = useMemo(() => {
    const q = search.toLowerCase();
    return templates.filter(
      (t) =>
        (filter === "all" || (filter === "tcp" && t.tcp_ready) || (filter === "custom" && t.source === "custom")) &&
        (!q || `${t.name} ${t.sub_type} ${t.gateway_id ?? ""}`.toLowerCase().includes(q)),
    );
  }, [templates, search, filter]);

  const importFile = async (file) => {
    try {
      const r = await uploadTemplates(file, onlyTcp);
      message.success(`Imported: ${r.added} added, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped (not TCP)` : ""}`);
      refresh();
    } catch (e) {
      message.error(e.message);
    }
    return false; // handled manually, no default upload
  };

  const exportSelected = () => {
    modal.confirm({
      title: "Export for the gateway",
      width: 560,
      content: (
        <div className="text-sm">
          Import the downloaded file on the gateway with <b>delete_existing=false</b> so it is added next to the existing templates:
          <pre className="bg-slate-100 text-xs p-2 rounded mt-2 whitespace-pre-wrap">
            {`POST http://<gateway-ip>:5001/dbexpimp/import?template=modbus_templates&delete_existing=false`}
          </pre>
          <span className="text-red-600">delete_existing=true removes every template already on the gateway.</span>
        </div>
      ),
      okText: "Download",
      onOk: () => downloadTemplates(selected),
    });
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (n, t) => (
        <a className="font-medium" onClick={() => navigate(`/templates/${t.id}`)}>
          {n}
        </a>
      ),
    },
    {
      title: "Source",
      dataIndex: "source",
      width: 150,
      render: (s, t) => (
        <div className="flex gap-1">
          <Tag color={s === "custom" ? "purple" : "default"} className="m-0">
            {s === "gateway" ? `gateway #${t.gateway_id}` : "custom"}
          </Tag>
          {t.modified && (
            <Tooltip title="Edited here - export it so the gateway has the same register map">
              <Tag color="orange" className="m-0">
                modified
              </Tag>
            </Tooltip>
          )}
        </div>
      ),
    },
    { title: "Sub type", dataIndex: "sub_type", width: 160 },
    { title: "Function", dataIndex: "register_func_type", width: 120 },
    {
      title: "Byte / word",
      key: "order",
      width: 110,
      render: (_, t) => <span className="text-xs">{t.byte_order} / {t.word_order}</span>,
    },
    { title: "Registers", dataIndex: "registers", width: 90, align: "right" },
    {
      title: "Gateway TCP",
      dataIndex: "tcp_ready",
      width: 110,
      render: (ok) =>
        ok ? (
          <Tag color="green" className="m-0">
            ready
          </Tag>
        ) : (
          <Tooltip title="Gateway polls only MOD-TCP templates (input / holding / discrete_input) over the network">
            <Tag className="m-0">serial only</Tag>
          </Tooltip>
        ),
    },
    {
      title: "Used by",
      dataIndex: "used_by",
      width: 160,
      render: (u) => (u.length ? <span className="text-xs">{u.join(", ")}</span> : <span className="text-slate-300">—</span>),
    },
    {
      title: "",
      key: "actions",
      width: 120,
      render: (_, t) => (
        <div className="flex gap-1 justify-end">
          <Button size="small" icon={<MdEdit />} onClick={() => navigate(`/templates/${t.id}`)} />
          <Tooltip title="Clone as custom template">
            <Button size="small" icon={<MdContentCopy />} loading={clone.isPending} onClick={() => clone.mutate(t)} />
          </Tooltip>
          <Popconfirm
            title={`Delete ${t.name}?`}
            disabled={t.used_by.length > 0}
            onConfirm={() => remove.mutate(t.id)}
          >
            <Tooltip title={t.used_by.length ? "Used by devices" : undefined}>
              <Button size="small" danger icon={<MdDelete />} disabled={t.used_by.length > 0} />
            </Tooltip>
          </Popconfirm>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="text-lg font-semibold text-slate-800 m-0">Device templates</h2>
        <div className="flex flex-wrap items-center gap-2">
          <Checkbox checked={onlyTcp} onChange={(e) => setOnlyTcp(e.target.checked)}>
            <span className="text-xs">only TCP-ready</span>
          </Checkbox>
          <Upload accept=".json" showUploadList={false} beforeUpload={importFile}>
            <Tooltip title="Gateway templates.json (iam-gateway) or an export from this simulator">
              <Button icon={<MdFileUpload />}>Import templates.json</Button>
            </Tooltip>
          </Upload>
          <Button icon={<MdFileDownload />} disabled={!selected.length} onClick={exportSelected}>
            Export for gateway ({selected.length})
          </Button>
          <Button type="primary" icon={<MdAdd />} onClick={() => navigate("/templates/new")}>
            New template
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <Input
          allowClear
          prefix={<MdSearch className="text-slate-400" />}
          placeholder="Search name / sub type / gateway id"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 320 }}
        />
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { value: "tcp", label: `Gateway TCP-ready (${templates.filter((t) => t.tcp_ready).length})` },
            { value: "custom", label: `Custom (${templates.filter((t) => t.source === "custom").length})` },
            { value: "all", label: `All (${templates.length})` },
          ]}
        />
      </div>

      <div className="bg-white rounded-lg shadow-sm">
        <Table
          rowKey="id"
          size="small"
          loading={isLoading}
          columns={columns}
          dataSource={rows}
          rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
          pagination={{ pageSize: 50, hideOnSinglePage: true }}
          locale={{ emptyText: "No templates - import the gateway templates.json or create a new one" }}
        />
      </div>
    </div>
  );
}

export default Templates;
