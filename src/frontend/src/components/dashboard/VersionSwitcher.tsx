"use client";

import { useState } from "react";
import { Menu } from "@base-ui/react/menu";
import { AlertCircle, Check, Loader2, MoreHorizontal, Pencil, Plus, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ArtifactVersion } from "@/lib/types";

interface VersionSwitcherProps {
  versions: ArtifactVersion[];
  activeVersion: string | null;
  viewedVersion: string | null;
  onSwitch: (versionId: string) => void;
  onCreate?: () => void;
  onRename?: (versionId: string, label: string) => void;
  onDelete?: (versionId: string) => void;
}

export function VersionSwitcher({ versions, activeVersion, viewedVersion, onSwitch, onCreate, onRename, onDelete }: VersionSwitcherProps) {
  const [editingVersion, setEditingVersion] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState("");
  const [menuVersion, setMenuVersion] = useState<string | null>(null);

  const beginRename = (version: ArtifactVersion) => {
    setMenuVersion(null);
    setEditingVersion(version.version_id);
    setEditingLabel(version.label);
  };
  const saveRename = () => {
    if (editingVersion && editingLabel.trim()) onRename?.(editingVersion, editingLabel.trim());
    setEditingVersion(null);
  };

  return (
    <div className="flex max-w-full items-center gap-1 border-b border-border/60" role="group" aria-label="Phiên bản học liệu">
      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
      {versions.map((version) => {
        const selected = version.version_id === viewedVersion;
        return (
          <div key={version.version_id} className="relative flex shrink-0 items-center">
          {editingVersion === version.version_id ? (
            <div className={cn("flex shrink-0 items-center gap-1 border border-transparent px-3 py-2 text-xs font-semibold", selected ? "-mb-px border-border/60 border-b-card bg-card text-foreground" : "text-muted-foreground")}>
              <input autoFocus value={editingLabel} maxLength={40} aria-label="Tên phiên bản" onChange={(event) => setEditingLabel(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") saveRename(); if (event.key === "Escape") setEditingVersion(null); }} className="w-28 bg-transparent text-xs outline-none" />
            </div>
          ) : (
            <button
              type="button"
              aria-pressed={selected}
              title={version.created_at ? `Tạo lúc ${new Date(version.created_at).toLocaleString("vi-VN")}` : version.label}
              onClick={() => onSwitch(version.version_id)}
              className={cn(
                "flex shrink-0 items-center gap-1 border border-transparent px-3 py-2 text-xs font-semibold transition-colors",
                selected ? "-mb-px border-border/60 border-b-card bg-card text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <span>{version.label}</span>
              {version.version_id === activeVersion && <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-label="Đang dùng" />}
              {version.status === "processing" && <Loader2 className="h-3 w-3 animate-spin" aria-label="Đang tạo" />}
              {version.status === "error" && <AlertCircle className="h-3 w-3 text-error" aria-label="Lỗi" />}
            </button>
          )}
          {editingVersion === version.version_id ? <><button type="button" onClick={(event) => { event.stopPropagation(); saveRename(); }} className="grid h-6 w-6 place-items-center text-primary" title="Lưu tên"><Check className="h-3.5 w-3.5" /></button><button type="button" onClick={(event) => { event.stopPropagation(); setEditingVersion(null); }} className="grid h-6 w-6 place-items-center text-muted-foreground" title="Hủy"><X className="h-3.5 w-3.5" /></button></> : (onRename || onDelete) && (
            <Menu.Root modal={false} open={menuVersion === version.version_id} onOpenChange={(open) => setMenuVersion((active) => open ? version.version_id : active === version.version_id ? null : active)}>
              <Menu.Trigger className="-ml-2 mr-1 grid h-6 w-6 shrink-0 place-items-center text-muted-foreground hover:text-foreground" title="Tùy chọn phiên bản" onClick={(event) => event.stopPropagation()}>
                <MoreHorizontal className="h-4 w-4" />
              </Menu.Trigger>
              <Menu.Portal>
                <Menu.Positioner side="bottom" align="end" sideOffset={4} className="z-50">
                  <Menu.Popup className="w-28 border border-border/60 bg-card py-1 text-xs shadow-[var(--shadow-sm)] outline-none">
                    {onRename && <Menu.Item className="flex w-full items-center gap-2 px-3 py-2 text-left outline-none hover:bg-muted data-[highlighted]:bg-muted" onClick={() => beginRename(version)}><Pencil className="h-3.5 w-3.5" />Đổi tên</Menu.Item>}
                    {onDelete && <Menu.Item className="flex w-full items-center gap-2 px-3 py-2 text-left text-error outline-none hover:bg-muted data-[highlighted]:bg-muted" onClick={() => onDelete(version.version_id)}><Trash2 className="h-3.5 w-3.5" />Xóa</Menu.Item>}
                  </Menu.Popup>
                </Menu.Positioner>
              </Menu.Portal>
            </Menu.Root>
          )}
          </div>
        );
      })}
      </div>
      {onCreate && <button type="button" onClick={onCreate} className="grid h-8 w-8 shrink-0 place-items-center text-muted-foreground hover:text-foreground" title="Tạo phiên bản mới"><Plus className="h-4 w-4" /></button>}
    </div>
  );
}
