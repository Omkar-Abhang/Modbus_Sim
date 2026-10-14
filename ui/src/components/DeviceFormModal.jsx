import { useEffect } from "react";
import { Alert, Form, Input, InputNumber, Modal, Select, Switch, Tag } from "antd";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

function DeviceFormModal({ open, device, onCancel, onSave, saving }) {
  const [form] = Form.useForm();
  const { data: templates = [] } = useQuery({ queryKey: ["templates"], queryFn: () => api.get("/templates") });
  const templateId = Form.useWatch("template_id", form);
  const template = templates.find((t) => t.id === templateId);

  useEffect(() => {
    if (!open) return;
    if (device) {
      form.setFieldsValue(device);
    } else {
      form.resetFields();
      api.get("/devices/next-unit").then((r) => form.setFieldsValue({ unit_id: r.unit_id, enabled: true }));
    }
  }, [open, device, form]);

  // TCP-ready templates first: only those can be polled by the gateway over the network
  const options = [...templates]
    .sort((a, b) => Number(b.tcp_ready) - Number(a.tcp_ready) || a.name.localeCompare(b.name))
    .map((t) => ({
      value: t.id,
      search: `${t.name} ${t.sub_type}`.toLowerCase(),
      label: (
        <div className="flex items-center justify-between gap-2">
          <span className="truncate">{t.name}</span>
          <span className="shrink-0">
            <Tag className="m-0 text-[10px]" color={t.tcp_ready ? "green" : "default"}>
              {t.sub_type}
            </Tag>
          </span>
        </div>
      ),
    }));

  return (
    <Modal
      title={device ? `Edit ${device.name}` : "Add simulated device"}
      open={open}
      onCancel={onCancel}
      okText={device ? "Save" : "Add device"}
      confirmLoading={saving}
      onOk={() => form.validateFields().then((v) => onSave({ overrides: device?.overrides || {}, ...v }))}
      destroyOnClose
    >
      <Form form={form} layout="vertical" requiredMark={false} initialValues={{ enabled: true }}>
        <Form.Item name="name" label="Name" rules={[{ required: true, message: "Give the device a name" }]}>
          <Input placeholder="e.g. IT Rack 1 meter" />
        </Form.Item>
        <Form.Item name="template_id" label="Template" rules={[{ required: true, message: "Choose a template" }]}>
          <Select
            showSearch
            placeholder="Search templates"
            options={options}
            filterOption={(input, o) => o.search.includes(input.toLowerCase())}
          />
        </Form.Item>
        {template && !template.tcp_ready && (
          <Alert
            className="mb-3"
            type="warning"
            showIcon
            message="The gateway cannot poll this template over TCP"
            description={`Its sub_type is ${template.sub_type} / ${template.register_func_type}. The gateway only polls MOD-TCP devices (input, holding or discrete_input) over the network. Clone it as a custom template and export that to the gateway instead.`}
          />
        )}
        <div className="flex gap-4">
          <Form.Item
            name="unit_id"
            label="Unit id (gateway slave_id)"
            rules={[{ required: true, type: "number", min: 1, max: 247, message: "1 – 247" }]}
          >
            <InputNumber min={1} max={247} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}

export default DeviceFormModal;
