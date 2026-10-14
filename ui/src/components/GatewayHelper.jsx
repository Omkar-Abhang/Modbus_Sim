import { useEffect, useMemo, useState } from "react";
import { Alert, App, Button, Collapse, Input, Modal, Select, Steps, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { MdContentCopy } from "react-icons/md";
import { api, downloadTemplates } from "../api";

function CodeBlock({ text }) {
  const { message } = App.useApp();
  const copy = () => {
    // clipboard API needs https or localhost; fall back to a hidden textarea
    const done = () => message.success("Copied");
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done);
    } else {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      document.body.removeChild(area);
      done();
    }
  };
  return (
    <div className="relative">
      <pre className="bg-slate-900 text-slate-100 text-xs rounded-md p-3 pr-10 overflow-auto max-h-64 whitespace-pre-wrap break-all">
        {text}
      </pre>
      <Button size="small" className="absolute top-2 right-2" icon={<MdContentCopy />} onClick={copy} />
    </div>
  );
}

// Step by step: get this simulated device polled by the IESG gateway
function GatewayHelper({ device, info, onClose }) {
  const [gatewayIp, setGatewayIp] = useState("");
  const [pcIp, setPcIp] = useState("");
  const [deviceCode, setDeviceCode] = useState("");

  const { data: template } = useQuery({
    queryKey: ["template", device?.template_id],
    queryFn: () => api.get(`/templates/${device.template_id}`),
    enabled: !!device,
  });

  useEffect(() => {
    if (!device) return;
    setDeviceCode(`MOD${String(device.unit_id).padStart(2, "0")}`);
    setPcIp(info?.ips?.[0] || "");
  }, [device, info]);

  const gw = gatewayIp || "<gateway-ip>";
  const port = `${pcIp || "<pc-ip>"}:${info?.modbus_port ?? 5020}`;
  const needsImport = template && (template.source === "custom" || template.modified);

  const addBody = useMemo(
    () =>
      JSON.stringify(
        {
          template_id: "<id of '" + (template?.name || "") + "' on the gateway>",
          slave_id: device?.unit_id,
          modbus_port: port,
          device_code: deviceCode,
          device_name: device?.name,
        },
        null,
        2,
      ),
    [template, device, port, deviceCode],
  );

  const mapping = useMemo(
    () =>
      JSON.stringify(
        (template?.in_registers || []).map((r) => ({
          device_name: r.name || r.zone,
          ip: gatewayIp || "<gateway-ip>",
          port: 8086,
          panel_no: "<gateway PANEL_NO>",
          device_code: deviceCode,
          zone: r.zone,
          measurement: r.measurement,
        })),
        null,
        2,
      ),
    [template, gatewayIp, deviceCode],
  );

  if (!device) return null;

  return (
    <Modal title={`Add "${device.name}" to the gateway`} open onCancel={onClose} footer={null} width={760}>
      <div className="flex flex-wrap gap-3 mb-4">
        <label className="text-xs text-slate-500">
          Gateway IP
          <Input size="small" placeholder="e.g. 10.36.15.232" value={gatewayIp} onChange={(e) => setGatewayIp(e.target.value.trim())} />
        </label>
        <label className="text-xs text-slate-500">
          This PC's IP (reachable from gateway)
          <Select
            size="small"
            className="block"
            style={{ width: 180 }}
            value={pcIp}
            onChange={setPcIp}
            options={(info?.ips || []).map((ip) => ({ value: ip, label: ip }))}
          />
        </label>
        <label className="text-xs text-slate-500">
          Device code
          <Input size="small" value={deviceCode} onChange={(e) => setDeviceCode(e.target.value.toUpperCase())} style={{ width: 110 }} />
        </label>
      </div>

      {template && !template.tcp_ready && (
        <Alert
          type="error"
          showIcon
          className="mb-3"
          message={`'${template.name}' is ${template.sub_type} / ${template.register_func_type}: the gateway will not poll it over TCP.`}
          description="Clone it as a custom template (Templates page). Custom templates are exported as MOD-TCP."
        />
      )}

      <Steps
        direction="vertical"
        size="small"
        items={[
          needsImport
            ? {
                title: "Import the template on the gateway (adds, does not delete)",
                status: "process",
                description: (
                  <div className="mt-1">
                    <Button size="small" className="mb-2" onClick={() => downloadTemplates([template.id])}>
                      Download sim_modbus_templates.json
                    </Button>
                    <CodeBlock
                      text={`curl -X POST "http://${gw}:5001/dbexpimp/import?template=modbus_templates&delete_existing=false" \\\n  -H "Content-Type: application/json" -d @sim_modbus_templates.json`}
                    />
                    <Typography.Text type="danger" className="text-xs">
                      Never use delete_existing=true: it removes all templates already on the gateway.
                    </Typography.Text>
                  </div>
                ),
              }
            : {
                title: "Template already exists on the gateway",
                status: "finish",
                description: (
                  <span className="text-xs">
                    Imported from the gateway file
                    {template?.gateway_id ? ` (id ${template.gateway_id} there)` : ""} — not modified here.
                  </span>
                ),
              },
          {
            title: "Find the template id on the gateway",
            status: "process",
            description: (
              <div className="mt-1">
                <span className="text-xs text-slate-500">Look for name "{template?.name}" with sub_type MOD-TCP.</span>
                <CodeBlock text={`curl -s http://${gw}:5001/devices/modbus/listTemplate`} />
              </div>
            ),
          },
          {
            title: "Add the device",
            status: "process",
            description: (
              <div className="mt-1">
                <CodeBlock
                  text={`curl -X POST http://${gw}:5001/devices/modbus/addFromTemplate \\\n  -H "Content-Type: application/json" -d '${addBody}'`}
                />
                <span className="text-xs text-slate-500">
                  Replace template_id with the number from step 2. Restart the gateway service if polling does not start; the Devices page
                  here shows "Polled" as soon as requests arrive. Make sure the gateway can reach {port} (firewall).
                </span>
              </div>
            ),
          },
          {
            title: "Check the data",
            status: "process",
            description: (
              <CodeBlock
                text={`curl -s "http://${gw}:5001/status_all_device/%7Bunique-tag%7D?unique_tag=${deviceCode}-${template?.in_registers?.[0]?.zone || "ZONE"}"`}
              />
            ),
          },
        ]}
      />

      <Collapse
        size="small"
        className="mt-2"
        items={[
          {
            key: "mapping",
            label: "Rack dashboard device_mapping.json entries for this device",
            children: <CodeBlock text={mapping} />,
          },
        ]}
      />
    </Modal>
  );
}

export default GatewayHelper;
