import { useRef } from "react"
import { DownOutlined } from "@ant-design/icons"
import { Button, Dropdown, Input, type InputProps, type InputRef } from "antd"

type AuthorizationReasonInputProps = Pick<InputProps, "aria-label" | "className" | "disabled" | "placeholder"> & {
  value: string
  onChange: (reason: string) => void
  presets: readonly [string, string, string]
}

export function AuthorizationReasonInput({ value, onChange, presets, disabled, ...inputProps }: AuthorizationReasonInputProps) {
  const inputRef = useRef<InputRef>(null)

  return <Input {...inputProps} ref={inputRef} disabled={disabled} value={value}
    style={{ height: "var(--ant-control-height)" }}
    onChange={(event) => onChange(event.target.value)} maxLength={20} showCount
    prefix={<Dropdown trigger={["click"]} placement="topLeft" autoFocus destroyOnHidden disabled={disabled}
      menu={{
        items: presets.map((reason) => ({ key: reason, label: reason })),
        onClick: ({ key }) => {
          onChange(key)
          inputRef.current?.focus({ cursor: "end" })
        },
      }}>
      <Button className="!size-6 !min-w-0" type="text" size="small" icon={<DownOutlined />}
        aria-haspopup="menu" aria-label="快捷授权调整原因" title="快捷原因"
        onClick={(event) => event.stopPropagation()} />
    </Dropdown>} />
}
